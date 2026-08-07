// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. The UI lens asks for shots of the real app
// including one failure, and a screenshot taken by hand is one nobody can reproduce when the UI
// changes. Run this and the lens refills itself. Ported from kit #4's copy (docs-route).
//
// ⚠︎ IT NEVER SPENDS ON ITS OWN. Three of the four shots are free — /api/levels, /api/pair and
// /api/baseline all need nothing, since alignment and the regex baseline are both pure code. Only
// /api/classify calls a provider.
//
//   node tools/shoot_ui.mjs               # the three free shots
//   node tools/shoot_ui.mjs --live        # adds the model verdict shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8769)
const LIVE = process.argv.includes('--live')

function chromePath() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) return process.env.PUPPETEER_EXECUTABLE_PATH
  return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

mkdirSync(OUT, { recursive: true })

// THE SERVER IS STARTED WITHOUT A KEY UNLESS --live. src/config.py reads the environment, so
// blanking the variables gives the genuine no-key path rather than a mocked one.
const env = { ...process.env, PORT: String(PORT) }
if (!LIVE) { env.API_KEY = ''; env.LLM_API_KEY = ''; env.OPENAI_API_KEY = '' }

const server = spawn('python3', ['-m', 'src.app'], { cwd: HERE, env, stdio: 'ignore' })
process.on('exit', () => server.kill())

// ⚑ PROVE THE THING ON THAT PORT IS THIS KIT BEFORE PHOTOGRAPHING IT — same discipline docs-route
// learned the hard way (see its own copy's header): a dead server is caught by any timeout, but a
// LIVE server belonging to something else answers everything. The handshake is on identity, not
// reachability — /api/levels must answer, and with this kit's own shape.
async function proveItIsOurs() {
  let last = 'no attempt completed'
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/levels`)
      if (!r.ok) {
        last = `HTTP ${r.status} from /api/levels`
      } else {
        const j = await r.json()
        if (Array.isArray(j.levels) && j.levels.length && typeof j.floor === 'number'
            && Array.isArray(j.pairs)) return j
        last = 'answered, but not with this kit\'s shape'
      }
    } catch (e) {
      last = e.message
    }
    await sleep(250)
  }
  console.error(`  !! nothing recognisable as docs-redline is serving 127.0.0.1:${PORT}.`)
  console.error(`     Last: ${last}`)
  console.error('     If another app owns that port, free it or set PORT= to a spare one.')
  console.error('     Refusing to screenshot a page this script cannot identify.')
  process.exit(3)
}

// ⚠︎ PUPPETEER IS NOT A DEPENDENCY OF THIS KIT AND MUST NOT BECOME ONE. A kit's promise is stdlib
// Python and a clone that runs in ten minutes.
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
  await sleep(900)

  // 1. The landing state. A pair is selected and the free regex baseline has already decided —
  //    the shot that shows what this kit is about before anything has been spent.
  await page.screenshot({ path: path.join(OUT, 'redline-baseline.png') })
  console.log('  wrote redline-baseline.png')

  // 2. A pair the regex baseline ABSTAINS on. Found by asking the page, not by hard-coding an id
  //    — a fixed id rots the first time the corpus is rebuilt. If none abstains the shot is
  //    skipped loudly rather than silently duplicating shot 1.
  const ids = await page.$$eval('#pair option', (o) => o.map((x) => x.value))
  let abstained = null
  // Skip the landing pair itself (ids[0]) even if it happens to abstain too — shot 1 already
  // shows it, and a second shot of the identical pair would look like a mistake, not a second
  // finding.
  for (const id of ids.slice(1)) {
    const r = await page.evaluate(async (i) =>
      (await (await fetch('/api/baseline?id=' + encodeURIComponent(i))).json()), id)
    if (r.state === 'abstained') { abstained = id; break }
  }
  if (abstained) {
    await page.select('#pair', abstained)
    await sleep(700)
    await page.screenshot({ path: path.join(OUT, 'redline-baseline-abstains.png') })
    console.log(`  wrote redline-baseline-abstains.png (${abstained})`)
  } else {
    console.log('  !! no pair makes the regex baseline abstain — skipping that shot rather '
                + 'than shooting a duplicate of the one above')
    process.exitCode = 1
  }

  // 3. Press Classify the change. Without a key that is the calm no-key state; with one it is a
  //    real model verdict, including the guardrail line when the floor overrides it.
  const btn = await page.$('#go')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#k-state').textContent.includes('nothing has run'),
        { timeout: 180000 })
      await sleep(500)
    } else {
      await sleep(1400)
    }
    const name = LIVE ? 'redline-model.png' : 'redline-nokey.png'
    await page.screenshot({ path: path.join(OUT, name) })
    console.log(`  wrote ${name}`)
  } else {
    console.log('  !! no Classify control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
