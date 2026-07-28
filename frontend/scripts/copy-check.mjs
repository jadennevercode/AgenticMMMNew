/**
 * UI copy check (decision D4, docs/agent-design/08 §7.3):
 * internal architecture terms must not appear in user-visible copy.
 * Scans string literals and JSX text in src/ — code identifiers are exempt.
 *
 * Usage: node scripts/copy-check.mjs
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = new URL('../src', import.meta.url).pathname

const BANNED = [
  'proposal',
  'gate',
  'insight engine',
  'automation class',
  'cognitive task',
  'mechanical task',
  'human-only',
  'context bus',
  'lineage',
  'dual-plane',
  'process plane',
  'collaboration plane',
  'deterministic engine',
  'copilot',
]

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) yield* walk(p)
    else if (/\.(ts|tsx)$/.test(name)) yield p
  }
}

/** Looks like prose meant for humans, not a code fragment */
function isProse(chunk) {
  if (!/[A-Za-z]{3}/.test(chunk)) return false
  if (!chunk.includes(' ')) return false
  return !/[=;{}()]|\?\.|&&|\|\|/.test(chunk)
}

/** Pull out string literals and JSX text nodes after stripping comments */
function extractCopy(source) {
  const stripped = source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
  const chunks = []
  const stringRe = /'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`/gs
  let m
  while ((m = stringRe.exec(stripped))) chunks.push(m[1] ?? m[2] ?? m[3] ?? '')
  const jsxTextRe = />([^<>{}]+)</g
  while ((m = jsxTextRe.exec(stripped))) chunks.push(m[1])
  return chunks.filter(isProse)
}

const TERM_RES = BANNED.map((t) => ({
  term: t,
  re: new RegExp(`\\b${t.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&')}\\b`, 'i'),
}))

let failures = 0
for (const file of walk(SRC)) {
  const rel = relative(SRC, file)
  // The banned list itself lives in ui-language.ts — skip its own definition
  if (rel.endsWith('ui-language.ts')) continue
  const source = readFileSync(file, 'utf8')
  for (const chunk of extractCopy(source)) {
    for (const { term, re } of TERM_RES) {
      if (re.test(chunk)) {
        failures += 1
        console.log(`✗ ${rel}: "${chunk.trim().slice(0, 80)}" contains banned term "${term}"`)
      }
    }
  }
}

if (failures) {
  console.log(`\n${failures} banned-term hit(s) in user-visible copy. Fix before shipping.`)
  process.exit(1)
}
console.log('✓ UI copy clean — no internal architecture terms in user-visible strings.')
