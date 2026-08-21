// Screenshot the running kit UI, for the use-case standard's UI lens.
//
//   node tools/shoot_ui.mjs               # the two free shots
//   node tools/shoot_ui.mjs --live        # adds the answered shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8895)
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
  // ⚠︎ 1040 HIGH, NOT THE SIBLINGS' 820. This kit's payoff is the COMPUTED panel under the
  // field table -- ten field rows plus three computed rows -- and at 820 the 'Needs expedited
  // review' row fell below the fold, so the published shot showed everything except the thing
  // the kit computes. Found by opening the PNG, not by any check.
  await page.setViewport({ width: 1280, height: 1040, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(600)

  await page.screenshot({ path: path.join(OUT, 'extract-fields.png') })
  console.log('  wrote extract-fields.png')

  if (LIVE) {
    // AE-0011 is the record every available shortcut gets wrong, which is why it is the shot:
    // the report calls the event "mild", the Hospitalization field says no and the Event Outcome
    // says recovered -- and the narrative records an episode the treating clinician called
    // immediately life-threatening. Serious by the regulatory criteria, missed by the keyword
    // floor (a false negative in results/eval-b000-rules.json). Not an alphabetical first pick.
    await page.select('#doc', 'AE-0011')
    await sleep(300)
  }

  const btn = await page.$('#go, button[type=submit], .go, button')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#rows').textContent.includes('not extracted yet'),
        { timeout: 120000 })
      await sleep(400)
    } else {
      await sleep(1200)
    }
    await page.screenshot({ path: path.join(OUT, LIVE ? 'extract-answered.png' : 'extract-nokey.png') })
    console.log(`  wrote ${LIVE ? 'extract-answered.png' : 'extract-nokey.png'}`)
  } else {
    console.log('  !! no Extract control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
