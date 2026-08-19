<script setup lang="ts">
import { computed } from 'vue'
import katex from 'katex'
import 'katex/dist/katex.min.css'

type InlineToken = { type: 'text'; value: string } | { type: 'math'; html: string; display: boolean }
type TextBlock = { type: 'text'; lines: string[] }
type TableBlock = { type: 'table'; headers: string[]; rows: string[][] }

const props = defineProps<{ text: string }>()

function cells(line: string) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim().replace(/\\\|/g, '|'))
}

function isTableRow(line: string) { return /^\s*\|?.+\|.+\|?\s*$/.test(line) }
function isDivider(line: string) { return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line) }

function collapseDisplayMath(text: string) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const collapsed: string[] = []
  let pending: string[] | null = null
  for (const line of lines) {
    if (!pending && line.trim() === '\\[') { pending = [line]; continue }
    if (pending) {
      pending.push(line)
      if (line.trim() === '\\]') { collapsed.push(pending.join('\n')); pending = null }
      continue
    }
    collapsed.push(line)
  }
  if (pending) collapsed.push(...pending)
  return collapsed
}

function renderMath(source: string, display: boolean) {
  return katex.renderToString(source.trim(), { displayMode: display, throwOnError: false, strict: 'ignore', trust: false })
}

function inlineTokens(value: string): InlineToken[] {
  const tokens: InlineToken[] = []
  const mathPattern = /\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|\$\$([\s\S]*?)\$\$|\$([^$\n]+)\$/g
  let cursor = 0
  for (const match of value.matchAll(mathPattern)) {
    const start = match.index ?? 0
    if (start > cursor) tokens.push({ type: 'text', value: value.slice(cursor, start) })
    const source = match[1] ?? match[2] ?? match[3] ?? match[4] ?? ''
    tokens.push({ type: 'math', html: renderMath(source, Boolean(match[1] ?? match[3])), display: Boolean(match[1] ?? match[3]) })
    cursor = start + match[0].length
  }
  const rest = value.slice(cursor)
  if (rest || tokens.length === 0) {
    const looksLikeMath = /^\s*\\(?:frac|dfrac|min|max|left|right|sqrt|sum|prod|int|begin|mathrm|text)\b/.test(rest)
    tokens.push(looksLikeMath ? { type: 'math', html: renderMath(rest, true), display: true } : { type: 'text', value: rest })
  }
  return tokens
}

function parseBlocks(text: string): Array<TextBlock | TableBlock> {
  const lines = collapseDisplayMath(text)
  const blocks: Array<TextBlock | TableBlock> = []
  let pending: string[] = []
  const flushText = () => {
    if (pending.length) blocks.push({ type: 'text', lines: pending })
    pending = []
  }

  for (let index = 0; index < lines.length; index += 1) {
    if (isTableRow(lines[index]) && index + 1 < lines.length && isDivider(lines[index + 1])) {
      const headers = cells(lines[index])
      const rows: string[][] = []
      index += 2
      while (index < lines.length && isTableRow(lines[index]) && !isDivider(lines[index])) {
        const row = cells(lines[index])
        if (row.length === headers.length) rows.push(row)
        else break
        index += 1
      }
      index -= 1
      flushText()
      blocks.push({ type: 'table', headers, rows })
    } else {
      pending.push(lines[index])
    }
  }
  flushText()
  return blocks
}

const blocks = computed(() => parseBlocks(props.text))
const hasTable = computed(() => blocks.value.some((block) => block.type === 'table'))
</script>

<template>
  <div class="question-text" :class="{ 'has-table': hasTable }">
    <template v-for="(block, index) in blocks" :key="index">
      <div v-if="block.type === 'text'" class="text-block">
        <p v-for="(line, lineIndex) in block.lines" :key="lineIndex" :class="{ 'math-line': inlineTokens(line).some((token) => token.type === 'math' && token.display) }"><template v-for="(token, tokenIndex) in inlineTokens(line)" :key="tokenIndex"><span v-if="token.type === 'text'">{{ token.value || ' ' }}</span><span v-else class="math" :class="{ display: token.display }" v-html="token.html"></span></template></p>
      </div>
      <div v-else class="table-scroll" tabindex="0" aria-label="识别出的表格">
        <table>
          <thead><tr><th v-for="(header, headerIndex) in block.headers" :key="headerIndex"><template v-for="(token, tokenIndex) in inlineTokens(header)" :key="tokenIndex"><span v-if="token.type === 'text'">{{ token.value }}</span><span v-else class="math" v-html="token.html"></span></template></th></tr></thead>
          <tbody><tr v-for="(row, rowIndex) in block.rows" :key="rowIndex"><td v-for="(cell, cellIndex) in row" :key="cellIndex"><template v-for="(token, tokenIndex) in inlineTokens(cell)" :key="tokenIndex"><span v-if="token.type === 'text'">{{ token.value }}</span><span v-else class="math" v-html="token.html"></span></template></td></tr></tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.question-text { color: inherit; font: inherit; line-height: inherit; }
.text-block p { min-height: 1.55em; margin: 0; white-space: pre-wrap; }.text-block p.math-line { min-height: 0; margin: .34em 0; white-space: normal; }.math { display: inline; }.math.display { display: block; overflow-x: auto; padding: .08em 0; }
.table-scroll { max-width: 100%; margin: 9px 0; overflow-x: auto; border: 1px solid #c9d8e6; border-radius: 8px; background: #fff; }
.table-scroll:focus-visible { outline: 3px solid rgba(37,99,235,.18); outline-offset: 2px; }
table { width: 100%; min-width: max-content; border-collapse: collapse; color: #29435f; font: inherit; }
th,td { padding: 8px 11px; border-right: 1px solid #dce6ef; border-bottom: 1px solid #dce6ef; text-align: left; vertical-align: top; white-space: pre-wrap; }
th:last-child,td:last-child { border-right: 0; }
tbody tr:last-child td { border-bottom: 0; }
th { color: #2f5d91; background: #edf5ff; font-weight: 800; }
td { background: #fff; }
@media (max-width: 760px) { th,td { padding: 8px 10px; } }
</style>
