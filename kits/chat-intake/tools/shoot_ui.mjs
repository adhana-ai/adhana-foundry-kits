// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. The UI lens asks for shots of the real app
// including one FAILURE, and a screenshot taken by hand is one nobody can reproduce when the UI
// changes. Ported from docs-comply's copy, with one structural difference: that kit's UI is one
// document and one call, and this one is a conversation you step through, so the shots have to
// drive the stepper rather than press a single button.
//
//   node tools/shoot_ui.mjs          # the free shots: replay, and the checklist full
//   node tools/shoot_ui.mjs --live   # adds the red state. SPENDS ONE CALL.
//
// ⚠︎ THE FREE PASS IS FREE BY CONSTRUCTION, NOT BY INTENTION. The server below is started with
// API_KEY blanked, so the page cannot make a call even if something clicks. docs-comply recorded
// paying for the difference: while smoke-testing by hand, a key WAS configured at the repo root
// and a request made a real unintended provider call.
//
// ⚑ WHY --live EXISTS HERE WHEN docs-comply LEAVES ITS EQUIVALENT UNUSED. This kit's red state —
// "wrong against gold" — is the one thing the standard's "no page of only wins" rule is actually
// about, and it CANNOT appear in replay: replay paints the dataset's own state, which is correct
// by definition. One call on a case both models are known to get wrong is the cheapest honest way
// to photograph a real failure.
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8772)
const LIVE = process.argv.includes('--live')
// The case both deepseek-v4-flash and deepseek-v4-pro invented `account_type` on, in r002 and
// r003. Named rather than searched for, so the shot is of a KNOWN failure and not of whatever
// happened to go wrong today.
const LIVE_DIALOGUE = process.env.DIALOGUE || '39_00123'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function chromePath() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) return process.env.PUPPETEER_EXECUTABLE_PATH
  return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
}

function portIsFree(port) {
  return new Promise((resolve) => {
    const s = net.createServer()
    s.once('error', () => resolve(false))
    s.once('listening', () => s.close(() => resolve(true)))
    s.listen(port, '127.0.0.1')
  })
}

if (!(await portIsFree(PORT))) {
  console.error(`  !! something is ALREADY listening on 127.0.0.1:${PORT}.`)
  console.error('     Refusing to start: the free pass blanks API_KEY so its shots cannot spend,')
  console.error('     and photographing somebody else\'s server would defeat that.')
  console.error(`     Free the port (lsof -nP -iTCP:${PORT} -sTCP:LISTEN) or set PORT=.`)
  process.exit(1)
}

mkdirSync(OUT, { recursive: true })

// ⚠︎ --live NEEDS THE KEY AND THE FREE PASS MUST NOT HAVE IT. One env, two truths.
const env = { ...process.env, PORT: String(PORT) }
if (!LIVE) env.API_KEY = ''
const srv = spawn('python3', ['-m', 'src.app'], { cwd: HERE, env, stdio: 'ignore' })
process.on('exit', () => srv.kill())

async function proveItIsOurs() {
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/state`)
      const j = await r.json()
      // ⚑ PROVE THE THING ON THAT PORT IS THIS KIT BEFORE PHOTOGRAPHING IT. `checklist` keyed by
      // the Banks_1 intents is a fingerprint no other kit's /api/state carries.
      if (j && j.checklist && ('TransferMoney' in j.checklist)) {
        if (!j.built) {
          console.error('  !! the corpus is not built. This kit fetches it (CC BY-SA 4.0):')
          console.error('     python3 -m tools.fetch_corpus && python3 -m tools.build_corpus')
          process.exit(4)
        }
        return j
      }
    } catch { /* not up yet */ }
    await sleep(250)
  }
  console.error(`  !! nothing recognisable as chat-intake is serving 127.0.0.1:${PORT}.`)
  process.exit(3)
}

const PUP = process.env.PUPPETEER_MODULE || 'puppeteer'
let puppeteer
try {
  puppeteer = (await import(PUP)).default
} catch {
  console.error('  !! puppeteer not resolvable as %s. Set PUPPETEER_MODULE.', PUP)
  process.exit(2)
}

let browser
try {
  const state = await proveItIsOurs()
  console.log(`  serving ${Object.keys(state.checklist).length} intent(s), key=${state.has_key}`)
  browser = await puppeteer.launch({ executablePath: chromePath(), args: ['--no-sandbox'] })
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(800)

  // Pick the conversation the shots are of, so re-running produces the same pictures.
  //
  // ⚠︎ VERIFY THE SELECTION TOOK. page.select on a value that is not an option is a SILENT no-op:
  // the first --live pass asked for 39_00123, got 32_00011, and produced a "failure" screenshot of
  // a success. A shot of the wrong subject is worse than no shot, because it looks like evidence.
  const want = LIVE ? LIVE_DIALOGUE : (await page.$eval('#conv', (s) => s.value))
  await page.select('#conv', want)
  const got = await page.$eval('#conv', (s) => s.value)
  if (got !== want) {
    console.error(`  !! asked for conversation ${want}, the picker is showing ${got}.`)
    console.error('     Refusing to photograph a conversation this script did not choose.')
    process.exit(5)
  }
  await sleep(600)

  if (!LIVE) {
    // 1. The opening turn: checklist all "still missing", decision "ask again".
    //    fullPage, because the state cards below the fold are what the panel is teaching.
    await page.screenshot({ path: path.join(OUT, 'intake-opening.png'), fullPage: true })
    console.log('  wrote intake-opening.png')

    // 2. Step to the end: the checklist fills and the decision flips to "nothing further".
    //    ⚠︎ LABELLED REPLAY IN THE UI ITSELF. These values are the dataset's own dialogue state,
    //    not a prediction, and the banner on the page says so — which is the only reason a shot
    //    of a kit with no key configured is honest to publish at all.
    for (let i = 0; i < 12; i++) {
      const done = await page.$eval('#step', (b) => b.disabled)
      if (done) break
      await page.click('#step')
      await sleep(350)
    }
    await page.screenshot({ path: path.join(OUT, 'intake-complete.png'), fullPage: true })
    console.log('  wrote intake-complete.png')
  } else {
    // 3. THE RED STATE, and the reason --live exists. Step to the turn where both models invented
    //    `account_type`; the model's answer replaces replay and the row goes "wrong against gold".
    // Step 0 IS the case both models failed (39_00123#1 — a one-turn prefix), so the model is
    // asked about the turn already on screen rather than advanced past it.
    await page.click('#ask')
    await page.waitForFunction(
      () => document.querySelector('#decision').textContent.includes('[model]'),
      { timeout: 120000 })
    await sleep(500)
    await page.screenshot({ path: path.join(OUT, 'intake-wrong.png'), fullPage: true })
    console.log('  wrote intake-wrong.png  (one call spent)')
  }
} finally {
  if (browser) await browser.close()
  srv.kill()
}
