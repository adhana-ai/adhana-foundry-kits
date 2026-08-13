// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. The UI lens asks for shots of the real app
// including one FAILURE, and a screenshot taken by hand is one nobody can reproduce when the UI
// changes. Ported from chat-intake's copy, with one structural difference: that kit's unit of work
// is a conversation you step through, and this one is a PAIR with a control that reclassifies it,
// so the free shots have to MOVE the threshold rather than press a single button.
//
//   node tools/shoot_ui.mjs          # the free shots: the slider at 0.70 and at 0.95
//   node tools/shoot_ui.mjs --live   # adds the model's own failure. SPENDS ONE CALL.
//
// ⚠︎ THE FREE PASS IS FREE BY CONSTRUCTION, NOT BY INTENTION. The server below is started with
// API_KEY blanked, so the page cannot make a call even if something clicks. This repo has a SHARED
// .env at its root that every kit inherits, so a kit that has never been configured still holds a
// live key — and this kit's own Judge button is one click from spending. Blanking the key is the
// only thing that makes an unattended screenshot pass safe to run.
//
// ⚑ WHY THE TWO FREE SHOTS ARE THE SAME PAGE AT TWO SETTINGS. The panel's whole argument is that no
// threshold is simply correct, and a single screenshot of a slider is a screenshot of a widget. Two
// settings with the tiles visibly different is the argument itself, and it doubles as the assertion
// the estate's own rule asks for: an interactive control is not verified until you move it and read
// the state at two positions.
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8811)
const LIVE = process.argv.includes('--live')
// A TWIN pair, named rather than searched for, so the shot is of a KNOWN failure and not of
// whatever happened to go wrong today. r013 said SAME on all six twins — the pair type the prompt's
// third verdict UNSURE exists for — and every one is a false merge.
const LIVE_A = process.env.PAIR_A || 'r031'
const LIVE_B = process.env.PAIR_B || 'r273'

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
  console.error("     and photographing somebody else's server would defeat that.")
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
      const r = await fetch(`http://127.0.0.1:${PORT}/api/pairs?limit=5`)
      const j = await r.json()
      // ⚑ PROVE THE THING ON THAT PORT IS THIS KIT BEFORE PHOTOGRAPHING IT. A `blocking` block
      // carrying candidate_pairs alongside per-pair `fields` is a fingerprint no other kit serves.
      if (j && j.blocking && j.pairs && j.pairs[0] && j.pairs[0].fields) return j
    } catch { /* not up yet */ }
    await sleep(250)
  }
  console.error(`  !! nothing recognisable as data-match is serving 127.0.0.1:${PORT}.`)
  console.error('     Is the corpus built?  python3 tools/build_corpus.py')
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

// The tiles, read out of the DOM rather than out of the picture. A screenshot proves the pixels
// exist; this proves the numbers behind them changed when the control moved.
const readTiles = (page) =>
  page.$$eval('#tiles .tile', (ts) =>
    Object.fromEntries(ts.map((t) => [t.querySelector('.k').textContent.trim(),
                                      Number(t.querySelector('.n').textContent.trim())])))

async function setThreshold(page, value) {
  await page.$eval('#thr', (el, v) => {
    el.value = String(v)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }, value)
  await sleep(400)
  const shown = await page.$eval('#tv', (el) => el.textContent.trim())
  if (shown !== value.toFixed(2)) {
    console.error(`  !! asked for threshold ${value.toFixed(2)}, the panel is showing ${shown}.`)
    process.exit(5)
  }
}

let browser
try {
  const state = await proveItIsOurs()
  console.log(`  serving ${state.blocking.candidate_pairs} candidate pair(s), live=${LIVE}`)
  browser = await puppeteer.launch({ executablePath: chromePath(), args: ['--no-sandbox'] })
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(900)

  if (!LIVE) {
    // 1. The default setting. 0.70 is what the harness scored at, so this shot and the published
    //    baseline table are the same number by construction rather than by coincidence.
    await setThreshold(page, 0.70)
    const low = await readTiles(page)
    await page.screenshot({ path: path.join(OUT, 'threshold-070.png'), fullPage: false })
    console.log('  wrote threshold-070.png  ', JSON.stringify(low))

    // 2. Drag it up. Recall collapses and the false merges DO NOT GO AWAY — which is the finding,
    //    and the reason this kit exists rather than a tuning guide.
    await setThreshold(page, 0.95)
    const high = await readTiles(page)
    await page.screenshot({ path: path.join(OUT, 'threshold-095.png'), fullPage: false })
    console.log('  wrote threshold-095.png  ', JSON.stringify(high))

    // ⚑ THE ASSERTION IS THE POINT, NOT THE PICTURE. This panel shipped once with the slider
    // rendering perfectly and reclassifying NOTHING, because it loaded the top 40 pairs by score
    // and every visible pair was already above 0.90. Two shots of that build would have looked
    // exactly like two shots of this one.
    if (JSON.stringify(low) === JSON.stringify(high)) {
      console.error('  !! the tiles did not move between 0.70 and 0.95.')
      console.error('     The control is inert — refusing to publish shots that imply it works.')
      process.exit(6)
    }
    if (!(high['False merge'] > 0)) {
      console.error('  !! no false merges at 0.95. The kit\'s central claim is that no threshold')
      console.error('     avoids one; a shot contradicting it must not be published unexamined.')
      process.exit(7)
    }
    console.log(`  moved: false merges ${low['False merge']} -> ${high['False merge']}, ` +
                `missed ${low['Missed match']} -> ${high['Missed match']}`)
  } else {
    // 3. The model's own failure, photographed. One call.
    await setThreshold(page, 0.70)
    const sel = `button.judge[data-a="${LIVE_A}"][data-b="${LIVE_B}"]`
    const btn = await page.$(sel)
    if (!btn) {
      console.error(`  !! no Judge button for the pair ${LIVE_A}/${LIVE_B}.`)
      console.error('     Refusing to photograph a pair this script did not choose.')
      process.exit(8)
    }
    // ⚠︎ NOT ElementHandle.scrollIntoView — it is absent on the puppeteer this repo resolves and
    // throws AFTER the click has already spent a call. Evaluated in the page instead, which is
    // supported everywhere and cannot fail between the money going out and the picture being taken.
    await btn.evaluate((el) => el.scrollIntoView({ block: 'center' }))
    await btn.click()
    // The button says "calling…" while in flight; wait for the verdict line to fill instead of
    // guessing a duration.
    await page.waitForFunction(
      (a, b) => document.querySelector(`#v-${a}-${b}`)?.textContent.trim().length > 0,
      { timeout: 120000 }, LIVE_A, LIVE_B)
    await sleep(500)
    const said = await page.$eval(`#v-${LIVE_A}-${LIVE_B}`, (el) => el.textContent.trim())
    console.log('  the model said:', said)
    await btn.evaluate((el) => el.scrollIntoView({ block: 'center' }))
    await sleep(300)
    await page.screenshot({ path: path.join(OUT, 'twin-false-merge.png'), fullPage: false })
    console.log('  wrote twin-false-merge.png')
  }
} finally {
  if (browser) await browser.close()
  srv.kill()
}
