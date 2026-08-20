// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. A screenshot taken by hand is one nobody can
// reproduce when the UI changes. Ported from rcv-disc's copy, with one difference that matters:
// this kit's page renders ALL 33 case windows at once rather than one record at a time, so a
// fullPage shot would be a several-thousand-pixel strip in which nothing is legible. Both shots
// here are therefore FRAMED -- the first on the viewport, the second clipped to one card.
//
// ⚠︎ IT NEVER SPENDS ON ITS OWN. Both shots are free -- /api/state and /api/window need nothing,
// and clicking "Ask the model" with no API_KEY configured returns a calm 200 with no call made. A
// third, --live shot is deliberately NOT taken: a committed run's numbers come from evals/run.py,
// not from a screenshot.
//
//   node tools/shoot_ui.mjs               # the two free shots -- this is the only mode today
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8792)

// The window the second shot frames. cw026 is a false_correlation trap window -- a real
// brute-force + login pair plus an unrelated benign travelling-user login that merely shares the
// same source IP. Framing the trap is the point: the reader should see what the model is being
// tempted by, not a window where nothing is at stake.
const TRAP_WIN = process.env.TRAP_WIN || 'cw026'

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
        if (Array.isArray(j.windows) && j.windows.length === 33
            && j.windows.every((d) => /^cw\d+$/.test(d))) return j
        last = 'answered, but not with this kit\'s shape'
      }
    } catch (e) {
      last = e.message
    }
    await sleep(250)
  }
  console.error(`  !! nothing recognisable as it-sectriage is serving 127.0.0.1:${PORT}.`)
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
  await page.setViewport({ width: 1280, height: 1000, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  // The page fans out one /api/window fetch per window before it renders a single card; wait for
  // the cards themselves rather than for a timer.
  await page.waitForFunction(
    () => document.querySelectorAll('article.win').length === 33, { timeout: 20000 })
  await sleep(400)

  // 1. The landing state: the counted tiles, the gate line naming both planted traps, and the
  //    first window cards with their alerts, indicators and gold grouping already on the page --
  //    all of it before any call is made. Viewport, not fullPage: 33 cards in one strip is a
  //    picture of nothing.
  await page.screenshot({ path: path.join(OUT, 'it-sectriage-landing.png') })
  console.log('  wrote it-sectriage-landing.png')

  // 2. Press "Ask the model" on the trap window with no API_KEY configured -- a real state, not a
  //    mock. Free-by-construction: the server above is started with the key blanked in its own
  //    environment, so this cannot become the mistake data-reconcile's own build session made once
  //    already (curl'ing an endpoint by hand against a server that inherited a real shared key).
  const card = await page.$(`article[data-win="${TRAP_WIN}"]`)
  if (!card) {
    console.log(`  !! no card for ${TRAP_WIN} -- the UI or the corpus changed; fix TRAP_WIN above`)
    process.exitCode = 1
  } else {
    await card.evaluate((el) => el.scrollIntoView({ block: 'center' }))
    await sleep(200)
    const btn = await page.$(`button.ask[data-ask="${TRAP_WIN}"]`)
    if (!btn) {
      console.log('  !! no .ask control found -- the UI changed; fix the selector above')
      process.exitCode = 1
    } else {
      await btn.click()
      await page.waitForFunction(
        (w) => {
          const c = document.querySelector(`article[data-win="${w}"] [data-result]`)
          return c && c.querySelector('p.err')
        },
        { timeout: 15000 }, TRAP_WIN)
      await sleep(300)
      // Clip to the card so the note, the alerts it applies to and the gold grouping are all
      // legible in one frame.
      await card.screenshot({ path: path.join(OUT, 'it-sectriage-nokey.png') })
      console.log('  wrote it-sectriage-nokey.png')
    }
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
