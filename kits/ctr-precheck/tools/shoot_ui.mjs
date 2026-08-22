// Screenshot the running kit UI, for the use-case standard's UI lens.
//
//   node tools/shoot_ui.mjs               # the two free shots
//   node tools/shoot_ui.mjs --live        # adds the answered shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8956)
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
  // ⚠︎ 1420 HIGH, TALLER THAN THE SIBLING KIT THIS WAS FORKED FROM. This kit's payoff is the
  // DECIDED panel under the field table — FOURTEEN field rows plus SIX decided rows, two of which
  // wrap — and it sits under a compliance notice the page must not be screenshotted without. At
  // 1180 the 'Recompute before filing' row falls below the fold, which is the one row a reader of
  // a QC surface most needs to see.
  await page.setViewport({ width: 1280, height: 1420, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(600)

  await page.screenshot({ path: path.join(OUT, 'precheck-fields.png') })
  console.log('  wrote precheck-fields.png')

  if (LIVE) {
    // QCP-0040 exercises every moving part at once: a cash-out draft whose own arithmetic is
    // correct — the three entries it lists really do add to 12,250 CU — under a preparer's note
    // reading "Reviewed against the log line by line; totals agree and the pack is ready to go."
    // What the draft missed is a SECOND patron record in the same log, matching on both link keys,
    // carrying 2,500 CU more. Nothing on the drafted total's own line says so, and the pure-code
    // rule raises the recompute flag because the defect changes what would be filed.
    await page.select('#doc', 'QCP-0040')
    await sleep(300)
  }

  const btn = await page.$('#go, button[type=submit], .go, button')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#rows').textContent.includes('not checked yet'),
        { timeout: 180000 })
      await sleep(400)
    } else {
      await sleep(1200)
    }
    await page.screenshot({ path: path.join(OUT, LIVE ? 'precheck-answered.png' : 'precheck-nokey.png') })
    console.log(`  wrote ${LIVE ? 'precheck-answered.png' : 'precheck-nokey.png'}`)
  } else {
    console.log('  !! no Check control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
