// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. The UI lens asks for shots of the real app
// including one failure, and a screenshot taken by hand is one nobody can reproduce when the UI
// changes. Run this and the lens refills itself. Ported from kit #3's copy.
//
// ⚠︎ IT NEVER SPENDS ON ITS OWN. Three of the four shots are free — and on THIS kit that is not
// merely a convenience, it is the product: the keyword router runs with no key and no money, so
// the free shots contain a real routing decision rather than an empty panel. Only the model
// answer costs a call.
//
//   node tools/shoot_ui.mjs               # the three free shots
//   node tools/shoot_ui.mjs --live        # adds the model-routed shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8900)
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

// ⚑ PROVE THE THING ON THAT PORT IS THIS KIT BEFORE PHOTOGRAPHING IT — added 2026-08-06, after
// this script shot a JUPYTER LOGIN PAGE and filed it as the kit's UI.
//
// ⚠︎ EVERY LAYER BEHAVED CORRECTLY AND THE RESULT WAS STILL A LIE. Port 8899 was already taken by
// a notebook server; `src/app.py` has an EADDRINUSE guard and exited with a clear message, exactly
// as designed; puppeteer connected to the port, got a 200, and screenshotted it. Nothing failed —
// the script simply never asked whether the page in front of it was ours. A dead server would have
// been caught by any timeout; a LIVE server belonging to something else answers everything.
//
// So the handshake is on identity, not on reachability: /api/queues must answer, and it must
// answer with this kit's own shape. Anything else aborts before a single shot is taken, because a
// screenshot of the wrong app is worse than a missing one — a missing shot fails the UI lens, and
// a wrong one passes it.
// ⚠︎ AND THE FIRST VERSION OF THIS FUNCTION DID NOT WORK, WHICH IS THE POINT OF RED-PROVING IT.
// It only bailed out from inside a `catch`, so it caught the shapes that THROW — a refused
// connection, HTML where JSON was expected — and sailed straight past the one that does not: a
// plain 404 from a healthy server that has never heard of /api/queues. `r.ok` was false, nothing
// threw, the loop ran out, the function returned `undefined`, and the script carried on and
// photographed Jupyter a second time. Pointed at the occupied port, it printed
// "wrote route-baseline.png" exactly as before. The loop now has two exits and no fall-through.
async function proveItIsOurs() {
  let last = 'no attempt completed'
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/queues`)
      if (!r.ok) {
        last = `HTTP ${r.status} from /api/queues`
      } else {
        const j = await r.json()
        if (Array.isArray(j.queues) && j.queues.length && typeof j.floor === 'number') return j
        last = 'answered, but not with this kit\'s shape'
      }
    } catch (e) {
      last = e.message
    }
    await sleep(250)
  }
  console.error(`  !! nothing recognisable as docs-route is serving 127.0.0.1:${PORT}.`)
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

  // 1. The landing state. THE FREE ROUTER HAS ALREADY DECIDED — which is the shot that shows what
  //    this kit is about: there is an answer on screen before anything has been spent, and the
  //    model's job is to beat it.
  await page.screenshot({ path: path.join(OUT, 'route-baseline.png') })
  console.log('  wrote route-baseline.png')

  // 2. A document the keyword router REFUSES. Found by asking the page, not by hard-coding an id —
  //    a fixed id rots the first time the corpus is rebuilt, and this kit's corpus is rebuilt by
  //    a script anyone can run. If no such document exists the shot is skipped loudly rather than
  //    silently duplicating shot 1.
  const ids = await page.$$eval('#doc option', (o) => o.map((x) => x.value))
  let declined = null
  for (const id of ids) {
    const r = await page.evaluate(async (i) =>
      (await (await fetch('/api/baseline?id=' + encodeURIComponent(i))).json()), id)
    if (!r.queue) { declined = id; break }
  }
  if (declined) {
    await page.select('#doc', declined)
    await sleep(700)
    await page.screenshot({ path: path.join(OUT, 'route-baseline-declines.png') })
    console.log(`  wrote route-baseline-declines.png (${declined})`)
  } else {
    console.log('  !! no document makes the keyword router decline — skipping that shot rather '
                + 'than shooting a duplicate of the one above')
    process.exitCode = 1
  }

  // 3. Press Route it. Without a key that is the calm configuration state; with one it is a real
  //    model decision, including the guardrail line when the floor overrides it.
  const btn = await page.$('#go')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#k-state').textContent.includes('nothing has run')
           && !document.querySelector('#k-state').textContent.includes('routing'),
        { timeout: 180000 })
      await sleep(500)
    } else {
      await sleep(1400)
    }
    const name = LIVE ? 'route-model.png' : 'route-nokey.png'
    await page.screenshot({ path: path.join(OUT, name) })
    console.log(`  wrote ${name}`)
  } else {
    console.log('  !! no Route control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
