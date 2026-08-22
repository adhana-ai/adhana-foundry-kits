// Screenshot the running kit UI, for the use-case standard's UI lens.
//
//   node tools/shoot_ui.mjs               # the two free shots
//   node tools/shoot_ui.mjs --live        # adds the answered shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8952)
const LIVE = process.argv.includes('--live')

function chromePath() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) return process.env.PUPPETEER_EXECUTABLE_PATH
  return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

mkdirSync(OUT, { recursive: true })

const env = { ...process.env, PORT: String(PORT) }
if (!LIVE) { env.API_KEY = ''; env.LLM_API_KEY = ''; env.OPENAI_API_KEY = '' }

async function portIsFree(port) {
  const net = await import('node:net')
  return new Promise((resolve) => {
    const s = net.createConnection({ host: '127.0.0.1', port })
    const done = (v) => { try { s.destroy() } catch {} ; resolve(v) }
    s.setTimeout(1200)
    s.on('connect', () => done(false))
    s.on('timeout', () => done(true))
    s.on('error', () => done(true))
  })
}
if (!(await portIsFree(PORT))) {
  console.error(`  !! something is ALREADY listening on 127.0.0.1:${PORT}.`)
  console.error('     Refusing to start: this script blanks API_KEY so its shots are free, and a')
  console.error('     server it did not start may hold a real key — clicking would SPEND.')
  console.error(`     Free the port (lsof -nP -iTCP:${PORT} -sTCP:LISTEN) or set PORT= to a spare one.`)
  process.exit(4)
}

const server = spawn('python3', ['-m', 'src.app'], { cwd: HERE, env, stdio: 'ignore' })
process.on('exit', () => server.kill())

const PUP = process.env.PUPPETEER_MODULE || 'puppeteer'
let puppeteer
try {
  puppeteer = (await import(PUP)).default
} catch {
  console.error('  !! puppeteer not resolvable as %r.', PUP)
  console.error('     Set PUPPETEER_MODULE to an installed copy.')
  process.exit(2)
}
let browser
try {
  await sleep(1500)
  browser = await puppeteer.launch({ executablePath: chromePath(), args: ['--no-sandbox'] })
  const page = await browser.newPage()
  // ⚠︎ 1560 HIGH, TALLER AGAIN THAN THE SIBLING KIT THIS WAS FORKED FROM, AND THE HEIGHT IS THE
  // POINT. This kit has SEVENTEEN field rows plus SIX decided rows -- two of which wrap (the
  // rulebook's own reasoning, and what would settle an undecidable alert) -- and all of it sits
  // under a notice that says the kit clears nothing, blocks nothing and files nothing. A shot that
  // crops either the 'Put in front of a person' row or that notice would be a picture of a
  // different, more confident product than the one that ships.
  await page.setViewport({ width: 1280, height: 1560, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(600)

  await page.screenshot({ path: path.join(OUT, 'adjudicate-fields.png') })
  console.log('  wrote adjudicate-fields.png')

  if (LIVE) {
    // SCR-0006 exercises every moving part at once, and it is the sharpest alert in the corpus:
    // identical names, identical full dates of birth, identical places of birth, identical
    // nationalities, an engine match score of 0.94 the model never sees, and an analyst note
    // reading "I am satisfied these are the same party." -- against two DIFFERENT passport
    // numbers. The rulebook answers not_a_match on the identifier alone, names it as the deciding
    // one, and the escalation rule correctly does NOT fire even though the account is live,
    // because a dismissible alert does not jump the queue.
    await page.select('#doc', 'SCR-0006')
    await sleep(300)
  }

  const btn = await page.$('#go, button[type=submit], .go, button')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#rows').textContent.includes('not checked yet'),
        { timeout: 120000 })
      await sleep(400)
    } else {
      await sleep(1200)
    }
    await page.screenshot({ path: path.join(OUT, LIVE ? 'adjudicate-answered.png' : 'adjudicate-nokey.png') })
    console.log(`  wrote ${LIVE ? 'adjudicate-answered.png' : 'adjudicate-nokey.png'}`)
  } else {
    console.log('  !! no Adjudicate control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
