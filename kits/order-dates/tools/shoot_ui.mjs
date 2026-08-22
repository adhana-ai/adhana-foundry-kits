// Screenshot the running kit UI, for the use-case standard's UI lens.
//
//   node tools/shoot_ui.mjs               # the two free shots
//   node tools/shoot_ui.mjs --live        # adds the answered shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8854)
const LIVE = process.argv.includes('--live')

function chromePath() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH) return process.env.PUPPETEER_EXECUTABLE_PATH
  return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

mkdirSync(OUT, { recursive: true })

const env = { ...process.env, PORT: String(PORT) }
if (!LIVE) { env.API_KEY = ''; env.LLM_API_KEY = ''; env.OPENAI_API_KEY = '' }

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
  console.error('     server it did not start may hold a real key — clicking would SPEND.')
  console.error(`     Free the port (lsof -nP -iTCP:${PORT} -sTCP:LISTEN) or set PORT= to a spare one.`)
  process.exit(4)
}

const server = spawn('python3', ['-m', 'src.app'], { cwd: HERE, env, stdio: 'ignore' })
process.on('exit', () => server.kill())

const PUP = process.env.PUPPETEER_MODULE || 'puppeteer'
let puppeteer
try {
  puppeteer = (await import(PUP)).default
} catch {
  console.error('  !! puppeteer not resolvable as %r.', PUP)
  console.error('     Set PUPPETEER_MODULE to an installed copy.')
  process.exit(2)
}
let browser
try {
  await sleep(1500)
  browser = await puppeteer.launch({ executablePath: chromePath(), args: ['--no-sandbox'] })
  const page = await browser.newPage()
  // ⚠︎ WIDER THAN THE SIBLING KIT THIS WAS FORKED FROM, AND CAPTURED fullPage. This kit's payoff
  // is a ROW PER OBLIGATION -- up to six of them, each carrying the model's own date, the pure-code
  // recomputation beside it and the working that produced it -- so the width is the constraint and
  // the height varies with the order. A FIXED height was tried first and it published a shot two
  // thirds empty on the no-key state and clipped the last obligation on the answered one; fullPage
  // measures what the eye actually sees rather than what the viewport was set to.
  await page.setViewport({ width: 1420, height: 900, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(600)

  await page.screenshot({ path: path.join(OUT, 'calendar-fields.png'), fullPage: true })
  console.log('  wrote calendar-fields.png')

  if (LIVE) {
    // ORD-0018 exercises every moving part at once, in six paragraphs:
    //   1  90 calendar days from the Order lands on a Sunday and ROLLS forward;
    //   2  a stated date, 3 October 2027, which is ALSO a Sunday and does NOT move;
    //   3  a period running from an event the Recorded Events table leaves "not recorded" --
    //      there is no date, and saying so is the answer;
    //   4  a WITHDRAWN paragraph that names an item, a number and a unit and sets no date, and
    //      names the SAME item paragraph 5 really does set;
    //   5  that real obligation, carrying a party's own calculation which is a month out;
    //   6  another calendar period that rolls off a Sunday.
    await page.select('#doc', 'ORD-0018')
    await sleep(300)
  }

  const btn = await page.$('#go, button[type=submit], .go, button')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#rows').textContent.includes('Nothing has been asked yet'),
        { timeout: 120000 })
      await sleep(400)
    } else {
      await sleep(1200)
    }
    await page.screenshot({ path: path.join(OUT, LIVE ? 'calendar-answered.png' : 'calendar-nokey.png'), fullPage: true })
    console.log(`  wrote ${LIVE ? 'calendar-answered.png' : 'calendar-nokey.png'}`)
  } else {
    console.log('  !! no Compute control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
