/* End-to-end walkthrough — artifact-driven Project workspace + Canvas / Decisions / Assets */
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

const onProject = async () => (await page.locator('text=Deliverables').count()) > 0
const ensureProject = async () => {
  if (!(await onProject())) {
    await page.click('a:has-text("Project")')
    await page.waitForTimeout(150)
  }
}
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

// 1. Initial — artifact-driven workspace (stage spine + deliverables + detail)
await page.goto(`${BASE}/#/`)
await page.waitForSelector('text=Deliverables')
await page.waitForTimeout(300)
await page.screenshot({ path: `${OUT}/01-project-initial.png` })

// 2. Collapse / expand the nav rail
await page.click('button[aria-label="Collapse navigation"]')
await page.waitForTimeout(300)
await page.screenshot({ path: `${OUT}/02-rail-collapsed.png` })
await page.click('button[aria-label="Expand navigation"]')
await page.waitForTimeout(300)

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

// 4. Run — first human touchpoint is the SOW upload (inline in the artifact detail)
await ensureProject()
await page.click('button:has-text("Run")')
let uploadShot = false
let decisionShot = false
let buildingShot = false
for (let i = 0; i < 460; i++) {
  if ((await page.locator('text=Project delivered').count()) > 0) break
  await ensureProject()

  const confirm = page.locator('button:has-text("Confirm choice"):not([disabled])').first()
  const hasUpload =
    (await page.getByRole('button', { name: 'Attach', exact: true }).count()) > 0 ||
    (await page.getByRole('button', { name: 'Download', exact: true }).count()) > 0

  if (!uploadShot && hasUpload) {
    await page.screenshot({ path: `${OUT}/04-needs-you-upload.png` })
    uploadShot = true
  }
  if (!decisionShot && (await confirm.count()) > 0) {
    await page.screenshot({ path: `${OUT}/05-decision-inline.png` })
    decisionShot = true
  }
  if (!buildingShot && i === 18) {
    await page.screenshot({ path: `${OUT}/06-building.png` })
    buildingShot = true
  }

  if ((await confirm.count()) > 0) {
    await confirm.click()
    await page.waitForTimeout(160)
    continue
  }
  if (hasUpload) {
    await attachOrDownloadAll()
    const submit = page
      .locator('button:has-text("Submit"):not([disabled]), button:has-text("Mark as sent"):not([disabled])')
      .first()
    if ((await submit.count()) > 0) {
      await submit.click()
      await page.waitForTimeout(160)
      continue
    }
  }
  await page.waitForTimeout(220)
}

// 7. Delivered state
await ensureProject()
await page.waitForTimeout(300)
await page.screenshot({ path: `${OUT}/07-project-delivered.png` })

// 8. Decisions inbox (full page)
await page.click('a:has-text("Decisions")')
await page.waitForTimeout(400)
await page.screenshot({ path: `${OUT}/08-decisions-inbox.png`, fullPage: true })

// 9. Assets library (list + detail)
await page.click('a:has-text("Assets")')
await page.waitForTimeout(300)
await page.getByText('Industry Knowledge', { exact: true }).click()
await page.waitForTimeout(300)
await page.screenshot({ path: `${OUT}/09-assets-library.png` })

// 10. Canvas node → lands on Project with that artifact focused (Process main + Canvas sidebar)
await page.click('a:has-text("Workflow Canvas")')
await page.waitForTimeout(500)
await page.locator('.react-flow__node', { hasText: 'Technical review' }).click()
await page.waitForSelector('text=Build process')
await page.waitForTimeout(300)
await page.screenshot({ path: `${OUT}/10-canvas-node-to-project.png` })

// 10b. Canvas sidebar chat — applies an edit to the document
const chatInput = page.getByPlaceholder('Ask AI to change this…')
await chatInput.fill('加一条校验：VIF 全部 < 5')
await chatInput.press('Enter')
await page.waitForTimeout(400)
await page.screenshot({ path: `${OUT}/10c-canvas-chat-edit.png` })

// 11. Knowledge still works
await page.click('a:has-text("Knowledge")')
await page.waitForSelector('text=What the team knows')
await page.screenshot({ path: `${OUT}/11-knowledge.png` })

// 12. Responsive
await page.setViewportSize({ width: 768, height: 1024 })
await page.goto(`${BASE}/#/`)
await page.waitForTimeout(600)
await page.screenshot({ path: `${OUT}/12-responsive-768.png` })

await browser.close()

if (errors.length) {
  console.log('RUNTIME ERRORS:')
  for (const e of errors) console.log(' -', e)
  process.exit(1)
}
console.log('VISUAL CHECK PASSED — screenshots in', OUT)
