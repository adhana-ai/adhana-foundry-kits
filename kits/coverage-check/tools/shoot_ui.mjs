// Screenshot the running kit UI, for the use-case standard's UI lens.
//
//   node tools/shoot_ui.mjs               # the two free shots
//   node tools/shoot_ui.mjs --live        # adds the answered shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8846)
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
  // ⚠︎ 1500 HIGH, TALLER THAN THE SIBLING KIT THIS WAS COPIED FROM, AND MEASURED RATHER THAN
  // GUESSED. This kit's payoff is the 'Needs a recovery review' row at the bottom of the
  // ADJUDICATION panel -- fourteen field rows and six routed rows above it, one of which wraps to
  // four lines because it copies the whole technician narrative. The first attempt used the
  // sibling kit's 1040, the second 1200, and the payoff row was below the fold in BOTH; the shots
  // were opened and looked at, which is the only way that is knowable.
  await page.setViewport({ width: 1280, height: 1500, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(600)

  await page.screenshot({ path: path.join(OUT, 'adjudicate-fields.png') })
  console.log('  wrote adjudicate-fields.png')

  if (LIVE) {
    // WCL-0047 exercises every moving part at once, and every visible signal points the wrong
    // way: a drive axle (a covered powertrain component) on a powertrain plan at 13 months and
    // 17,091 miles (comfortably inside 60/60,000), coded `defect` on the form, with the
    // technician signing off "Should be covered under the plan terms, no question." The one
    // sentence that decides it is the technician's own description of what they found -- "cracked
    // open with fresh impact marks ... a strike from underneath, not a failure" -- which is
    // collision damage, and an exclusion outranks every coverage term. The claim is already PAID,
    // so the pure-code rule routes it for recovery.
    await page.select('#doc', 'WCL-0047')
    await sleep(300)
  }

  const btn = await page.$('#go, button[type=submit], .go, button')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#rows').textContent.includes('not adjudicated yet'),
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
