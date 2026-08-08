// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. The UI lens asks for shots of the real app
// including one failure, and a screenshot taken by hand is one nobody can reproduce when the UI
// changes. Ported from docs-extract's copy (kit #2), same shape: this kit's UI is also one
// document, one call, no multi-step flow to drive.
//
// ⚠︎ IT NEVER SPENDS ON ITS OWN. Both shots here are free — /api/state and /api/doc need
// nothing, and clicking Detect with no API_KEY configured returns a calm 200 with no call made.
// A third, --live shot (a real answered call) is deliberately NOT taken by this pass: docs-comply
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
const PORT = Number(process.env.PORT || 8771)
const LIVE = process.argv.includes('--live')

function chromePath() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) return process.env.PUPPETEER_EXECUTABLE_PATH
  return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

mkdirSync(OUT, { recursive: true })

// ⚠︎ REFUSE TO RUN IF THE PORT IS ALREADY TAKEN — and this is not the usual "is a server up yet"
// check, it is the opposite one, added because its absence cost a real provider call.
//
// The identity check below asks "is the thing on this port docs-comply?". A STALE COPY OF THIS
// KIT, left listening by an earlier session, answers that perfectly — it IS docs-comply. But it
// was started with the operator's real API_KEY, while this script deliberately starts its server
// with the key blanked so that clicking the button is free. The spawn below then loses the bind,
// dies quietly, and the script photographs the old server instead: the click reached a process
// holding a live key, made a real call, and the no-key panel this pass exists to capture never
// appeared. Identity is not enough when the imposter is yourself.
//
// So: the port must be FREE before we start, and if it is not, nothing is photographed.
async function portIsFree() {
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/api/state`, { signal: AbortSignal.timeout(1500) })
    return !r.ok
  } catch { return true }
}
if (!(await portIsFree())) {
  console.error(`  !! something is ALREADY serving 127.0.0.1:${PORT}.`)
  console.error('     Refusing to start: this script blanks API_KEY so its shots are free, and a')
  console.error('     server it did not start may hold a real key — clicking would SPEND.')
  console.error(`     Free the port (lsof -nP -iTCP:${PORT} -sTCP:LISTEN) or set PORT= to a spare one.`)
  process.exit(4)
}


// THE SERVER IS STARTED WITHOUT A KEY UNLESS --live. src/config.py reads the environment, so
// blanking the variables gives the genuine no-key path rather than a mocked one.
const env = { ...process.env, PORT: String(PORT) }
if (!LIVE) { env.API_KEY = ''; env.LLM_API_KEY = ''; env.OPENAI_API_KEY = '' }

const server = spawn('python3', ['-m', 'src.app'], { cwd: HERE, env, stdio: 'ignore' })
process.on('exit', () => server.kill())

// ⚑ PROVE THE THING ON THAT PORT IS THIS KIT BEFORE PHOTOGRAPHING IT — same discipline the
// sibling scripts learned the hard way: a dead server is caught by any timeout, but a LIVE server
// belonging to something else answers everything. /api/state must answer, with this kit's
// own shape: a documents list of exactly the 30 CTG records this kit ships.
async function proveItIsOurs() {
  let last = 'no attempt completed'
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/state`)
      if (!r.ok) {
        last = `HTTP ${r.status} from /api/state`
      } else {
        const j = await r.json()
        if (Array.isArray(j.documents) && j.documents.length === 30
            && j.documents.every((d) => /^NCT\d+$/.test(d))) return j
        last = 'answered, but not with this kit\'s shape'
      }
    } catch (e) {
      last = e.message
    }
    await sleep(250)
  }
  console.error(`  !! nothing recognisable as docs-comply is serving 127.0.0.1:${PORT}.`)
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
  // fullPage: the five summary boxes and the reconciliation line sit below a 900px
  // fold, and they are the whole point of this panel — a shot that crops them shows a
  // rule list and hides the arithmetic the Admin console got wrong on seven kits.
  await page.screenshot({ path: path.join(OUT, 'comply-landing.png'), fullPage: true })
  console.log('  wrote comply-landing.png')

  // 2. Press "Check against rulebook". With DOC set, a specific document is selected first.
  //
  // ⚠︎ THE NO-KEY SHOT IS THE FREE ONE AND IT IS A REAL STATE, NOT A MOCK. The server above is
  //    started with API_KEY blanked, so clicking the button exercises the genuine "no key
  //    configured" path in src/app.py — a calm 200 with a note, no call made, nothing billed.
  //
  //    ⚑ AND THAT BLANKING IS THE POINT, recorded because this kit paid for its absence. While
  //    smoke-testing POST /api/check by hand, a key WAS configured in the repo-root .env and the
  //    request made a real, unintended provider call. A script that blanks the variable cannot
  //    make that mistake; a person with curl can, and did. Free-by-construction beats
  //    free-by-intention.
  //
  //    --live adds a third shot of a real answered panel and SPENDS ONE CALL. It is not taken by
  //    default. The kit's paid evidence is r001-docs-comply, a full 30-document run whose numbers
  //    are committed; a screenshot is not where a measurement should come from.
  if (process.env.DOC) {
    await page.select('#doc', process.env.DOC)
    await sleep(500)
  }
  const btn = await page.$('#go')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => document.querySelector('#s-total').textContent !== '—'
              && !document.querySelector('#go').disabled,
        { timeout: 120000 })
      await sleep(400)
    } else {
      await page.waitForFunction(
        () => !document.querySelector('#note').hidden,
        { timeout: 15000 })
      await sleep(300)
    }
    const name = LIVE ? 'comply-answered.png' : 'comply-nokey.png'
    await page.screenshot({ path: path.join(OUT, name), fullPage: true })
    console.log(`  wrote ${name}`)
  } else {
    console.log('  !! no #go control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
