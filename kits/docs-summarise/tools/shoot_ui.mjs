// Screenshot the running kit UI, for the use-case standard's UI lens.
//
// ⚑ WHY THIS IS A SCRIPT AND NOT A MANUAL STEP. The UI lens asks for shots of the real app
// including one failure, and a screenshot taken by hand is a screenshot nobody can reproduce when
// the UI changes. Run this and the lens refills itself. Ported from kit #2's copy, which learned
// all of the notes below the expensive way.
//
// ⚠︎ IT NEVER SPENDS ON ITS OWN. Two of the three shots are free — the empty panel with the rubric
// showing before anything runs, and the calm no-key state. The third drives the real Summarise
// button and therefore costs one model call, so it only runs with --live.
//
//   node tools/shoot_ui.mjs               # the two free shots
//   node tools/shoot_ui.mjs --live        # adds the answered shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = 8898
const LIVE = process.argv.includes('--live')

function chromePath() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) return process.env.PUPPETEER_EXECUTABLE_PATH
  return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

mkdirSync(OUT, { recursive: true })

// THE SERVER IS STARTED WITHOUT A KEY UNLESS --live. src/config.py reads the environment, so
// blanking the variables gives the genuine no-key path rather than a mocked one — the same calm
// 200 the app returns, which is the state a reader is most likely to meet first.
const env = { ...process.env, PORT: String(PORT) }
if (!LIVE) { env.API_KEY = ''; env.LLM_API_KEY = ''; env.OPENAI_API_KEY = '' }

const server = spawn('python3', ['-m', 'src.app'], { cwd: HERE, env, stdio: 'ignore' })
process.on('exit', () => server.kill())

// ⚠︎ PUPPETEER IS NOT A DEPENDENCY OF THIS KIT AND MUST NOT BECOME ONE. A kit's promise is stdlib
// Python and a clone that runs in ten minutes; adding a browser to package.json to take
// screenshots would put a Chromium download in the path of everyone who only wants a brief. So
// the module is located by an explicit env var. ESM resolves relative to THIS FILE, not to cwd.
const PUP = process.env.PUPPETEER_MODULE || 'puppeteer'
let puppeteer
try {
  puppeteer = (await import(PUP)).default
} catch {
  console.error('  !! puppeteer not resolvable as %s.', PUP)
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
  await page.setViewport({ width: 1280, height: 860, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(800)

  // 1. The empty panel, before anything is asked of the model. THE RUBRIC IS ALREADY ON SCREEN,
  //    with its six sections and their weights — which is the shot that shows what this kit is:
  //    a reader learns what the brief will be graded ON before anything has run.
  await page.screenshot({ path: path.join(OUT, 'summarise-empty.png') })
  console.log('  wrote summarise-empty.png')

  // 2. Press Summarise with no key configured. A configuration state the page renders calmly —
  //    a plain sentence, not a stack trace and not a spinner that never resolves.
  const btn = await page.$('#go')
  if (btn) {
    await btn.click()
    // WAIT FOR THE PANEL, NOT FOR THE CLOCK. A fixed sleep either shoots an empty panel or wastes
    // a minute; the live call took about 9 seconds on the reasoning-off run.
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#k-state').textContent.includes('nothing has run'),
        { timeout: 180000 })
      await sleep(500)
    } else {
      await sleep(1400)
    }
    const name = LIVE ? 'summarise-answered.png' : 'summarise-nokey.png'
    await page.screenshot({ path: path.join(OUT, name) })
    console.log(`  wrote ${name}`)
  } else {
    console.log('  !! no Summarise control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
