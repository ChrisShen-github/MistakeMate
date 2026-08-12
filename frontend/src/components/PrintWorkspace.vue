<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, BookOpenCheck, CheckCircle2, FileText, LoaderCircle, Printer, RefreshCw } from '@lucide/vue'
import type { MistakeQuestion, QuestionPart } from '../types/questions'

type PrintableQuestion = MistakeQuestion & {
  batch_id: string
  subject: string
  source: string
  batch_created_at: string
}

const emit = defineEmits<{ back: [] }>()
const questions = ref<PrintableQuestion[]>([])
const selectedIds = ref<string[]>([])
const activeSubject = ref('全部学科')
const showAnswers = ref(false)
const answerDensity = ref<'standard' | 'large'>('standard')
const title = ref('MistakeMate 错题练习')
const isLoading = ref(true)
const errorMessage = ref('')

const subjects = computed(() => ['全部学科', ...Array.from(new Set(questions.value.map((question) => question.subject)))])
const visibleQuestions = computed(() => activeSubject.value === '全部学科' ? questions.value : questions.value.filter((question) => question.subject === activeSubject.value))
const selectedQuestions = computed(() => questions.value.filter((question) => selectedIds.value.includes(question.id)))
const allVisibleSelected = computed(() => visibleQuestions.value.length > 0 && visibleQuestions.value.every((question) => selectedIds.value.includes(question.id)))
const answerCount = computed(() => selectedQuestions.value.filter(hasAnswer).length)

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric' }).format(new Date(value))
}

function rootParts(question: PrintableQuestion) {
  return question.parts.filter((part) => !part.parent_id).sort((a, b) => a.position - b.position)
}

function childParts(question: PrintableQuestion, parentId: string) {
  return question.parts.filter((part) => part.parent_id === parentId).sort((a, b) => a.position - b.position)
}

function answerLineCount(part?: QuestionPart) {
  if (part) return Math.max(1, Math.min(10, part.answer_lines || 3))
  return answerDensity.value === 'large' ? 7 : 4
}

function hasPartAnswer(part: QuestionPart) {
  return part.answers.some((answer) => answer.trim()) || Boolean(part.solution.trim())
}

function hasAnswer(question: PrintableQuestion) {
  return Boolean(question.correct_answer.trim() || question.explanation.trim() || question.parts.some(hasPartAnswer))
}

function toggleVisibleQuestions() {
  const visibleIds = visibleQuestions.value.map((question) => question.id)
  if (allVisibleSelected.value) {
    selectedIds.value = selectedIds.value.filter((id) => !visibleIds.includes(id))
  } else {
    selectedIds.value = Array.from(new Set([...selectedIds.value, ...visibleIds]))
  }
}

async function loadQuestions() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const response = await fetch('/api/print/questions')
    const payload = await response.json().catch(() => ({ detail: '暂时无法读取可打印题目。' }))
    if (!response.ok) throw new Error(payload.detail)
    questions.value = payload
    selectedIds.value = payload.map((question: PrintableQuestion) => question.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '暂时无法读取可打印题目。'
  } finally {
    isLoading.value = false
  }
}

function printQuestions() {
  if (!selectedQuestions.value.length) {
    errorMessage.value = '请至少选择一道题再打印。'
    return
  }
  errorMessage.value = ''
  window.print()
}

onMounted(loadQuestions)
</script>

<template>
  <section class="print-workspace" aria-labelledby="print-heading">
    <header class="print-heading screen-only">
      <div>
        <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回</button>
        <p class="eyebrow">错题集打印</p>
        <h1 id="print-heading">选择题目，生成 A4 练习</h1>
        <p>只显示已确认的题目。可以直接连接打印机，也可以在打印窗口中保存为 PDF。</p>
      </div>
      <button class="print-button" type="button" :disabled="!selectedQuestions.length" @click="printQuestions"><Printer :size="18" />打印 {{ selectedQuestions.length }} 道题</button>
    </header>

    <div v-if="isLoading" class="state-card screen-only" aria-live="polite"><LoaderCircle class="spin" :size="22" />正在整理已确认错题…</div>
    <div v-else-if="errorMessage && !questions.length" class="state-card error screen-only" role="alert"><RefreshCw :size="21" /><div><strong>读取失败</strong><p>{{ errorMessage }}</p></div><button type="button" @click="loadQuestions">重试</button></div>
    <div v-else-if="!questions.length" class="state-card empty screen-only"><BookOpenCheck :size="28" /><strong>还没有可打印的题目</strong><p>先在“我的错题”中完成 OCR 核对并确认题目。</p><button type="button" @click="emit('back')">返回我的错题</button></div>

    <div v-else class="print-layout">
      <aside class="print-controls screen-only" aria-label="打印设置">
        <section class="control-card">
          <div class="control-title"><div><span>第 1 步</span><h2>选择题目</h2></div><strong>{{ selectedIds.length }} / {{ questions.length }}</strong></div>
          <div class="subject-filters" aria-label="按学科筛选">
            <button v-for="subject in subjects" :key="subject" type="button" :class="{ active: activeSubject === subject }" :aria-pressed="activeSubject === subject" @click="activeSubject = subject">{{ subject }}</button>
          </div>
          <button class="select-all" type="button" @click="toggleVisibleQuestions"><CheckCircle2 :size="17" />{{ allVisibleSelected ? '取消当前学科' : '选择当前学科全部题目' }}</button>
          <div class="print-question-list">
            <label v-for="question in visibleQuestions" :key="question.id" class="question-choice" :class="{ selected: selectedIds.includes(question.id) }">
              <input v-model="selectedIds" type="checkbox" :value="question.id" />
              <span><strong>{{ question.subject }} · {{ question.source }}</strong><small>{{ question.stem }}</small></span>
            </label>
          </div>
        </section>

        <section class="control-card">
          <div class="control-title"><div><span>第 2 步</span><h2>设置版式</h2></div></div>
          <label class="field-label">标题<input v-model="title" maxlength="60" /></label>
          <fieldset><legend>打印版本</legend><label><input v-model="showAnswers" type="radio" :value="false" />练习版</label><label><input v-model="showAnswers" type="radio" :value="true" />含答案版</label></fieldset>
          <fieldset v-if="!showAnswers"><legend>整题答题空间</legend><label><input v-model="answerDensity" type="radio" value="standard" />标准</label><label><input v-model="answerDensity" type="radio" value="large" />宽松</label></fieldset>
          <p v-if="showAnswers" class="answer-note"><FileText :size="16" />已选题目中 {{ answerCount }} 道录有答案；未录答案的题目会如实标注。</p>
        </section>

        <p v-if="errorMessage" class="inline-error" role="alert">{{ errorMessage }}</p>
        <button class="mobile-print-button" type="button" :disabled="!selectedQuestions.length" @click="printQuestions"><Printer :size="18" />打开打印窗口</button>
      </aside>

      <section class="print-preview" aria-label="A4 打印预览">
        <div v-if="!selectedQuestions.length" class="preview-empty screen-only"><FileText :size="27" /><strong>请选择要打印的题目</strong><p>左侧勾选后，这里会立即生成 A4 预览。</p></div>
        <article v-else class="print-paper">
          <header class="paper-heading">
            <div><span>MistakeMate</span><h2>{{ title || '错题练习' }}</h2></div>
            <strong>{{ showAnswers ? '含答案版' : '练习版' }}</strong>
            <p>姓名：<i></i></p><p>日期：<i></i></p><p>得分：<i></i></p>
          </header>

          <section v-for="(question, index) in selectedQuestions" :key="question.id" class="print-question">
            <div class="question-number">{{ index + 1 }}</div>
            <div class="question-content">
              <div class="question-meta"><span>{{ question.subject }}</span><span>{{ question.question_type }}</span><span>难度 {{ '★'.repeat(question.difficulty) }}</span><span>{{ formatDate(question.batch_created_at) }}</span></div>
              <p class="question-stem">{{ question.stem }}</p>
              <ol v-if="question.options.length" class="option-list">
                <li v-for="option in question.options" :key="option.label"><strong>{{ option.label }}.</strong>{{ option.text }}</li>
              </ol>

              <div v-if="question.parts.length" class="part-list">
                <section v-for="part in rootParts(question)" :key="part.id" class="question-part">
                  <p><strong>{{ part.label }}</strong>{{ part.prompt }}</p>
                  <template v-if="part.part_type !== '题组说明'">
                    <div v-if="showAnswers" class="printed-answer"><strong>答案</strong><span>{{ part.answers.filter(Boolean).join('；') || '暂未录入' }}</span><p v-if="part.solution">{{ part.solution }}</p></div>
                    <div v-else class="answer-lines"><span v-for="line in answerLineCount(part)" :key="line"></span></div>
                  </template>
                  <section v-for="child in childParts(question, part.id)" :key="child.id" class="question-part child">
                    <p><strong>{{ child.label }}</strong>{{ child.prompt }}</p>
                    <div v-if="showAnswers" class="printed-answer"><strong>答案</strong><span>{{ child.answers.filter(Boolean).join('；') || '暂未录入' }}</span><p v-if="child.solution">{{ child.solution }}</p></div>
                    <div v-else class="answer-lines"><span v-for="line in answerLineCount(child)" :key="line"></span></div>
                  </section>
                </section>
              </div>

              <div v-else-if="showAnswers" class="printed-answer"><strong>答案</strong><span>{{ question.correct_answer || '暂未录入' }}</span><p v-if="question.explanation">{{ question.explanation }}</p></div>
              <div v-else class="answer-lines"><span v-for="line in answerLineCount()" :key="line"></span></div>
            </div>
          </section>

          <footer class="paper-footer">由 MistakeMate 整理 · 共 {{ selectedQuestions.length }} 道题</footer>
        </article>
      </section>
    </div>
  </section>
</template>

<style scoped>
.print-workspace { max-width: 1480px; margin: 0 auto; padding: 32px 44px 64px; }.print-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; }.back-button { display: inline-flex; min-height: 44px; align-items: center; gap: 6px; margin: 0 0 14px; padding: 0; color: #315f9b; border: 0; background: transparent; font-weight: 700; cursor: pointer; }.eyebrow { margin: 0 0 7px; color: #7189a3; font-size: 12px; font-weight: 700; letter-spacing: .4px; }.print-heading h1 { margin: 0; color: #1e3553; font-size: 31px; letter-spacing: -.7px; }.print-heading p:last-child { margin: 9px 0 0; color: #667f98; font-size: 13px; }.print-button,.mobile-print-button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 7px; padding: 10px 15px; color: #fff; border: 0; border-radius: 9px; background: #f97316; font-size: 13px; font-weight: 700; cursor: pointer; }.print-button:disabled,.mobile-print-button:disabled { cursor: not-allowed; opacity: .48; }.print-layout { display: grid; grid-template-columns: minmax(300px,360px) minmax(0,1fr); gap: 24px; margin-top: 26px; align-items: start; }.print-controls { display: grid; gap: 14px; position: sticky; top: 20px; }.control-card { padding: 18px; border: 1px solid #dce5ef; border-radius: 12px; background: #fff; }.control-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.control-title > div { display: flex; align-items: center; gap: 8px; }.control-title span { padding: 3px 6px; color: #2862b9; border-radius: 5px; background: #eaf3ff; font-size: 10px; font-weight: 700; }.control-title h2 { margin: 0; color: #29435f; font-size: 16px; }.control-title > strong { color: #5d7690; font-size: 12px; }.subject-filters { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 15px; }.subject-filters button,.select-all { min-height: 40px; padding: 7px 10px; color: #536d89; border: 1px solid #d2dfea; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; cursor: pointer; }.subject-filters button.active { color: #fff; border-color: #2868cc; background: #2868cc; }.select-all { display: flex; width: 100%; min-height: 44px; align-items: center; justify-content: center; gap: 6px; margin-top: 10px; color: #315f9b; border-color: #b9d0ef; }.print-question-list { display: grid; gap: 8px; max-height: 340px; margin-top: 12px; overflow: auto; }.question-choice { display: grid; grid-template-columns: 22px minmax(0,1fr); gap: 9px; min-height: 62px; align-items: center; padding: 10px; border: 1px solid #e0e8f0; border-radius: 9px; cursor: pointer; }.question-choice.selected { border-color: #a6c5eb; background: #f5f9ff; }.question-choice input { width: 18px; height: 18px; accent-color: #2868cc; }.question-choice > span { display: grid; gap: 4px; min-width: 0; }.question-choice strong { color: #36516e; font-size: 12px; }.question-choice small { overflow: hidden; color: #6f8398; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.field-label { display: grid; gap: 7px; margin-top: 16px; color: #4a647f; font-size: 12px; font-weight: 700; }.field-label input { min-height: 44px; padding: 9px 11px; color: #243e5d; border: 1px solid #cbd9e7; border-radius: 8px; background: #fff; font: inherit; font-size: 16px; }.control-card fieldset { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 15px 0 0; padding: 0; border: 0; }.control-card legend { width: 100%; margin-bottom: 7px; color: #4a647f; font-size: 12px; font-weight: 700; }.control-card fieldset label { display: flex; min-height: 40px; align-items: center; gap: 7px; color: #536d89; font-size: 13px; cursor: pointer; }.control-card fieldset input { width: 18px; height: 18px; accent-color: #2868cc; }.answer-note { display: flex; align-items: flex-start; gap: 7px; margin: 14px 0 0; padding: 10px; color: #5c728a; border-radius: 8px; background: #f5f8fb; font-size: 11px; line-height: 1.55; }.answer-note svg { flex: 0 0 auto; }.inline-error { margin: 0; padding: 11px; color: #a7483b; border-radius: 8px; background: #fff0ed; font-size: 12px; }.mobile-print-button { width: 100%; }.print-preview { min-width: 0; padding: 24px; overflow: auto; border: 1px solid #dce5ef; border-radius: 13px; background: #e9edf1; }.preview-empty { display: grid; min-height: 500px; place-items: center; align-content: center; color: #73879b; text-align: center; }.preview-empty strong { margin-top: 9px; color: #38516e; }.preview-empty p { margin: 5px 0 0; font-size: 12px; }.print-paper { box-sizing: border-box; width: min(100%,210mm); min-height: 297mm; margin: 0 auto; padding: 14mm; color: #1f2937; background: #fff; box-shadow: 0 5px 20px rgba(30,48,70,.16); font-family: 'Noto Sans SC', 'Microsoft YaHei', sans-serif; }.paper-heading { display: grid; grid-template-columns: 1fr auto; gap: 4mm 6mm; padding-bottom: 6mm; border-bottom: 1.5px solid #1f2937; }.paper-heading > div span { color: #5f6b78; font-size: 9pt; font-weight: 700; letter-spacing: .5pt; }.paper-heading h2 { margin: 1mm 0 0; font-size: 18pt; }.paper-heading > strong { align-self: center; padding: 2mm 3mm; border: 1px solid #5b6570; font-size: 10pt; }.paper-heading > p { display: flex; align-items: flex-end; gap: 2mm; margin: 2mm 0 0; font-size: 10pt; }.paper-heading > p i { display: block; width: 32mm; border-bottom: 1px solid #69717a; }.paper-heading > p:last-of-type i { width: 20mm; }.print-question { display: grid; grid-template-columns: 8mm minmax(0,1fr); gap: 2mm; padding: 7mm 0; border-bottom: 1px dashed #aeb5bd; break-inside: auto; }.question-number { display: grid; width: 6mm; height: 6mm; place-items: center; color: #fff; border-radius: 50%; background: #222; font-size: 9pt; font-weight: 700; }.question-meta { display: flex; flex-wrap: wrap; gap: 2mm; margin-bottom: 3mm; color: #606a75; font-size: 8.5pt; }.question-meta span + span::before { content: '·'; margin-right: 2mm; }.question-stem,.question-part > p { margin: 0; font-size: 11pt; line-height: 1.8; white-space: pre-wrap; }.option-list { display: grid; grid-template-columns: 1fr 1fr; gap: 2mm 7mm; margin: 4mm 0 0; padding: 0; list-style: none; font-size: 10.5pt; }.option-list li { break-inside: avoid; }.option-list strong { margin-right: 2mm; }.part-list { display: grid; gap: 5mm; margin-top: 5mm; }.question-part { break-inside: auto; }.question-part.child { margin: 4mm 0 0 5mm; }.question-part > p strong { margin-right: 2mm; }.answer-lines { display: grid; margin-top: 2mm; }.answer-lines span { display: block; height: 7mm; border-bottom: 1px solid #bcc2c9; }.printed-answer { margin-top: 3mm; padding: 3mm; border-left: 2px solid #4b5563; background: #f4f5f6; font-size: 9.5pt; line-height: 1.65; break-inside: avoid; }.printed-answer strong { margin-right: 3mm; }.printed-answer p { margin: 2mm 0 0; white-space: pre-wrap; }.paper-footer { padding-top: 5mm; color: #6b7280; text-align: center; font-size: 8.5pt; }.state-card { display: flex; min-height: 230px; align-items: center; justify-content: center; gap: 10px; margin-top: 24px; padding: 24px; color: #5c748d; border: 1px solid #dce5ef; border-radius: 13px; background: #fff; }.state-card.error div { flex: 1; }.state-card.error p,.state-card.empty p { margin: 5px 0 0; font-size: 12px; }.state-card button { min-height: 44px; padding: 9px 12px; color: #2d64ba; border: 1px solid #b7cfed; border-radius: 8px; background: #fff; font-weight: 700; }.state-card.empty { flex-direction: column; text-align: center; }.spin { animation: rotate .8s linear infinite; }@keyframes rotate { to { transform: rotate(360deg); } }
@media (max-width: 980px) { .print-workspace { padding: 26px 24px 48px; }.print-layout { grid-template-columns: 1fr; }.print-controls { position: static; grid-template-columns: 1fr 1fr; }.mobile-print-button,.inline-error { grid-column: 1 / -1; }.print-question-list { max-height: 280px; } }
@media (max-width: 640px) { .print-workspace { padding: 22px 17px 42px; }.print-heading { align-items: stretch; flex-direction: column; }.print-heading h1 { font-size: 27px; line-height: 1.25; }.print-button { width: 100%; }.print-controls { grid-template-columns: 1fr; }.mobile-print-button,.inline-error { grid-column: auto; }.print-preview { margin-inline: -17px; padding: 12px 7px; border-right: 0; border-left: 0; border-radius: 0; }.print-paper { padding: 8mm 6mm; }.paper-heading { grid-template-columns: 1fr auto; }.paper-heading > p { font-size: 8.5pt; }.paper-heading > p i { width: 20mm; }.question-meta span:nth-last-child(-n+2) { display: none; }.option-list { grid-template-columns: 1fr; } }
.mobile-print-button { display: none; }
.subject-filters button,.select-all,.control-card fieldset label { min-height: 44px; }
@media (max-width: 640px) { .print-heading > .print-button { display: none; }.mobile-print-button { display: inline-flex; } }
@page { size: A4; margin: 14mm; }
@media print {
  :global(.sidebar),:global(.topbar),:global(.toast),.screen-only { display: none !important; }
  :global(html),:global(body),:global(.app-shell),:global(.main-content) { min-height: 0 !important; margin: 0 !important; background: #fff !important; }
  .print-workspace,.print-preview { width: auto; margin: 0; padding: 0; overflow: visible; border: 0; background: #fff; }
  .print-layout { display: block; margin: 0; }
  .print-paper { width: auto; min-height: 0; margin: 0; padding: 0; box-shadow: none; }
}
</style>
