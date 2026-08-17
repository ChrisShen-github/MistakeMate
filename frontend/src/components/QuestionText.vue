<script setup lang="ts">
import { computed } from 'vue'

type TextBlock = { type: 'text'; lines: string[] }
type TableBlock = { type: 'table'; headers: string[]; rows: string[][] }

const props = defineProps<{ text: string }>()

function cells(line: string) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim().replace(/\\\|/g, '|'))
}

function isTableRow(line: string) { return /^\s*\|?.+\|.+\|?\s*$/.test(line) }
function isDivider(line: string) { return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line) }

function parseBlocks(text: string): Array<TextBlock | TableBlock> {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
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
        <p v-for="(line, lineIndex) in block.lines" :key="lineIndex">{{ line || ' ' }}</p>
      </div>
      <div v-else class="table-scroll" tabindex="0" aria-label="识别出的表格">
        <table>
          <thead><tr><th v-for="(header, headerIndex) in block.headers" :key="headerIndex">{{ header }}</th></tr></thead>
          <tbody><tr v-for="(row, rowIndex) in block.rows" :key="rowIndex"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.question-text { color: inherit; font: inherit; line-height: inherit; }
.text-block p { min-height: 1.55em; margin: 0; white-space: pre-wrap; }
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
