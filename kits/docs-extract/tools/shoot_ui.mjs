// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. The UI lens asks for shots of the real app
// including one failure, and that was the last thing in kit #2's capture that "needs a person".
// It does not: the app is a local HTTP server, the browser is already a dependency of this
// estate's smoke suite, and a screenshot taken by hand is a screenshot nobody can reproduce when
// the UI changes. Run this and the lens refills itself.
//
// ⚠︎ IT NEVER SPENDS ON ITS OWN. Two of the three shots are free — the field table before any
// call, and the calm no-key state. The third drives the real Extract button and therefore costs
// one model call, so it only runs with --live, and the caption records which run it came from.
//
//   node tools/shoot_ui.mjs               # the two free shots
//   node tools/shoot_ui.mjs --live        # adds the answered shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = 8899
const LIVE = process.argv.includes('--live')

function chromePath() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) return process.env.PUPPETEER_EXECUTABLE_PATH
  return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

mkdirSync(OUT, { recursive: true })

// THE SERVER IS STARTED WITHOUT A KEY UNLESS --live. src/config.py reads the environment, so
// blanking the two variables gives the genuine no-key path rather than a mocked one — the same
// calm 200 the deployed app returns, which is the state a reader is most likely to meet first.
const env = { ...process.env, PORT: String(PORT) }
if (!LIVE) { env.API_KEY = ''; env.LLM_API_KEY = ''; env.OPENAI_API_KEY = '' }

const server = spawn('python3', ['-m', 'src.app'], { cwd: HERE, env, stdio: 'ignore' })
process.on('exit', () => server.kill())

// ⚠︎ PUPPETEER IS NOT A DEPENDENCY OF THIS KIT AND MUST NOT BECOME ONE. A kit's promise is
// stdlib Python and a clone that runs in ten minutes; adding a browser to package.json to take
// screenshots would put a Chromium download in the path of everyone who only wants to extract
// fields. So the module is located by an explicit env var, and the script says plainly what to
// set when it is not there. ESM resolves relative to THIS FILE, not to cwd — NODE_PATH does
// nothing here, which is the first thing tried and the reason this note exists.
const PUP = process.env.PUPPETEER_MODULE || 'puppeteer'
let puppeteer
try {
  puppeteer = (await import(PUP)).default
} catch {
  console.error('  !! puppeteer not resolvable as %r.', PUP)
  console.error('     Set PUPPETEER_MODULE to an installed copy, e.g.')
  console.error('     PUPPETEER_MODULE=/path/to/node_modules/puppeteer/lib/esm/puppeteer/'
                + 'puppeteer.js node tools/shoot_ui.mjs')
  process.exit(2)
}
let browser
try {
  await sleep(1500)
  browser = await puppeteer.launch({ executablePath: chromePath(), args: ['--no-sandbox'] })
  const page = await browser.newPage()
  // HEIGHT TRIMMED TO THE CONTENT. At 900 the field table ended two hundred pixels up
  // and every shot published a band of empty background — on a page whose whole claim is
  // that this UI is a field table and not a chat box, that band is the largest thing on it.
  await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(600)

  // 1. The field table, before anything is asked of the model. This is the shot that shows the
  //    UI is NOT a chat box — nine named fields with types and allowed values, which is the whole
  //    reason this use case was chosen as the second one.
  await page.screenshot({ path: path.join(OUT, 'extract-fields.png') })
  console.log('  wrote extract-fields.png')

  // 2. Press Extract with no key configured. A configuration state the page renders calmly, and
  //    the honest thing to publish as this kit's "failure" shot until a live run replaces it.
  const btn = await page.$('#go, button[type=submit], .go, button')
  if (btn) {
    await btn.click()
    // WAIT FOR THE TABLE, NOT FOR THE CLOCK. A fixed sleep either shoots an empty table or
    // wastes a minute; the live call took 4 seconds and the placeholder is a known string.
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#rows').textContent.includes('not extracted yet'),
        { timeout: 120000 })
      await sleep(400)
    } else {
      await sleep(1200)
    }
    await page.screenshot({ path: path.join(OUT, LIVE ? 'extract-answered.png' : 'extract-nokey.png') })
    console.log(`  wrote ${LIVE ? 'extract-answered.png' : 'extract-nokey.png'}`)
  } else {
    console.log('  !! no Extract control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
