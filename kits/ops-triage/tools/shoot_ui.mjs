// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. A screenshot taken by hand is one nobody can
// reproduce when the UI changes. Ported from data-match's copy, with one structural difference:
// that kit's control is a single similarity threshold, and this one has THREE inputs — a count, a
// keyword regex and a silence signal — because those are the three things the free floor knows.
// The shots have to move all three or they are photographs of a widget.
//
//   node tools/shoot_ui.mjs          # the free shots. Calls no model, spends nothing.
//   node tools/shoot_ui.mjs --live   # adds the model's own answer. SPENDS ONE CALL.
//
// ⚠︎ THE FREE PASS IS FREE BY CONSTRUCTION, NOT BY INTENTION. The server below is started with
// API_KEY blanked, so the page cannot make a call even if something clicks. This repo has a SHARED
// .env at its root that every kit inherits, so a kit that has never been configured still holds a
// live key — and this kit's Ask-the-model button is one click from spending.
//
// ⚑ THE ASSERTIONS ARE THE POINT, NOT THE PICTURES. UC011 shipped a threshold slider with no
// handler at all, under a label promising the tiles would re-count; it rendered perfectly and every
// gate stayed green. So this script reads the tile NUMBERS out of the DOM at each setting and exits
// non-zero if they did not move — and it re-asserts the kit's own headline claim from the panel,
// so a UI that stopped agreeing with `evals/baseline.py` fails the shot rather than shipping.
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8812)
const LIVE = process.argv.includes('--live')
// A quiet-killer window, named rather than searched for, so the live shot is of the KNOWN gap: the
// one trap kind no free setting reaches. Overridable, because the corpus may be regenerated.
const LIVE_WINDOW = process.env.WINDOW_ID || ''

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
      const r = await fetch(`http://127.0.0.1:${PORT}/api/windows?limit=5`)
      const j = await r.json()
      // ⚑ PROVE THE THING ON THAT PORT IS THIS KIT BEFORE PHOTOGRAPHING IT. A `gate` block
      // carrying gate_recall alongside per-window `collapsed` lines is a fingerprint no other kit
      // in this repo serves.
      if (j && j.gate && j.gate.gate_recall !== undefined && j.windows?.[0]?.collapsed) return j
    } catch { /* not up yet */ }
    await sleep(250)
  }
  console.error(`  !! nothing recognisable as ops-triage is serving 127.0.0.1:${PORT}.`)
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

// How many of the six trap kinds the panel says are fully handled at the current setting. This is
// the kit's headline claim, read back off the UI.
const readTraps = (page) =>
  page.$eval('#traps b', (el) => Number(el.textContent.match(/(\d+) of/)[1]))

async function setThreshold(page, value) {
  await page.$eval('#thr', (el, v) => {
    el.value = String(v)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }, value)
  await sleep(350)
  const shown = await page.$eval('#tv', (el) => el.textContent.trim())
  if (shown !== String(value)) {
    console.error(`  !! asked for threshold ${value}, the panel is showing ${shown}.`)
    process.exit(5)
  }
}

async function setBox(page, id, on) {
  await page.$eval(`#${id}`, (el, v) => {
    el.checked = v
    el.dispatchEvent(new Event('change', { bubbles: true }))
  }, on)
  await sleep(350)
}

let browser
const seen = []
try {
  const state = await proveItIsOurs()
  console.log(`  serving ${state.gate.candidates} candidate window(s) of ${state.gate.windows}, live=${LIVE}`)
  browser = await puppeteer.launch({ executablePath: chromePath(), args: ['--no-sandbox'] })
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.setViewport({ width: 1280, height: 980, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(900)

  if (!LIVE) {
    // 1. The default. A count threshold of 20 with the keyword regex on — a fair rendering of what
    //    a great many rotations are running right now.
    await setThreshold(page, 20)
    await setBox(page, 'kw', true)
    await setBox(page, 'ab', false)
    const a = { tiles: await readTiles(page), traps: await readTraps(page) }
    await page.screenshot({ path: path.join(OUT, 'floor-default.png'), fullPage: false })
    console.log('  wrote floor-default.png   ', JSON.stringify(a))
    seen.push(a)

    // 2. Tuned up until the noise stops. The false pages go to zero and THE MISSED INCIDENTS DO
    //    NOT MOVE — which is the finding, and the reason this kit exists rather than a tuning guide.
    await setThreshold(page, 49)
    const b = { tiles: await readTiles(page), traps: await readTraps(page) }
    await page.screenshot({ path: path.join(OUT, 'floor-tuned.png'), fullPage: false })
    console.log('  wrote floor-tuned.png     ', JSON.stringify(b))
    seen.push(b)

    // 3. With the silence signal — the one fact that has to be COMPUTED rather than matched.
    await setBox(page, 'ab', true)
    const c = { tiles: await readTiles(page), traps: await readTraps(page) }
    await page.screenshot({ path: path.join(OUT, 'floor-with-silence.png'), fullPage: false })
    console.log('  wrote floor-with-silence.png', JSON.stringify(c))
    seen.push(c)

    // ── the assertions ──────────────────────────────────────────────────────────────────────────
    const miss = (x) => x.tiles['MISSED INCIDENT']
    const fp = (x) => x.tiles['False page']
    const total = (x) => Object.values(x.tiles).reduce((s, n) => s + n, 0)

    if (fp(seen[0]) <= 0) {
      console.error('  !! the default setting sends no false pages. The control is dead, or the')
      console.error('     corpus no longer contains the noise this kit is about.')
      process.exit(6)
    }
    if (fp(seen[1]) !== 0 || miss(seen[1]) <= 0) {
      console.error(`  !! tuning the threshold up should silence the noise and keep the misses;`)
      console.error(`     got false pages ${fp(seen[1])}, missed ${miss(seen[1])}.`)
      process.exit(6)
    }
    if (miss(seen[2]) >= miss(seen[1])) {
      console.error('  !! the silence signal changed nothing. It is the one input that cannot be')
      console.error('     a regex, so a panel where it does nothing is a broken panel.')
      process.exit(6)
    }
    if (seen.some((x) => total(x) !== total(seen[0]))) {
      console.error('  !! the five tiles stopped reconciling against the window count.')
      process.exit(6)
    }
    // ⚑ THE KIT'S OWN CLAIM, RE-ASSERTED FROM THE UI. If some setting ever does get all six traps,
    // that is a real finding and it must fail the shot rather than ship quietly under a page that
    // still says otherwise.
    const best = Math.max(...seen.map((x) => x.traps))
    if (best >= 6) {
      console.error(`  !! a free setting handled all six traps (${best}). The panel and`)
      console.error('     evals/baseline.py now disagree with the page. Re-measure before shipping.')
      process.exit(7)
    }
    console.log(`  ✓ tiles moved, reconciled at ${total(seen[0])} windows, and no free setting`)
    console.log(`    handled more than ${best} of 6 traps — the claim holds from the UI too.`)
  } else {
    // ⚠︎ ONE CALL, ON PURPOSE, AND ONLY WITH --live. The window is named so the shot is of the
    //    known gap rather than of whatever happened to go wrong today.
    const id = LIVE_WINDOW || (await page.$$eval('[data-win]', (els) => {
      const el = els.find((e) => e.querySelector('.chip.trap')?.textContent.trim() === 'quiet-killer')
      return el ? el.getAttribute('data-win') : null
    }))
    if (!id) { console.error('  !! no quiet-killer window on the page'); process.exit(8) }
    const btn = await page.$(`[data-ask="${id}"]`)
    // ⚠︎ ElementHandle.scrollIntoView DOES NOT EXIST ON THIS PUPPETEER and throws AFTER the click,
    //    which is how a call gets spent and the shot lost. Evaluate it in the page instead.
    await btn.evaluate((el) => el.scrollIntoView({ block: 'center' }))
    await sleep(200)
    await btn.click()
    await page.waitForFunction(
      (w) => !/calling the model/.test(
        document.querySelector(`[data-win="${w}"] [data-verdict]`).textContent), {}, id)
    await sleep(400)
    await page.screenshot({ path: path.join(OUT, 'model-on-the-quiet-killer.png'), fullPage: false })
    console.log('  wrote model-on-the-quiet-killer.png (ONE call spent, window %s)', id)
  }

  if (errors.length) {
    console.error('  !! %d page error(s):', errors.length)
    errors.slice(0, 6).forEach((e) => console.error('     ' + e))
    process.exit(9)
  }
  console.log('  0 page errors')
} finally {
  if (browser) await browser.close()
  srv.kill()
}
