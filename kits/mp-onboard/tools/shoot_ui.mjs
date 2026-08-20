// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. A screenshot taken by hand is one nobody can
// reproduce when the UI changes. Ported from fin-payrun's copy, same shape: this kit's UI is
// also one record (here, one seller application's seven field pairs), one call, no multi-step
// flow to drive.
//
// ⚠︎ IT NEVER SPENDS ON ITS OWN. Both shots here are free -- /api/state and /api/application need
// nothing, and clicking Cross-check with no API_KEY configured returns a calm 200 with no call
// made. A third, --live shot is deliberately NOT taken by this pass: a real committed run's
// numbers should come from evals/run.py, not from a screenshot.
//
//   node tools/shoot_ui.mjs               # the two free shots -- this is the only mode today
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8791)

function chromePath() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) return process.env.PUPPETEER_EXECUTABLE_PATH
  return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

mkdirSync(OUT, { recursive: true })

// ⚠︎ REFUSE TO RUN IF THE PORT IS ALREADY TAKEN -- same discipline data-reconcile's script paid a
// real provider call to learn (traced back to docs-comply). This script blanks API_KEY so its
// shots are free; a server it did not start may hold a real key, and clicking would spend on it.
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
  console.error('     server it did not start may hold a real key -- clicking would SPEND.')
  console.error(`     Free the port (lsof -nP -iTCP:${PORT} -sTCP:LISTEN) or set PORT= to a spare one.`)
  process.exit(4)
}

const env = { ...process.env, PORT: String(PORT), API_KEY: '', LLM_API_KEY: '', OPENAI_API_KEY: '' }
const server = spawn('python3', ['-m', 'src.app'], { cwd: HERE, env, stdio: 'ignore' })
process.on('exit', () => server.kill())

// ⚑ PROVE THE THING ON THAT PORT IS THIS KIT BEFORE PHOTOGRAPHING IT.
async function proveItIsOurs() {
  let last = 'no attempt completed'
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/state`)
      if (!r.ok) {
        last = `HTTP ${r.status} from /api/state`
      } else {
        const j = await r.json()
        if (Array.isArray(j.applications) && j.applications.length === 36
            && j.applications.every((d) => /^APP-2024-\d+$/.test(d))) return j
        last = 'answered, but not with this kit\'s shape'
      }
    } catch (e) {
      last = e.message
    }
    await sleep(250)
  }
  console.error(`  !! nothing recognisable as mp-onboard is serving 127.0.0.1:${PORT}.`)
  console.error(`     Last: ${last}`)
  console.error('     If another app owns that port, free it or set PORT= to a spare one.')
  console.error('     Refusing to screenshot a page this script cannot identify.')
  process.exit(3)
}

const PUP = process.env.PUPPETEER_MODULE || 'puppeteer'
let puppeteer
try {
  puppeteer = (await import(PUP)).default
} catch {
  console.error('  !! puppeteer not resolvable as %s.', PUP)
  console.error('     Set PUPPETEER_MODULE to an installed copy.')
  process.exit(2)
}
let browser
try {
  await proveItIsOurs()
  browser = await puppeteer.launch({ executablePath: chromePath(), args: ['--no-sandbox'] })
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(700)

  // 1. The landing state: the first shipped application loaded, all seven field-pair rows
  //    populated with their declared and document values, no call made yet. fullPage so every
  //    row and the submission note -- the whole point of this panel -- are not cropped below
  //    the fold.
  await page.screenshot({ path: path.join(OUT, 'mp-onboard-landing.png'), fullPage: true })
  console.log('  wrote mp-onboard-landing.png')

  // 2. Press "Cross-check" with no API_KEY configured -- a real state, not a mock. Free-by-
  //    construction: the server above is started with the key blanked in its own environment, so
  //    this cannot become the mistake data-reconcile's own build session made once already
  //    (curl'ing /api/check by hand against a server that inherited a real shared key).
  const btn = await page.$('#go')
  if (btn) {
    await btn.click()
    await page.waitForFunction(
      () => !document.querySelector('#note').hidden,
      { timeout: 15000 })
    await sleep(300)
    await page.screenshot({ path: path.join(OUT, 'mp-onboard-nokey.png'), fullPage: true })
    console.log('  wrote mp-onboard-nokey.png')
  } else {
    console.log('  !! no #go control found -- the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
