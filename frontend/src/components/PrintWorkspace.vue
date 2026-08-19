<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, type CSSProperties } from 'vue'
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Check,
  FileText,
  LayoutTemplate,
  LoaderCircle,
  Printer,
  RefreshCw,
  Save,
  Trash2,
} from '@lucide/vue'
import QuestionText from './QuestionText.vue'
import type { MistakeQuestion, QuestionPart } from '../types/questions'

type PrintableQuestion = MistakeQuestion & {
  batch_id: string
  subject: string
  source: string
  batch_created_at: string
  print_kind?: 'text' | 'clean_image'
  clean_image_file_id?: string | null
  clean_image_name?: string
}

type Orientation = 'portrait' | 'landscape'
type MobileStep = 'questions' | 'preview' | 'settings'
type MarginSettings = { top: number; right: number; bottom: number; left: number }
type PrintSettings = {
  paperId: string
  customWidth: number
  customHeight: number
  orientation: Orientation
  margins: MarginSettings
  columns: 1 | 2
  fontSize: number
  lineHeight: number
  questionGap: number
  defaultAnswerLines: number
  showAnswers: boolean
  showAnswerLines: boolean
  showHeader: boolean
  showFooter: boolean
  showQuestionDivider: boolean
  showQuestionNumbers: boolean
  showMeta: boolean
  showDifficulty: boolean
  showDate: boolean
  showScoreFields: boolean
  a4B5Imposition: boolean
  showCropMarks: boolean
  bindingMargin: number
  showBindingGuide: boolean
  title: string
  footer: string
}
type QuestionAdjustment = { answerLines: number; pageBreakBefore: boolean; partLines: Record<string, number> }
type PaperPreset = { id: string; label: string; width: number; height: number }
type TemplateDefinition = { id: string; name: string; description: string; settings: PrintSettings; custom?: boolean }
type StoredTemplate = { id: string; name: string; settings: Partial<PrintSettings>; created_at: string; updated_at: string }
type PlacedQuestion = { question: PrintableQuestion; number: number; oversized: boolean }
type PrintPage = { columns: PlacedQuestion[][] }

const emit = defineEmits<{ back: [] }>()
const props = withDefaults(defineProps<{ initialQuestionIds?: string[] }>(), { initialQuestionIds: () => [] })

const paperPresets: PaperPreset[] = [
  { id: 'A3', label: 'A3（297 × 420 mm）', width: 297, height: 420 },
  { id: 'A4', label: 'A4（210 × 297 mm）', width: 210, height: 297 },
  { id: 'A5', label: 'A5（148 × 210 mm）', width: 148, height: 210 },
  { id: 'A6', label: 'A6（105 × 148 mm）', width: 105, height: 148 },
  { id: 'B4', label: 'B4（250 × 353 mm）', width: 250, height: 353 },
  { id: 'B5', label: 'B5（176 × 250 mm）', width: 176, height: 250 },
  { id: 'JIS-B5', label: 'JIS B5（182 × 257 mm）', width: 182, height: 257 },
  { id: 'Letter', label: 'Letter（216 × 279 mm）', width: 216, height: 279 },
  { id: 'Legal', label: 'Legal（216 × 356 mm）', width: 216, height: 356 },
  { id: '16K', label: '16K（195 × 270 mm）', width: 195, height: 270 },
  { id: 'custom', label: '自定义尺寸', width: 210, height: 297 },
]

const standardSettings: PrintSettings = {
  paperId: 'A4', customWidth: 210, customHeight: 297, orientation: 'portrait',
  margins: { top: 12, right: 12, bottom: 10, left: 12 }, columns: 1,
  fontSize: 11, lineHeight: 1.75, questionGap: 5, defaultAnswerLines: 4,
  showAnswers: false, showAnswerLines: false, showHeader: true, showFooter: true,
  showQuestionDivider: true, showQuestionNumbers: true, showMeta: true, showDifficulty: true, showDate: false,
  showScoreFields: true, a4B5Imposition: false, showCropMarks: true,
  bindingMargin: 0, showBindingGuide: false,
  title: 'MistakeMate 错题练习', footer: '由 MistakeMate 整理',
}

function cloneSettings(value: Partial<PrintSettings>): PrintSettings {
  return {
    ...standardSettings,
    ...value,
    margins: { ...standardSettings.margins, ...(value.margins || {}) },
  }
}

const builtInTemplates: TemplateDefinition[] = [
  { id: 'standard', name: '标准练习', description: 'A4 单栏，适合日常重练', settings: cloneSettings(standardSettings) },
  { id: 'calculation', name: '计算题宽松', description: '大行距单栏，题面阅读更舒展', settings: cloneSettings({ ...standardSettings, questionGap: 7 }) },
  { id: 'compact', name: '省纸双栏', description: 'A4 双栏，适合短题与选择题', settings: cloneSettings({ ...standardSettings, columns: 2, fontSize: 9.5, lineHeight: 1.55, margins: { top: 10, right: 9, bottom: 9, left: 9 } }) },
  { id: 'large-text', name: '大字护眼', description: '大字号与宽行距，阅读更轻松', settings: cloneSettings({ ...standardSettings, fontSize: 13, lineHeight: 1.9 }) },
  { id: 'a5-booklet', name: 'A5 小册', description: '适合便携练习册与活页纸', settings: cloneSettings({ ...standardSettings, paperId: 'A5', fontSize: 10.5, margins: { top: 9, right: 9, bottom: 8, left: 9 } }) },
  { id: 'a4-cut-b5', name: 'A4 裁 B5', description: '右下裁切，左侧留 1cm 装订区', settings: cloneSettings({ ...standardSettings, a4B5Imposition: true, showCropMarks: true, bindingMargin: 10, showAnswerLines: false, margins: { top: 10, right: 10, bottom: 9, left: 10 } }) },
  { id: 'answer-sheet', name: '答案校对', description: '双栏紧凑展示已录答案', settings: cloneSettings({ ...standardSettings, columns: 2, fontSize: 9.5, lineHeight: 1.55, defaultAnswerLines: 0, showAnswers: true, showScoreFields: false }) },
]

const questions = ref<PrintableQuestion[]>([])
const selectedIds = ref<string[]>([])
const adjustments = ref<Record<string, QuestionAdjustment>>({})
const customTemplates = ref<StoredTemplate[]>([])
const settings = ref<PrintSettings>(cloneSettings(standardSettings))
const activeTemplateId = ref('standard')
const activeSubject = ref('全部学科')
const mobileStep = ref<MobileStep>('questions')
const isLoading = ref(true)
const isSavingTemplate = ref(false)
const showTemplateName = ref(false)
const templateName = ref('')
const errorMessage = ref('')
const noticeMessage = ref('')

const subjects = computed(() => ['全部学科', ...Array.from(new Set(questions.value.map((question) => question.subject)))])
const visibleQuestions = computed(() => activeSubject.value === '全部学科' ? questions.value : questions.value.filter((question) => question.subject === activeSubject.value))
const selectedQuestions = computed(() => {
  const lookup = new Map(questions.value.map((question) => [question.id, question]))
  return selectedIds.value.map((id) => lookup.get(id)).filter((question): question is PrintableQuestion => Boolean(question))
})
const allVisibleSelected = computed(() => visibleQuestions.value.length > 0 && visibleQuestions.value.every((question) => selectedIds.value.includes(question.id)))
const answerCount = computed(() => selectedQuestions.value.filter(hasAnswer).length)
const allTemplates = computed<TemplateDefinition[]>(() => [
  ...builtInTemplates,
  ...customTemplates.value.map((template) => ({ id: template.id, name: template.name, description: '我的自定义模板', settings: cloneSettings(template.settings), custom: true })),
])

const paperSize = computed(() => {
  if (settings.value.a4B5Imposition) return { width: 210, height: 297 }
  const preset = paperPresets.find((paper) => paper.id === settings.value.paperId) || paperPresets[1]
  const baseWidth = preset.id === 'custom' ? clamp(settings.value.customWidth, 80, 500) : preset.width
  const baseHeight = preset.id === 'custom' ? clamp(settings.value.customHeight, 80, 500) : preset.height
  return settings.value.orientation === 'landscape'
    ? { width: baseHeight, height: baseWidth }
    : { width: baseWidth, height: baseHeight }
})

const trimSize = computed(() => settings.value.a4B5Imposition ? { width: 176, height: 250 } : paperSize.value)
const extraBindingMargin = computed(() => settings.value.a4B5Imposition ? clamp(settings.value.bindingMargin, 0, 25) : 0)

const paperStyle = computed<CSSProperties>(() => ({
  '--paper-width': `${paperSize.value.width}mm`,
  '--paper-height': `${paperSize.value.height}mm`,
  '--trim-width': `${trimSize.value.width}mm`,
  '--trim-height': `${trimSize.value.height}mm`,
  '--margin-top': `${settings.value.margins.top}mm`,
  '--margin-right': `${settings.value.margins.right}mm`,
  '--margin-bottom': `${settings.value.margins.bottom}mm`,
  '--margin-left': `${settings.value.margins.left + extraBindingMargin.value}mm`,
  '--base-left-margin': `${settings.value.margins.left}mm`,
  '--binding-margin': `${extraBindingMargin.value}mm`,
  '--paper-font-size': `${settings.value.fontSize}pt`,
  '--paper-line-height': `${settings.value.lineHeight}`,
  '--question-gap': `${settings.value.questionGap}mm`,
  '--column-count': `${settings.value.columns}`,
}))

function clamp(value: number, min: number, max: number) {
  const safeValue = Number.isFinite(Number(value)) ? Number(value) : min
  return Math.min(max, Math.max(min, safeValue))
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric' }).format(new Date(value))
}

function figureUrl(question: PrintableQuestion, figureId: string) {
  return `/api/mistakes/${question.batch_id}/questions/${question.id}/figures/${figureId}`
}

function isCleanOriginal(question: PrintableQuestion) {
  return (question.print_kind === 'clean_image' && Boolean(question.clean_image_file_id)) || (question.is_image_only && Boolean(question.clean_source_file_id))
}

function cleanImageUrl(question: PrintableQuestion) {
  return `/api/mistakes/${question.batch_id}/files/${question.clean_image_file_id || question.clean_source_file_id}/clean-image`
}

function rootParts(question: PrintableQuestion) {
  return question.parts.filter((part) => !part.parent_id).sort((a, b) => a.position - b.position)
}

function childParts(question: PrintableQuestion, parentId: string) {
  return question.parts.filter((part) => part.parent_id === parentId).sort((a, b) => a.position - b.position)
}

function adjustmentFor(question: PrintableQuestion | string) {
  const id = typeof question === 'string' ? question : question.id
  if (!adjustments.value[id]) {
    const target = typeof question === 'string' ? questions.value.find((item) => item.id === id) : question
    adjustments.value[id] = {
      answerLines: settings.value.defaultAnswerLines,
      pageBreakBefore: false,
      partLines: Object.fromEntries((target?.parts || []).map((part) => [part.id, clamp(part.answer_lines || 3, 1, 16)])),
    }
  }
  return adjustments.value[id]
}

function questionAnswerLines(question: PrintableQuestion) {
  return clamp(adjustmentFor(question).answerLines, 0, 16)
}

function partAnswerLines(question: PrintableQuestion, part: QuestionPart) {
  return clamp(adjustmentFor(question).partLines[part.id] ?? part.answer_lines ?? 3, 1, 16)
}

function hasPartAnswer(part: QuestionPart) {
  return part.answers.some((answer) => answer.trim()) || Boolean(part.solution.trim())
}

function hasAnswer(question: PrintableQuestion) {
  if (isCleanOriginal(question)) return false
  return Boolean(question.correct_answer.trim() || question.explanation.trim() || question.parts.some(hasPartAnswer))
}

function toggleQuestion(question: PrintableQuestion) {
  if (selectedIds.value.includes(question.id)) selectedIds.value = selectedIds.value.filter((id) => id !== question.id)
  else {
    selectedIds.value.push(question.id)
    adjustmentFor(question)
  }
}

function toggleVisibleQuestions() {
  const visibleIds = visibleQuestions.value.map((question) => question.id)
  if (allVisibleSelected.value) selectedIds.value = selectedIds.value.filter((id) => !visibleIds.includes(id))
  else {
    for (const question of visibleQuestions.value) {
      if (!selectedIds.value.includes(question.id)) selectedIds.value.push(question.id)
      adjustmentFor(question)
    }
  }
}

function moveQuestion(id: string, direction: -1 | 1) {
  const currentIndex = selectedIds.value.indexOf(id)
  const nextIndex = currentIndex + direction
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= selectedIds.value.length) return
  const reordered = [...selectedIds.value]
  ;[reordered[currentIndex], reordered[nextIndex]] = [reordered[nextIndex], reordered[currentIndex]]
  selectedIds.value = reordered
}

function estimatedTextHeight(text: string, charactersPerLine: number) {
  const explicitLines = Math.max(1, text.split(/\r?\n/).length)
  const wrappedLines = Math.max(explicitLines, Math.ceil(Math.max(text.length, 1) / charactersPerLine))
  const tableRowCount = text.split(/\r?\n/).filter((line) => /^\s*\|?.+\|.+\|?\s*$/.test(line) && !/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)).length
  return (wrappedLines + tableRowCount * .8) * settings.value.fontSize * 0.3528 * settings.value.lineHeight
}

function estimateQuestionHeight(question: PrintableQuestion) {
  if (isCleanOriginal(question)) return Math.max(80, trimSize.value.height - settings.value.margins.top - settings.value.margins.bottom - 28)
  const contentWidth = Math.max(35, (trimSize.value.width - settings.value.margins.left - extraBindingMargin.value - settings.value.margins.right - (settings.value.columns - 1) * 7) / settings.value.columns)
  const charactersPerLine = Math.max(8, Math.floor(contentWidth / (settings.value.fontSize * 0.37)))
  let height = 9 + estimatedTextHeight(question.stem, charactersPerLine)
  if (settings.value.showMeta) height += 5
  if (question.options.length) height += question.options.reduce((total, option) => total + estimatedTextHeight(`${option.label}.${option.text}`, charactersPerLine / (settings.value.columns === 1 ? 2 : 1)), 0) + 3
  if (question.parts.length) {
    for (const part of question.parts) {
      height += estimatedTextHeight(`${part.label}${part.prompt}`, charactersPerLine) + 2
      if (part.part_type !== '题组说明') {
        height += settings.value.showAnswers
          ? estimatedTextHeight(`${part.answers.join('；')}${part.solution}`, charactersPerLine) + 5
          : settings.value.showAnswerLines ? partAnswerLines(question, part) * 7 : 0
      }
    }
  } else if (settings.value.showAnswers) height += estimatedTextHeight(`${question.correct_answer}${question.explanation}`, charactersPerLine) + 6
  else if (settings.value.showAnswerLines) height += questionAnswerLines(question) * 7
  return height + settings.value.questionGap
}

const pages = computed<PrintPage[]>(() => {
  if (!selectedQuestions.value.length) return []
  const headerHeight = settings.value.showHeader ? (settings.value.showScoreFields ? 29 : 20) : 0
  const footerHeight = settings.value.showFooter ? 9 : 0
  const availableHeight = Math.max(40, trimSize.value.height - settings.value.margins.top - settings.value.margins.bottom - headerHeight - footerHeight)
  const pageList: PrintPage[] = [{ columns: Array.from({ length: settings.value.columns }, () => []) }]
  let pageIndex = 0
  let columnIndex = 0
  let usedHeight = 0

  const createPage = () => {
    pageList.push({ columns: Array.from({ length: settings.value.columns }, () => []) })
    pageIndex += 1
    columnIndex = 0
    usedHeight = 0
  }
  const advanceColumn = () => {
    if (columnIndex < settings.value.columns - 1) {
      columnIndex += 1
      usedHeight = 0
    } else createPage()
  }

  selectedQuestions.value.forEach((question, index) => {
    const adjustment = adjustmentFor(question)
    let currentPageHasContent = pageList[pageIndex].columns.some((column) => column.length)
    if (isCleanOriginal(question) && currentPageHasContent) {
      createPage()
      currentPageHasContent = false
    }
    if (adjustment.pageBreakBefore && currentPageHasContent) createPage()
    const estimatedHeight = estimateQuestionHeight(question)
    if (usedHeight > 0 && usedHeight + estimatedHeight > availableHeight) advanceColumn()
    pageList[pageIndex].columns[columnIndex].push({ question, number: index + 1, oversized: estimatedHeight > availableHeight })
    usedHeight += estimatedHeight
    if (isCleanOriginal(question) && index < selectedQuestions.value.length - 1) createPage()
  })
  return pageList.filter((page) => page.columns.some((column) => column.length))
})

function applyTemplate(template: TemplateDefinition) {
  settings.value = cloneSettings(template.settings)
  if (settings.value.a4B5Imposition) {
    settings.value.paperId = 'A4'
    settings.value.orientation = 'portrait'
  }
  activeTemplateId.value = template.id
  noticeMessage.value = `已应用“${template.name}”`
  window.setTimeout(() => { noticeMessage.value = '' }, 1800)
}

function toggleA4B5Imposition() {
  if (!settings.value.a4B5Imposition) return
  settings.value.paperId = 'A4'
  settings.value.orientation = 'portrait'
  settings.value.showCropMarks = true
  if (settings.value.bindingMargin === 0) settings.value.bindingMargin = 10
}

async function loadData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [questionResponse, templateResponse] = await Promise.all([fetch('/api/print/questions'), fetch('/api/print/templates')])
    const questionPayload = await questionResponse.json().catch(() => ({ detail: '暂时无法读取可打印题目。' }))
    if (!questionResponse.ok) throw new Error(questionPayload.detail)
    questions.value = questionPayload
    const requestedIds = props.initialQuestionIds.filter((id) => questionPayload.some((question: PrintableQuestion) => question.id === id))
    selectedIds.value = requestedIds.length ? requestedIds : questionPayload.map((question: PrintableQuestion) => question.id)
    questionPayload.forEach((question: PrintableQuestion) => adjustmentFor(question))
    if (templateResponse.ok) customTemplates.value = await templateResponse.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '暂时无法读取可打印题目。'
  } finally {
    isLoading.value = false
  }
}

async function saveTemplate() {
  const name = templateName.value.trim()
  if (!name) {
    errorMessage.value = '请先填写模板名称。'
    return
  }
  isSavingTemplate.value = true
  errorMessage.value = ''
  try {
    const response = await fetch('/api/print/templates', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, settings: settings.value }),
    })
    const payload = await response.json().catch(() => ({ detail: '模板保存失败。' }))
    if (!response.ok) throw new Error(payload.detail)
    customTemplates.value.unshift(payload)
    activeTemplateId.value = payload.id
    templateName.value = ''
    showTemplateName.value = false
    noticeMessage.value = '模板已保存，下次打开仍可使用。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '模板保存失败。'
  } finally {
    isSavingTemplate.value = false
  }
}

async function deleteTemplate(template: TemplateDefinition) {
  if (!template.custom || !window.confirm(`确定删除“${template.name}”吗？`)) return
  try {
    const response = await fetch(`/api/print/templates/${template.id}`, { method: 'DELETE' })
    if (!response.ok) throw new Error('模板删除失败。')
    customTemplates.value = customTemplates.value.filter((item) => item.id !== template.id)
    if (activeTemplateId.value === template.id) applyTemplate(builtInTemplates[0])
    noticeMessage.value = '自定义模板已删除。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '模板删除失败。'
  }
}

function installPageStyle() {
  let style = document.querySelector<HTMLStyleElement>('#mistakemate-print-page')
  if (!style) {
    style = document.createElement('style')
    style.id = 'mistakemate-print-page'
    document.head.appendChild(style)
  }
  style.textContent = `@page { size: ${paperSize.value.width}mm ${paperSize.value.height}mm; margin: 0; }`
}

function printQuestions() {
  if (!selectedQuestions.value.length) {
    errorMessage.value = '请至少选择一道题再打印。'
    mobileStep.value = 'questions'
    return
  }
  errorMessage.value = ''
  installPageStyle()
  window.print()
}

onMounted(loadData)
onBeforeUnmount(() => document.querySelector('#mistakemate-print-page')?.remove())
</script>

<template>
  <section class="print-workspace" aria-labelledby="print-heading">
    <header class="studio-heading screen-only">
      <div>
        <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回</button>
        <p class="eyebrow">错题集打印</p>
        <h1 id="print-heading">打印模板</h1>
        <p>选择纸张和版式，预览会自动分页；打印窗口里也可以保存为 PDF。</p>
      </div>
      <div class="heading-actions">
        <button class="secondary-button" type="button" @click="showTemplateName = true"><Save :size="17" />另存为模板</button>
        <button class="print-button" type="button" :disabled="!selectedQuestions.length" @click="printQuestions"><Printer :size="18" />打印 {{ selectedQuestions.length }} 道题</button>
      </div>
    </header>

    <nav class="mobile-steps screen-only" aria-label="打印设置步骤">
      <button type="button" :class="{ active: mobileStep === 'questions' }" @click="mobileStep = 'questions'">1 题目</button>
      <button type="button" :class="{ active: mobileStep === 'settings' }" @click="mobileStep = 'settings'">2 模板</button>
      <button type="button" :class="{ active: mobileStep === 'preview' }" @click="mobileStep = 'preview'">3 预览</button>
    </nav>

    <div v-if="isLoading" class="state-card screen-only" aria-live="polite"><LoaderCircle class="spin" :size="22" />正在准备打印模板…</div>
    <div v-else-if="errorMessage && !questions.length" class="state-card error screen-only" role="alert"><RefreshCw :size="21" /><div><strong>读取失败</strong><p>{{ errorMessage }}</p></div><button type="button" @click="loadData">重试</button></div>
    <div v-else-if="!questions.length" class="state-card empty screen-only"><FileText :size="28" /><strong>还没有可打印的内容</strong><p>先确认 OCR 题目，或在清洁原图核对后点击“确认此清洁图可用”。</p><button type="button" @click="emit('back')">返回我的错题</button></div>

    <div v-else class="studio-grid">
      <aside class="studio-panel questions-panel screen-only" :class="{ 'mobile-visible': mobileStep === 'questions' }" aria-label="选择题目">
        <div class="panel-heading"><div><span>题目</span><h2>选择与排序</h2></div><strong>{{ selectedIds.length }} / {{ questions.length }}</strong></div>
        <div class="subject-filters" aria-label="按学科筛选">
          <button v-for="subject in subjects" :key="subject" type="button" :class="{ active: activeSubject === subject }" :aria-pressed="activeSubject === subject" @click="activeSubject = subject">{{ subject }}</button>
        </div>
        <button class="select-all" type="button" @click="toggleVisibleQuestions"><Check :size="17" />{{ allVisibleSelected ? '取消当前学科' : '全选当前学科' }}</button>

        <div class="question-editor-list">
          <article v-for="question in visibleQuestions" :key="question.id" class="question-editor" :class="{ selected: selectedIds.includes(question.id) }">
            <label class="question-check">
              <input type="checkbox" :checked="selectedIds.includes(question.id)" @change="toggleQuestion(question)" />
              <span><strong>{{ question.subject }} · {{ isCleanOriginal(question) ? '清洁原图' : question.source }}</strong><small>{{ isCleanOriginal(question) ? (question.clean_image_name || '已确认的清洁原图') : question.stem }}</small></span>
            </label>
            <div v-if="selectedIds.includes(question.id)" class="question-tools">
              <div class="tool-row">
                <span>顺序</span>
                <button type="button" title="上移" aria-label="上移题目" :disabled="selectedIds.indexOf(question.id) === 0" @click="moveQuestion(question.id, -1)"><ArrowUp :size="15" /></button>
                <button type="button" title="下移" aria-label="下移题目" :disabled="selectedIds.indexOf(question.id) === selectedIds.length - 1" @click="moveQuestion(question.id, 1)"><ArrowDown :size="15" /></button>
                <label class="break-toggle"><input v-model="adjustmentFor(question).pageBreakBefore" type="checkbox" />题前分页</label>
              </div>
            </div>
          </article>
        </div>
      </aside>

      <main class="preview-panel" :class="{ 'mobile-visible': mobileStep === 'preview' }" aria-label="打印分页预览">
        <div class="preview-toolbar screen-only">
          <div><strong>{{ settings.a4B5Imposition ? 'A4 承印 / B5 成品' : paperPresets.find((paper) => paper.id === settings.paperId)?.label.split('（')[0] }}</strong><span>{{ settings.a4B5Imposition ? '靠左上裁切' : (settings.orientation === 'portrait' ? '竖版' : '横版') }} · {{ settings.columns }} 栏 · {{ pages.length }} 页</span></div>
          <span class="zoom-note">预览按真实纸张比例显示</span>
        </div>
        <div v-if="!selectedQuestions.length" class="preview-empty screen-only"><FileText :size="27" /><strong>请选择要打印的题目</strong><p>选择后会立即生成分页预览。</p></div>
        <div v-else class="page-stage">
          <div class="page-stack" :style="paperStyle">
            <article v-for="(page, pageIndex) in pages" :key="pageIndex" class="paper-sheet" :class="{ imposed: settings.a4B5Imposition }">
              <div class="trim-area">
                <header v-if="settings.showHeader" class="paper-heading">
                  <div><span>MistakeMate</span><h2>{{ settings.title || '错题练习' }}</h2></div>
                  <strong>{{ settings.showAnswers ? '含答案版' : '练习版' }}</strong>
                  <template v-if="settings.showScoreFields"><p>姓名：<i></i></p><p>日期：<i></i></p><p>得分：<i></i></p></template>
                </header>

                <div class="paper-body">
                  <div v-for="(column, columnIndex) in page.columns" :key="columnIndex" class="paper-column">
                    <section v-for="item in column" :key="item.question.id" class="print-question" :class="{ oversized: item.oversized, 'clean-original': isCleanOriginal(item.question), 'without-divider': !settings.showQuestionDivider, 'without-number': !settings.showQuestionNumbers }">
                    <div v-if="settings.showQuestionNumbers" class="question-number">{{ item.number }}</div>
                    <div class="question-content">
                      <div v-if="settings.showMeta" class="question-meta">
                        <span>{{ item.question.subject }}</span><span>{{ item.question.question_type }}</span>
                        <span v-if="settings.showDifficulty && !isCleanOriginal(item.question)">难度 {{ '★'.repeat(item.question.difficulty) }}</span>
                        <span v-if="settings.showDate">{{ formatDate(item.question.batch_created_at) }}</span>
                      </div>
                      <img v-if="isCleanOriginal(item.question)" class="print-clean-image" :src="cleanImageUrl(item.question)" :alt="`清洁原图：${item.question.clean_image_name}`" />
                      <template v-else>
                      <QuestionText class="question-stem" :text="item.question.stem" />
                      <div v-if="item.question.figures.length" class="question-figures"><img v-for="figure in item.question.figures" :key="figure.id" :src="figureUrl(item.question, figure.id)" alt="题目图形" /></div>
                      <ol v-if="item.question.options.length" class="option-list">
                        <li v-for="option in item.question.options" :key="option.label"><strong>{{ option.label }}.</strong>{{ option.text }}</li>
                      </ol>

                      <div v-if="item.question.parts.length" class="part-list">
                        <section v-for="part in rootParts(item.question)" :key="part.id" class="question-part">
                          <p><strong>{{ part.label }}</strong>{{ part.prompt }}</p>
                          <template v-if="part.part_type !== '题组说明'">
                            <div v-if="settings.showAnswers" class="printed-answer"><strong>答案</strong><span>{{ part.answers.filter(Boolean).join('；') || '暂未录入' }}</span><p v-if="part.solution">{{ part.solution }}</p></div>
                            <div v-else-if="settings.showAnswerLines" class="answer-lines"><span v-for="line in partAnswerLines(item.question, part)" :key="line"></span></div>
                          </template>
                          <section v-for="child in childParts(item.question, part.id)" :key="child.id" class="question-part child">
                            <p><strong>{{ child.label }}</strong>{{ child.prompt }}</p>
                            <div v-if="settings.showAnswers" class="printed-answer"><strong>答案</strong><span>{{ child.answers.filter(Boolean).join('；') || '暂未录入' }}</span><p v-if="child.solution">{{ child.solution }}</p></div>
                            <div v-else-if="settings.showAnswerLines" class="answer-lines"><span v-for="line in partAnswerLines(item.question, child)" :key="line"></span></div>
                          </section>
                        </section>
                      </div>
                      <div v-else-if="settings.showAnswers" class="printed-answer"><strong>答案</strong><span>{{ item.question.correct_answer || '暂未录入' }}</span><p v-if="item.question.explanation">{{ item.question.explanation }}</p></div>
                      <div v-else-if="settings.showAnswerLines" class="answer-lines"><span v-for="line in questionAnswerLines(item.question)" :key="line"></span></div>
                      </template>
                      <p v-if="item.oversized && !isCleanOriginal(item.question)" class="overflow-warning screen-only">本题超过单页高度，请减少字号、题间距或页边距。</p>
                    </div>
                    </section>
                  </div>
                </div>
                <footer v-if="settings.showFooter" class="paper-footer"><span>{{ settings.footer }}</span><span>第 {{ pageIndex + 1 }} / {{ pages.length }} 页</span></footer>
              </div>
              <template v-if="settings.a4B5Imposition && settings.showCropMarks"><span class="crop-line crop-right" aria-hidden="true"></span><span class="crop-line crop-bottom" aria-hidden="true"></span><span class="crop-label crop-label-right screen-only">裁切</span><span class="crop-label crop-label-bottom screen-only">裁切</span></template>
              <span v-if="settings.a4B5Imposition && settings.showBindingGuide && settings.bindingMargin > 0" class="binding-guide" aria-hidden="true"></span>
            </article>
          </div>
        </div>
      </main>

      <aside class="studio-panel settings-panel screen-only" :class="{ 'mobile-visible': mobileStep === 'settings' }" aria-label="模板和版式设置">
        <div class="panel-heading"><div><span>模板</span><h2>纸张与版式</h2></div><LayoutTemplate :size="19" /></div>
        <section class="template-section">
          <h3>快速模板</h3>
          <div class="template-grid">
            <div v-for="template in allTemplates" :key="template.id" class="template-item">
              <button type="button" class="template-card" :class="{ active: activeTemplateId === template.id }" @click="applyTemplate(template)">
                <span><strong>{{ template.name }}</strong><small>{{ template.description }}</small></span>
                <Check v-if="activeTemplateId === template.id" :size="16" />
              </button>
              <button v-if="template.custom" class="template-delete" type="button" :aria-label="`删除模板：${template.name}`" @click="deleteTemplate(template)"><Trash2 :size="14" /></button>
            </div>
          </div>
        </section>

        <details open>
          <summary>纸张</summary>
          <div class="settings-body">
            <label>纸张大小<select v-model="settings.paperId" :disabled="settings.a4B5Imposition"><option v-for="paper in paperPresets" :key="paper.id" :value="paper.id">{{ paper.label }}</option></select></label>
            <div v-if="settings.paperId === 'custom'" class="two-fields"><label>宽度 mm<input v-model.number="settings.customWidth" type="number" min="80" max="500" /></label><label>高度 mm<input v-model.number="settings.customHeight" type="number" min="80" max="500" /></label></div>
            <fieldset :disabled="settings.a4B5Imposition"><legend>方向</legend><label><input v-model="settings.orientation" type="radio" value="portrait" />竖版</label><label><input v-model="settings.orientation" type="radio" value="landscape" />横版</label></fieldset>
            <div class="margin-grid"><label>上边距<input v-model.number="settings.margins.top" type="number" min="5" max="40" /></label><label>右边距<input v-model.number="settings.margins.right" type="number" min="5" max="40" /></label><label>下边距<input v-model.number="settings.margins.bottom" type="number" min="5" max="40" /></label><label>左边距<input v-model.number="settings.margins.left" type="number" min="5" max="40" /></label></div>
          </div>
        </details>

        <details>
          <summary>裁切与装订（高级）</summary>
          <div class="settings-body checkbox-list">
            <label><input v-model="settings.a4B5Imposition" type="checkbox" @change="toggleA4B5Imposition" />A4 纸上排 B5 成品</label>
            <p class="setting-helper">B5 靠左上排版，右侧留 34mm、下方留 47mm 作为裁切区域。</p>
            <template v-if="settings.a4B5Imposition">
              <label><input v-model="settings.showCropMarks" type="checkbox" />显示右侧和下方裁切线</label>
              <label class="number-with-unit">额外装订留白<span><input v-model.number="settings.bindingMargin" type="number" min="0" max="25" />mm</span></label>
              <label><input v-model="settings.showBindingGuide" type="checkbox" />显示装订区参考线</label>
              <p class="setting-helper">装订留白会加在原左边距内侧；默认 10mm，裁掉右下余纸后不影响装订。</p>
            </template>
          </div>
        </details>

        <details open>
          <summary>内容版式</summary>
          <div class="settings-body">
            <label>标题<input v-model="settings.title" maxlength="60" /></label>
            <label>页脚<input v-model="settings.footer" maxlength="60" /></label>
            <fieldset><legend>打印版本</legend><label><input v-model="settings.showAnswers" type="radio" :value="false" />练习版</label><label><input v-model="settings.showAnswers" type="radio" :value="true" />含答案版</label></fieldset>
            <p v-if="settings.showAnswers" class="answer-note">已选题目中 {{ answerCount }} 道录有答案；没有答案的题目会标注“暂未录入”。</p>
            <fieldset><legend>分栏</legend><label><input v-model="settings.columns" type="radio" :value="1" />单栏</label><label><input v-model="settings.columns" type="radio" :value="2" />双栏</label></fieldset>
            <label>题目字号 <output>{{ settings.fontSize }} pt</output><input v-model.number="settings.fontSize" type="range" min="8" max="15" step="0.5" /></label>
            <label>行距 <output>{{ settings.lineHeight }}</output><input v-model.number="settings.lineHeight" type="range" min="1.3" max="2.2" step="0.05" /></label>
            <label>题间距 <output>{{ settings.questionGap }} mm</output><input v-model.number="settings.questionGap" type="range" min="2" max="12" step="1" /></label>
          </div>
        </details>

        <details>
          <summary>显示或隐藏</summary>
          <div class="settings-body checkbox-list">
            <label><input v-model="settings.showHeader" type="checkbox" />页眉和标题</label>
            <label><input v-model="settings.showScoreFields" type="checkbox" :disabled="!settings.showHeader" />姓名、日期和得分栏</label>
            <label><input v-model="settings.showFooter" type="checkbox" />页脚和页码</label>
            <label><input v-model="settings.showAnswerLines" type="checkbox" :disabled="settings.showAnswers" />答题横线</label>
            <label><input v-model="settings.showQuestionDivider" type="checkbox" />题目分隔线</label>
            <label><input v-model="settings.showQuestionNumbers" type="checkbox" />题号圆标</label>
            <label><input v-model="settings.showMeta" type="checkbox" />学科和题型</label>
            <label><input v-model="settings.showDifficulty" type="checkbox" :disabled="!settings.showMeta" />难度星级</label>
            <label><input v-model="settings.showDate" type="checkbox" :disabled="!settings.showMeta" />收录日期</label>
          </div>
        </details>

        <div v-if="showTemplateName" class="save-template-box">
          <label>新模板名称<input v-model="templateName" maxlength="80" placeholder="例如：数学周末练习" @keyup.enter="saveTemplate" /></label>
          <div><button type="button" @click="showTemplateName = false">取消</button><button class="primary-small" type="button" :disabled="isSavingTemplate" @click="saveTemplate">{{ isSavingTemplate ? '保存中…' : '保存模板' }}</button></div>
        </div>
        <button v-else class="save-template-button" type="button" @click="showTemplateName = true"><Save :size="16" />将当前设置保存为模板</button>
        <p v-if="noticeMessage" class="notice-message" aria-live="polite"><Check :size="16" />{{ noticeMessage }}</p>
        <p v-if="errorMessage" class="inline-error" role="alert">{{ errorMessage }}</p>
      </aside>
    </div>

    <div v-if="questions.length" class="mobile-bottom-bar screen-only">
      <span>{{ selectedQuestions.length }} 道 · {{ pages.length }} 页</span>
      <button type="button" :disabled="!selectedQuestions.length" @click="printQuestions"><Printer :size="17" />打印</button>
    </div>
  </section>
</template>

<style scoped>
.print-workspace{max-width:1600px;margin:0 auto;padding:26px 30px 60px;color:#29435f}.studio-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:24px}.back-button{display:inline-flex;min-height:44px;align-items:center;gap:6px;margin:0 0 10px;padding:0;color:#315f9b;border:0;background:transparent;font-weight:700;cursor:pointer}.eyebrow{margin:0 0 5px;color:#7189a3;font-size:12px;font-weight:700;letter-spacing:.4px}.studio-heading h1{margin:0;color:#1e3553;font-size:30px;letter-spacing:-.6px}.studio-heading p:last-child{margin:7px 0 0;color:#667f98;font-size:13px}.heading-actions{display:flex;gap:9px}.print-button,.secondary-button,.mobile-bottom-bar button{display:inline-flex;min-height:44px;align-items:center;justify-content:center;gap:7px;padding:10px 15px;border-radius:9px;font-size:13px;font-weight:700;cursor:pointer}.print-button,.mobile-bottom-bar button{color:#fff;border:0;background:#f97316}.print-button:disabled,.mobile-bottom-bar button:disabled{cursor:not-allowed;opacity:.45}.secondary-button{color:#315f9b;border:1px solid #bfd0e4;background:#fff}.studio-grid{display:grid;grid-template-columns:220px minmax(390px,1fr) 250px;gap:12px;margin-top:20px;align-items:start}.studio-panel{border:1px solid #dce5ef;border-radius:12px;background:#fff}.questions-panel,.settings-panel{position:sticky;top:16px;max-height:calc(100vh - 32px);overflow:auto}.panel-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:15px 15px 12px;border-bottom:1px solid #e5ebf1}.panel-heading>div{display:flex;align-items:center;gap:7px}.panel-heading span{padding:3px 6px;color:#2862b9;border-radius:5px;background:#eaf3ff;font-size:10px;font-weight:800}.panel-heading h2{margin:0;color:#29435f;font-size:15px}.panel-heading>strong{color:#6a8096;font-size:11px}.subject-filters{display:flex;flex-wrap:wrap;gap:6px;padding:12px 12px 5px}.subject-filters button{min-height:40px;padding:7px 9px;color:#536d89;border:1px solid #d2dfea;border-radius:8px;background:#fff;font-size:11px;font-weight:700;cursor:pointer}.subject-filters button.active{color:#fff;border-color:#2868cc;background:#2868cc}.select-all{display:flex;width:calc(100% - 24px);min-height:42px;align-items:center;justify-content:center;gap:6px;margin:5px 12px 10px;color:#315f9b;border:1px solid #b9d0ef;border-radius:8px;background:#f8fbff;font-size:12px;font-weight:700;cursor:pointer}.question-editor-list{display:grid;gap:8px;padding:0 10px 12px}.question-editor{border:1px solid #e0e8f0;border-radius:9px;background:#fff}.question-editor.selected{border-color:#a6c5eb;background:#f8fbff}.question-check{display:grid;grid-template-columns:22px minmax(0,1fr);gap:8px;min-height:60px;align-items:center;padding:9px;cursor:pointer}.question-check input{width:18px;height:18px;accent-color:#2868cc}.question-check>span{display:grid;gap:3px;min-width:0}.question-check strong{color:#36516e;font-size:11px}.question-check small{overflow:hidden;color:#6f8398;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.question-tools{display:grid;gap:5px;padding:7px;border-top:1px solid #dce8f4;background:#fff}.tool-row{display:flex;min-height:34px;align-items:center;gap:5px}.tool-row>span{flex:1;overflow:hidden;color:#61778e;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.tool-row button{display:grid;width:32px;height:32px;place-items:center;padding:0;color:#40668f;border:1px solid #cedcea;border-radius:7px;background:#fff;cursor:pointer}.tool-row button:disabled{opacity:.35}.tool-row b{min-width:19px;color:#29435f;text-align:center;font-size:11px}.break-toggle{display:flex!important;min-height:32px!important;align-items:center;gap:4px;color:#667e96;font-size:10px}.break-toggle input{width:15px;height:15px}.part-space-list{display:grid;gap:2px;padding-top:4px;border-top:1px dashed #d7e1eb}.preview-panel{min-width:0;border:1px solid #d8e1ea;border-radius:12px;background:#e7ebef}.preview-toolbar{display:flex;min-height:52px;align-items:center;justify-content:space-between;gap:14px;padding:9px 15px;border-bottom:1px solid #d4dde6;background:#f8fafc;border-radius:12px 12px 0 0}.preview-toolbar>div{display:grid;gap:2px}.preview-toolbar strong{font-size:13px}.preview-toolbar span{color:#74879a;font-size:10px}.zoom-note{white-space:nowrap}.page-stage{max-height:calc(100vh - 130px);padding:22px;overflow:auto}.page-stack{display:grid;gap:20px;width:max-content;min-width:100%;justify-items:center}.paper-sheet{box-sizing:border-box;display:grid;grid-template-rows:auto 1fr auto;width:var(--paper-width);height:var(--paper-height);padding:var(--margin-top) var(--margin-right) var(--margin-bottom) var(--margin-left);overflow:hidden;color:#1f2937;background:#fff;box-shadow:0 5px 20px rgba(30,48,70,.16);font-family:'Noto Sans SC','Microsoft YaHei',sans-serif}.paper-heading{display:grid;grid-template-columns:1fr auto;gap:3mm 5mm;padding-bottom:4mm;border-bottom:1.2px solid #1f2937}.paper-heading>div span{color:#5f6b78;font-size:8pt;font-weight:700;letter-spacing:.4pt}.paper-heading h2{margin:.6mm 0 0;font-size:16pt}.paper-heading>strong{align-self:center;padding:1.5mm 2.5mm;border:1px solid #5b6570;font-size:8.5pt}.paper-heading>p{display:flex;align-items:flex-end;gap:1.5mm;margin:1mm 0 0;font-size:8.5pt}.paper-heading>p i{display:block;width:25mm;border-bottom:1px solid #69717a}.paper-heading>p:last-of-type i{width:16mm}.paper-body{display:grid;grid-template-columns:repeat(var(--column-count),minmax(0,1fr));gap:7mm;min-height:0;padding-top:2mm}.paper-column{min-width:0}.print-question{display:grid;grid-template-columns:6mm minmax(0,1fr);gap:2mm;padding:var(--question-gap) 0;border-bottom:1px dashed #afb6be;break-inside:avoid}.question-number{display:grid;width:5mm;height:5mm;place-items:center;color:#fff;border-radius:50%;background:#222;font-size:7.5pt;font-weight:700}.question-meta{display:flex;flex-wrap:wrap;gap:1.5mm;margin-bottom:2mm;color:#606a75;font-size:7.5pt}.question-meta span+span::before{content:'·';margin-right:1.5mm}.question-stem,.question-part>p{margin:0;font-size:var(--paper-font-size);line-height:var(--paper-line-height);white-space:pre-wrap}.option-list{display:grid;grid-template-columns:repeat(var(--column-count),1fr);gap:1.5mm 5mm;margin:3mm 0 0;padding:0;list-style:none;font-size:calc(var(--paper-font-size) - .5pt);line-height:var(--paper-line-height)}.option-list strong{margin-right:1.5mm}.part-list{display:grid;gap:3mm;margin-top:3mm}.question-part.child{margin:3mm 0 0 4mm}.question-part>p strong{margin-right:1.5mm}.answer-lines{display:grid;margin-top:1mm}.answer-lines span{display:block;height:7mm;border-bottom:1px solid #bcc2c9}.printed-answer{margin-top:2mm;padding:2.5mm;border-left:2px solid #4b5563;background:#f4f5f6;font-size:calc(var(--paper-font-size) - 1pt);line-height:1.6;break-inside:avoid}.printed-answer strong{margin-right:2mm}.printed-answer p{margin:1.5mm 0 0;white-space:pre-wrap}.overflow-warning{margin:2mm 0 0;padding:2mm;color:#a14820;border-radius:4px;background:#fff0e5;font-size:8pt}.paper-footer{display:flex;justify-content:space-between;gap:8mm;padding-top:3mm;color:#6b7280;border-top:1px solid #e0e2e5;font-size:7.5pt}.preview-empty{display:grid;min-height:600px;place-items:center;align-content:center;color:#73879b;text-align:center}.preview-empty strong{margin-top:9px;color:#38516e}.preview-empty p{margin:5px 0 0;font-size:12px}.settings-panel{padding-bottom:12px}.template-section{padding:12px}.template-section h3{margin:0 0 8px;color:#60778f;font-size:11px}.template-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}.template-item{position:relative;min-width:0}.template-card{display:flex;width:100%;min-height:63px;align-items:flex-start;justify-content:space-between;gap:5px;padding:8px;text-align:left;border:1px solid #dce5ef;border-radius:8px;background:#fff;cursor:pointer}.template-item:has(.template-delete) .template-card{padding-right:33px}.template-card.active{border-color:#5990d4;background:#f1f7ff;box-shadow:inset 0 0 0 1px #5990d4}.template-card>span{display:grid;gap:3px;min-width:0}.template-card strong{color:#35506c;font-size:11px}.template-card small{color:#7a8ea2;font-size:9px;line-height:1.35}.template-card>svg{flex:0 0 auto;color:#3473c5}.template-delete{position:absolute;top:5px;right:5px;display:grid;width:28px;height:28px;place-items:center;padding:0;color:#778b9f;border:0;border-radius:6px;background:transparent;cursor:pointer}.template-delete:hover{color:#bd4b3d;background:#fff0ed}.settings-panel details{border-top:1px solid #e3e9ef}.settings-panel summary{min-height:44px;padding:13px 14px;color:#3d5874;font-size:12px;font-weight:800;cursor:pointer}.settings-body{display:grid;gap:11px;padding:0 14px 14px}.settings-body>label,.two-fields label,.margin-grid label,.save-template-box label{display:grid;gap:5px;color:#5c7289;font-size:10px;font-weight:700}.settings-body input:not([type=radio]):not([type=checkbox]):not([type=range]),.settings-body select,.save-template-box input{box-sizing:border-box;width:100%;min-height:40px;padding:7px 9px;color:#29435f;border:1px solid #cad7e4;border-radius:7px;background:#fff;font:inherit;font-size:12px}.settings-body fieldset{display:flex;flex-wrap:wrap;gap:6px 14px;margin:0;padding:0;border:0}.settings-body legend{width:100%;margin-bottom:3px;color:#5c7289;font-size:10px;font-weight:700}.settings-body fieldset label,.checkbox-list label{display:flex;min-height:40px;align-items:center;gap:6px;color:#4f6881;font-size:11px}.settings-body input[type=radio],.settings-body input[type=checkbox]{width:17px;height:17px;accent-color:#2868cc}.settings-body input[type=range]{width:100%;accent-color:#2868cc}.settings-body output{float:right;color:#2862b9}.two-fields,.margin-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}.answer-note{margin:0;padding:8px;color:#64798e;border-radius:7px;background:#f5f8fb;font-size:10px;line-height:1.5}.save-template-button{display:flex;width:calc(100% - 24px);min-height:42px;align-items:center;justify-content:center;gap:6px;margin:12px;color:#315f9b;border:1px solid #bdd0e6;border-radius:8px;background:#f8fbff;font-size:11px;font-weight:700;cursor:pointer}.save-template-box{margin:12px;padding:10px;border:1px solid #bfd3e9;border-radius:9px;background:#f8fbff}.save-template-box>div{display:flex;justify-content:flex-end;gap:6px;margin-top:8px}.save-template-box button{min-height:38px;padding:7px 10px;color:#506a84;border:1px solid #cedae6;border-radius:7px;background:#fff;font-size:11px;font-weight:700}.save-template-box .primary-small{color:#fff;border-color:#2868cc;background:#2868cc}.notice-message,.inline-error{display:flex;align-items:flex-start;gap:5px;margin:8px 12px 0;padding:9px;border-radius:7px;font-size:10px;line-height:1.5}.notice-message{color:#24744d;background:#eaf8f0}.inline-error{color:#a7483b;background:#fff0ed}.state-card{display:flex;min-height:230px;align-items:center;justify-content:center;gap:10px;margin-top:20px;padding:24px;color:#5c748d;border:1px solid #dce5ef;border-radius:13px;background:#fff}.state-card.error div{flex:1}.state-card p{margin:5px 0 0;font-size:12px}.state-card button{min-height:44px;padding:9px 12px;color:#2d64ba;border:1px solid #b7cfed;border-radius:8px;background:#fff;font-weight:700}.state-card.empty{flex-direction:column;text-align:center}.mobile-steps,.mobile-bottom-bar{display:none}.spin{animation:rotate .8s linear infinite}@keyframes rotate{to{transform:rotate(360deg)}}
.paper-sheet{position:relative;display:block;padding:0}.trim-area{box-sizing:border-box;display:grid;grid-template-rows:auto 1fr auto;width:var(--trim-width);height:var(--trim-height);padding:var(--margin-top) var(--margin-right) var(--margin-bottom) var(--margin-left);overflow:hidden;background:#fff}.paper-sheet.imposed{background:#f3f5f7}.paper-sheet.imposed .trim-area{box-shadow:inset -1px -1px 0 #c3ccd5}.crop-line,.binding-guide{position:absolute;z-index:2;display:block;pointer-events:none}.crop-right{top:0;left:var(--trim-width);height:var(--trim-height);border-left:.25mm dashed #6f7780}.crop-bottom{top:var(--trim-height);left:0;width:var(--trim-width);border-top:.25mm dashed #6f7780}.crop-label{position:absolute;z-index:3;padding:1mm 1.5mm;color:#5d6873;border-radius:2mm;background:#e9edf1;font-size:7pt;font-weight:700}.crop-label-right{top:4mm;left:calc(var(--trim-width) + 2mm)}.crop-label-bottom{top:calc(var(--trim-height) + 2mm);left:4mm}.binding-guide{top:var(--margin-top);bottom:var(--margin-bottom);left:calc(var(--base-left-margin) + var(--binding-margin));border-left:.2mm dotted #8c96a0}.print-question.without-divider{border-bottom-color:transparent}.print-question.without-number{grid-template-columns:minmax(0,1fr)}.setting-helper{margin:-3px 0 2px;padding:8px;color:#657b91;border-radius:7px;background:#f5f8fb;font-size:10px;line-height:1.55}.number-with-unit{display:flex!important;min-height:44px;align-items:center;justify-content:space-between;gap:8px}.number-with-unit span{display:flex;align-items:center;gap:5px}.number-with-unit input{width:68px!important}.settings-body select:disabled,.settings-body fieldset:disabled,.checkbox-list label:has(input:disabled){cursor:not-allowed;opacity:.48}
@media(max-width:1180px){.studio-grid{grid-template-columns:240px minmax(430px,1fr)}.settings-panel{grid-column:1/-1;position:static;display:grid;grid-template-columns:1fr 1fr;max-height:none}.settings-panel>.panel-heading,.settings-panel>.template-section,.settings-panel>.save-template-box,.settings-panel>.save-template-button,.settings-panel>.notice-message,.settings-panel>.inline-error{grid-column:1/-1}.settings-panel details{border:1px solid #e3e9ef;border-right:0;border-left:0}.page-stage{max-height:none}}
@media(max-width:900px){.print-workspace{padding:18px 14px 88px}.studio-heading{align-items:stretch;flex-direction:column}.studio-heading h1{font-size:26px}.heading-actions{display:none}.mobile-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-top:16px;padding:4px;border-radius:10px;background:#e9eff6}.mobile-steps button{min-height:42px;color:#627990;border:0;border-radius:7px;background:transparent;font-size:12px;font-weight:700}.mobile-steps button.active{color:#285faa;background:#fff;box-shadow:0 1px 4px rgba(46,72,101,.13)}.studio-grid{display:block;margin-top:12px}.studio-panel,.preview-panel{display:none}.studio-panel.mobile-visible,.preview-panel.mobile-visible{display:block}.questions-panel,.settings-panel{position:static;max-height:none}.question-editor-list{max-height:none}.settings-panel.mobile-visible{display:block}.preview-panel{margin-inline:-14px;border-right:0;border-left:0;border-radius:0}.preview-toolbar{border-radius:0}.page-stage{padding:12px 8px}.page-stack{zoom:.48}.zoom-note{display:none}.mobile-bottom-bar{position:fixed;z-index:30;right:0;bottom:0;left:0;display:flex;min-height:68px;align-items:center;justify-content:space-between;gap:12px;padding:10px 16px calc(10px + env(safe-area-inset-bottom));color:#516a82;border-top:1px solid #d6e0ea;background:rgba(255,255,255,.96);box-shadow:0 -4px 18px rgba(34,58,83,.1);font-size:12px;font-weight:700}.mobile-bottom-bar button{min-width:116px}.template-grid{grid-template-columns:1fr 1fr}}
@media print{:global(.sidebar),:global(.topbar),:global(.toast),.screen-only{display:none!important}:global(html),:global(body),:global(.app-shell),:global(.main-content){min-height:0!important;margin:0!important;background:#fff!important}.print-workspace,.studio-grid,.preview-panel,.page-stage,.page-stack{display:block!important;width:auto!important;max-width:none!important;max-height:none!important;margin:0!important;padding:0!important;overflow:visible!important;border:0!important;background:#fff!important;zoom:1!important}.paper-sheet,.paper-sheet.imposed{width:var(--paper-width);height:var(--paper-height);margin:0;background:#fff;box-shadow:none;break-after:page;page-break-after:always}.paper-sheet.imposed .trim-area{box-shadow:none}.paper-sheet:last-child{break-after:auto;page-break-after:auto}}
.question-stem :deep(.table-scroll){margin:1.6mm 0;overflow:visible;border-color:#96a5b3;border-radius:0}.question-stem :deep(table){min-width:0;table-layout:fixed;font-size:calc(var(--paper-font-size) - .35pt)}.question-stem :deep(th),.question-stem :deep(td){padding:1.25mm 1.6mm;border-color:#aebac5;overflow-wrap:anywhere}.question-stem :deep(th){color:#1f2937;background:#edf1f4}
.question-figures{display:grid;gap:2.5mm;margin-top:2.5mm}.question-figures img{display:block;max-width:100%;max-height:78mm;object-fit:contain;object-position:left top;border:.25mm solid #b9c1c9;break-inside:avoid}.print-question.clean-original{display:block;padding-top:var(--question-gap)}.print-clean-image{display:block;width:100%;max-height:190mm;object-fit:contain;object-position:left top;break-inside:avoid}
</style>
