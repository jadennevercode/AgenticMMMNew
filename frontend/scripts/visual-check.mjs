/* End-to-end walkthrough — left collapsible rail + Canvas / Decisions / Assets destinations */
import { chromium } from 'playwright'
import { mkdirSync, rmSync } from 'node:fs'

const BASE = 'http://localhost:5199'
const OUT = 'screenshots'
rmSync(OUT, { recursive: true, force: true })
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(`console: ${m.text()}`)
})

const attachOrDownloadAll = async () => {
  for (let n = 0; n < 14; n++) {
    const a = page.getByRole('button', { name: 'Attach', exact: true }).first()
    const d = page.getByRole('button', { name: 'Download', exact: true }).first()
    if ((await a.count()) > 0) await a.click()
    else if ((await d.count()) > 0) await d.click()
    else break
    await page.waitForTimeout(110)
  }
}

// 1. Initial — left rail expanded
await page.goto(`${BASE}/#/`)
await page.waitForSelector('text=Your workbench')
await page.screenshot({ path: `${OUT}/01-rail-expanded.png` })

// 2. Collapse the rail
await page.click('button[aria-label="Collapse navigation"]')
await page.waitForTimeout(300)
await page.screenshot({ path: `${OUT}/02-rail-collapsed.png` })
await page.click('button[aria-label="Expand navigation"]')
await page.waitForTimeout(300)

// 2b. Assets — all deliverables shown grayed before the run
await page.click('a:has-text("Assets")')
await page.waitForTimeout(300)
await page.screenshot({ path: `${OUT}/02b-assets-grayed.png` })

// 3. Workflow Canvas — three views
await page.click('a:has-text("Workflow Canvas")')
await page.waitForSelector('.react-flow__node')
await page.waitForTimeout(500)
await page.screenshot({ path: `${OUT}/03-canvas-stage.png` })
await page.click('button:has-text("Agent")')
await page.waitForTimeout(500)
await page.screenshot({ path: `${OUT}/03b-canvas-agent.png` })
await page.click('button:has-text("Human · AI · Auto")')
await page.waitForTimeout(500)
await page.screenshot({ path: `${OUT}/03c-canvas-execution.png` })
await page.click('button:has-text("Stage")')
await page.waitForTimeout(300)

// 4. Run the project to advance the DAG
await page.click('button:has-text("Run")')
let modelShot = false
for (let i = 0; i < 420; i++) {
  // resolve human touchpoints regardless of which page we're on
  const confirm = page.locator('button:has-text("Confirm choice"):not([disabled])').first()
  if ((await confirm.count()) > 0) {
    if (!modelShot && (await page.locator('text=Pick the final model').count()) > 0) {
      await page.screenshot({ path: `${OUT}/05-decision-card.png` })
      modelShot = true
    }
    await confirm.click()
    await page.waitForTimeout(180)
    continue
  }
  if (
    (await page.getByRole('button', { name: 'Attach', exact: true }).count()) > 0 ||
    (await page.getByRole('button', { name: 'Download', exact: true }).count()) > 0
  ) {
    await attachOrDownloadAll()
    const submit = page
      .locator('button:has-text("Submit"):not([disabled]), button:has-text("Mark as sent"):not([disabled])')
      .first()
    if ((await submit.count()) > 0) {
      await submit.click()
      await page.waitForTimeout(180)
      continue
    }
  }
  // mid-run snapshot of the canvas
  if (i === 14) {
    await page.click('a:has-text("Workflow Canvas")')
    await page.waitForTimeout(400)
    await page.screenshot({ path: `${OUT}/04-canvas-running.png` })
  }
  // decisions/inputs only appear on Project workbench → hop there to act
  if ((await page.locator('text=Project delivered').count()) > 0) break
  const onProject = (await page.locator('text=Your workbench').count()) > 0
  if (!onProject && (await confirm.count()) === 0) {
    // go to Decisions inbox to clear, fall back to Project for inputs
    await page.click('a:has-text("Project")')
    await page.waitForTimeout(150)
    // jump to what needs you if a selection is holding focus
    const wny = page.locator('button:has-text("What needs you")').first()
    if ((await wny.count()) > 0) await wny.click()
  }
  await page.waitForTimeout(220)
}

// 6. Decisions inbox (full page)
await page.click('a:has-text("Decisions")')
await page.waitForSelector('text=Already decided', { timeout: 8000 }).catch(() => {})
await page.screenshot({ path: `${OUT}/06-decisions-inbox.png`, fullPage: true })

// 7. Assets library (full page, list + detail)
await page.click('a:has-text("Assets")')
await page.waitForTimeout(300)
await page.getByText('Project Knowledge Package', { exact: true }).click()
await page.waitForTimeout(300)
await page.screenshot({ path: `${OUT}/07-assets-library.png` })

// 8. Canvas final + click a node → lands on Project with it selected
await page.click('a:has-text("Workflow Canvas")')
await page.waitForTimeout(500)
await page.screenshot({ path: `${OUT}/08-canvas-final.png` })
await page.locator('.react-flow__node', { hasText: 'Technical review' }).click()
await page.waitForSelector('text=Your workbench')
await page.waitForTimeout(200)
await page.screenshot({ path: `${OUT}/09-canvas-node-to-project.png` })

// 9. Knowledge still works
await page.click('a:has-text("Knowledge")')
await page.waitForSelector('text=What the team knows')
await page.screenshot({ path: `${OUT}/10-knowledge.png` })

// 10. Responsive
await page.setViewportSize({ width: 768, height: 1024 })
await page.goto(`${BASE}/#/`)
await page.waitForTimeout(600)
await page.screenshot({ path: `${OUT}/11-responsive-768.png` })

await browser.close()

if (errors.length) {
  console.log('RUNTIME ERRORS:')
  for (const e of errors) console.log(' -', e)
  process.exit(1)
}
console.log('VISUAL CHECK PASSED — screenshots in', OUT)
