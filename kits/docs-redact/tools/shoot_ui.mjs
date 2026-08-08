// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. The UI lens asks for shots of the real app
// including one failure, and a screenshot taken by hand is one nobody can reproduce when the UI
// changes. Ported from docs-extract's copy (kit #2), same shape: this kit's UI is also one
// document, one call, no multi-step flow to drive.
//
// ⚠︎ IT NEVER SPENDS ON ITS OWN. Both shots here are free — /api/categories and /api/doc need
// nothing, and clicking Detect with no API_KEY configured returns a calm 200 with no call made.
// A third, --live shot (a real answered call) is deliberately NOT taken by this pass: docs-redact
// already has three real paid runs on disk (r001/r002/r003) and this capture session's brief was
// explicit that no further spend should happen, so the "answered" shot is left for a future pass
// that is authorized to spend one call.
//
//   node tools/shoot_ui.mjs               # the two free shots — this is the only mode today
//   node tools/shoot_ui.mjs --live        # would add an answered shot; SPENDS one call — unused
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8770)
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

// ⚑ PROVE THE THING ON THAT PORT IS THIS KIT BEFORE PHOTOGRAPHING IT — same discipline the
// sibling scripts learned the hard way: a dead server is caught by any timeout, but a LIVE server
// belonging to something else answers everything. /api/categories must answer, with this kit's
// own shape (7 categories, a documents list).
async function proveItIsOurs() {
  let last = 'no attempt completed'
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/categories`)
      if (!r.ok) {
        last = `HTTP ${r.status} from /api/categories`
      } else {
        const j = await r.json()
        if (Array.isArray(j.categories) && j.categories.length === 7
            && Array.isArray(j.documents)) return j
        last = 'answered, but not with this kit\'s shape'
      }
    } catch (e) {
      last = e.message
    }
    await sleep(250)
  }
  console.error(`  !! nothing recognisable as docs-redact is serving 127.0.0.1:${PORT}.`)
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
  await sleep(700)

  // 1. The landing state. The first shipped document loaded, the 7-category legend built, no
  //    call made yet — the shot that shows the two-panel UI and what it asks of a document before
  //    anything is spent.
  await page.screenshot({ path: path.join(OUT, 'redact-landing.png') })
  console.log('  wrote redact-landing.png')

  // 2. Press "Detect & redact" with no API_KEY configured. A configuration state the page renders
  //    calmly — the note explains nothing was called, the source panel stays populated — and, in
  //    the absence of a fresh paid call, the honest failure/limitation shot for this pass.
  const btn = await page.$('#go')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => document.querySelector('#s-spans').textContent !== '—',
        { timeout: 120000 })
      await sleep(400)
    } else {
      await page.waitForFunction(
        () => !document.querySelector('#note').hidden,
        { timeout: 15000 })
      await sleep(300)
    }
    const name = LIVE ? 'redact-answered.png' : 'redact-nokey.png'
    await page.screenshot({ path: path.join(OUT, name) })
    console.log(`  wrote ${name}`)
  } else {
    console.log('  !! no #go control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
