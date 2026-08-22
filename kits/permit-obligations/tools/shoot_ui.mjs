// Screenshot the running kit UI, for the use-case standard's UI lens.
//
//   node tools/shoot_ui.mjs               # the two free shots
//   node tools/shoot_ui.mjs --live        # adds the read shot; SPENDS one call
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const HERE = path.dirname(path.dirname(new URL(import.meta.url).pathname))
const OUT = path.join(HERE, 'docs', 'shots')
const PORT = Number(process.env.PORT || 8953)
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
  // ⚠︎ TWO HEIGHTS, AND THE DIFFERENCE IS MEASURED RATHER THAN GUESSED. This kit's payoff is the
  // WORKLIST panel, which is one row per condition and a register carries up to seven of them,
  // each with a wrapped sentence of rulebook reasoning — so a read register is ~380px taller than
  // an unread one. Shooting both at the tall height leaves a 400px void under the empty-state
  // shot, which reads as a broken page; shooting both at the short one drops the escalation
  // panel, which is the single row a person acts on first, below the fold on the live shot.
  await page.setViewport({ width: 1280, height: LIVE ? 1400 : 1120, deviceScaleFactor: 2 })
  await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle0' })
  await sleep(600)

  if (LIVE) {
    // REG-0003 exercises every moving part at once: a dateless inspection entry (not_determinable,
    // and the site flags it `attention`), a SUPERSEDED reading carrying a stale date that would
    // compute as overdue (not_binding — a false alarm avoided), an annual report FILED LAST
    // NOVEMBER and credited to the 2023 reporting year (overdue since 2025-03-31, and the site
    // flags it `on track` — which is what raises the escalation), two financial assurances 49 and
    // 60 days out (due_in_window, because their window is 60 and every other type's is 30), and an
    // inspection 52 days out (not_yet_due, for exactly the opposite reason). Both directions of the
    // window trap, on one register.
    await page.select('#doc', 'REG-0003')
    await sleep(400)
  }

  await page.screenshot({ path: path.join(OUT, 'read-fields.png') })
  if (!LIVE) console.log('  wrote read-fields.png')

  const btn = await page.$('#go')
  if (btn) {
    await btn.click()
    if (LIVE) {
      await page.waitForFunction(
        () => !document.querySelector('#rows').textContent.includes('Nothing has been read yet'),
        { timeout: 180000 })
      await sleep(500)
    } else {
      await sleep(1500)
    }
    await page.screenshot({ path: path.join(OUT, LIVE ? 'read-answered.png' : 'read-nokey.png') })
    console.log(`  wrote ${LIVE ? 'read-answered.png' : 'read-nokey.png'}`)
  } else {
    console.log('  !! no Read control found — the UI changed; fix the selector above')
    process.exitCode = 1
  }
} finally {
  if (browser) await browser.close()
  server.kill()
}
