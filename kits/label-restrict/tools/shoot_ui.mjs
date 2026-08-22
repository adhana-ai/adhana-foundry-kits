// Screenshot the running kit UI, for the use-case standard's UI lens.
//
//   node tools/shoot_ui.mjs               # the two free shots
//   node tools/shoot_ui.mjs --live        # adds the answered shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8902)
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
  // ⚠︎ 2100 HIGH, AND EVERY PIXEL OF IT IS EARNED. This kit's field table is TWENTY-TWO rows,
  // under a safety notice the page must not be screenshotted without, and its payoff is TWO
  // panels below that: the decided answer (verdict AND deciding restriction) and the walk of all
  // eight checks beside it. A shorter viewport cuts the walk, which is the panel that makes the
  // verdict auditable rather than asserted.
  await page.setViewport({ width: 1280, height: 2100, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(600)

  await page.screenshot({ path: path.join(OUT, 'extract-fields.png') })
  console.log('  wrote extract-fields.png')

  if (LIVE) {
    // LBL-0032 exercises every moving part at once. Winter barley is on the label; the rate is a
    // quarter of the maximum; two of three season applications are used; the re-treatment
    // interval is met twice over; the buffer is EXACTLY on its 6 m minimum, which is inside an
    // inclusive limit; the pre-harvest interval is 28 days and harvest is 48 away. Everything on
    // the page reads clean until the last check: the re-entry interval is 48 HOURS and re-entry
    // is planned at 30. The 48 that satisfies nothing here is the same 48 that sits in the
    // days-to-harvest line, which is the trap. The note says the spray records are disputed --
    // the wrong register for a case that only needs eighteen more hours -- and the product is
    // already ON the crop, so the pure-code rule raises the hold.
    await page.select('#doc', 'LBL-0032')
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
