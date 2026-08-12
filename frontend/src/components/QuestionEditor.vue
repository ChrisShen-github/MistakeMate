<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { CheckCircle2, CircleAlert, LoaderCircle, Plus, Save, Trash2 } from '@lucide/vue'

export type QuestionOption = { label: string; text: string }
export type MistakeQuestion = {
  id: string
  position: number
  question_type: string
  stem: string
  options: QuestionOption[]
  correct_answer: string
  explanation: string
  knowledge_points: string
  difficulty: number
  error_type: string
  status: string
  updated_at: string
}

const props = defineProps<{ batchId: string; question: MistakeQuestion }>()
const emit = defineEmits<{ saved: [question: MistakeQuestion] }>()

function cloneQuestion(question: MistakeQuestion) {
  return {
    question_type: question.question_type,
    stem: question.stem,
    options: question.options.map((option) => ({ ...option })),
    correct_answer: question.correct_answer,
    explanation: question.explanation,
    knowledge_points: question.knowledge_points,
    difficulty: question.difficulty,
    error_type: question.error_type,
  }
}

const draft = reactive(cloneQuestion(props.question))
const isSaving = ref(false)
const feedback = ref('')
const saveError = ref('')

watch(() => props.question, (question) => {
  Object.assign(draft, cloneQuestion(question))
  feedback.value = ''
  saveError.value = ''
}, { deep: true })

function addOption() {
  const nextLabel = String.fromCharCode(65 + draft.options.length)
  draft.options.push({ label: nextLabel, text: '' })
}

function removeOption(index: number) { draft.options.splice(index, 1) }

async function save(status: 'draft' | 'confirmed') {
  if (isSaving.value) return
  isSaving.value = true
  feedback.value = ''
  saveError.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/questions/${props.question.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...draft, status }),
    })
    const payload = await response.json().catch(() => ({ detail: '保存失败，请稍后重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    emit('saved', payload)
    feedback.value = status === 'confirmed' ? '题目已确认，可以进入错题集和复练安排。' : '已保存为草稿。'
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '保存失败，请稍后重试。'
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <article class="question-editor" :aria-labelledby="`question-${question.id}`">
    <header class="editor-heading"><div><p class="eyebrow">题目 {{ question.position }} · 可编辑初稿</p><h2 :id="`question-${question.id}`">确认这道错题</h2><p>先核对 OCR 文字，再补充学习信息。原图始终保留在下方可对照。</p></div><span class="draft-chip" :class="{ confirmed: question.status === 'confirmed' }">{{ question.status === 'confirmed' ? '已确认' : '待确认' }}</span></header>

    <p v-if="saveError" class="editor-error" role="alert"><CircleAlert :size="17" />{{ saveError }}</p>
    <p v-else-if="feedback" class="editor-success" role="status" aria-live="polite"><CheckCircle2 :size="17" />{{ feedback }}</p>

    <div class="editor-grid">
      <label class="wide-field">题干 <span>必填</span><textarea v-model="draft.stem" rows="4" placeholder="补充或修正题干文字"></textarea></label>
      <label>题型<select v-model="draft.question_type"><option>单选题</option><option>多选题</option><option>判断题</option><option>填空题</option><option>计算题</option><option>简答题</option><option>其他</option></select></label>
      <fieldset class="difficulty-field"><legend>难度</legend><div class="stars" aria-label="难度星级"><button v-for="star in 5" :key="star" type="button" :class="{ active: star <= draft.difficulty }" :aria-label="`${star} 星难度`" :aria-pressed="star === draft.difficulty" @click="draft.difficulty = star">★</button></div></fieldset>
    </div>

    <section class="options-section" aria-labelledby="options-heading"><div class="field-heading"><div><p class="eyebrow">选择题可编辑</p><h3 id="options-heading">选项</h3></div><button class="text-action" type="button" @click="addOption"><Plus :size="17" />添加选项</button></div><p v-if="!draft.options.length" class="empty-options">这不是选择题？可以不添加选项，直接填写题干和答案。</p><div v-else class="option-list"><div v-for="(option, index) in draft.options" :key="`${option.label}-${index}`" class="option-row"><label :for="`option-label-${question.id}-${index}`">编号</label><input :id="`option-label-${question.id}-${index}`" v-model="option.label" maxlength="8" /><label :for="`option-text-${question.id}-${index}`" class="sr-only">选项内容</label><textarea :id="`option-text-${question.id}-${index}`" v-model="option.text" rows="2" placeholder="选项内容"></textarea><button class="remove-option" type="button" :aria-label="`移除选项 ${option.label || index + 1}`" @click="removeOption(index)"><Trash2 :size="17" /></button></div></div></section>

    <div class="editor-grid answer-grid">
      <label>正确答案<input v-model="draft.correct_answer" maxlength="128" placeholder="例如：A"></label>
      <label>错因<select v-model="draft.error_type"><option value="">暂不填写</option><option>计算错误</option><option>审题不清</option><option>概念不牢</option><option>方法不会</option><option>粗心遗漏</option><option>其他</option></select></label>
      <label class="wide-field">知识点 <span>用逗号分隔</span><input v-model="draft.knowledge_points" maxlength="1000" placeholder="例如：企业清算，企业所得税"></label>
      <label class="wide-field">解析 <span>可选</span><textarea v-model="draft.explanation" rows="5" placeholder="补充或修正解析；公式和图形仍建议以原图为准。"></textarea></label>
    </div>

    <footer class="editor-actions"><p><span aria-hidden="true">●</span> {{ question.status === 'confirmed' ? '已确认，可继续修改后重新确认。' : '保存草稿后可随时回来继续编辑。' }}</p><div><button class="draft-button" type="button" :disabled="isSaving" @click="save('draft')"><Save :size="17" />保存草稿</button><button class="confirm-button" type="button" :disabled="isSaving" @click="save('confirmed')"><LoaderCircle v-if="isSaving" class="spin" :size="17" /><CheckCircle2 v-else :size="17" />确认题目</button></div></footer>
  </article>
</template>

<style scoped>
.question-editor { margin-top: 27px; padding: 24px; border: 1px solid #d9e4ef; border-radius: 14px; background: #fff; }.editor-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }.eyebrow { margin: 0 0 6px; color: #7189a3; font-size: 12px; font-weight: 700; letter-spacing: .35px; }.editor-heading h2 { margin: 0; color: #29435f; font-size: 20px; }.editor-heading p:last-child { max-width: 640px; margin: 7px 0 0; color: #617991; font-size: 13px; line-height: 1.55; }.draft-chip { flex: 0 0 auto; padding: 6px 9px; color: #92651e; border-radius: 6px; background: #fff4d7; font-size: 11px; font-weight: 700; }.draft-chip.confirmed { color: #23785d; background: #e8f7f0; }.editor-error,.editor-success { display: flex; align-items: center; gap: 7px; margin: 16px 0 0; padding: 11px; border-radius: 8px; font-size: 13px; }.editor-error { color: #a84436; background: #fff4f2; }.editor-success { color: #247358; background: #edf9f3; }.editor-grid { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 15px; margin-top: 20px; }.editor-grid > label,.difficulty-field { display: grid; gap: 7px; color: #405a75; font-size: 12px; font-weight: 700; }.editor-grid span { color: #8597a8; font-size: 11px; font-weight: 500; }.wide-field { grid-column: 1 / -1; }.editor-grid input,.editor-grid textarea,.editor-grid select,.option-row input,.option-row textarea { width: 100%; box-sizing: border-box; color: #2d4662; border: 1px solid #c9d8e6; border-radius: 8px; background: #fff; font: inherit; font-size: 14px; line-height: 1.55; }.editor-grid input,.editor-grid select { min-height: 44px; padding: 0 11px; }.editor-grid textarea { padding: 10px 11px; resize: vertical; }.editor-grid input:focus,.editor-grid textarea:focus,.editor-grid select:focus,.option-row input:focus,.option-row textarea:focus { border-color: #2563eb; outline: 3px solid rgba(37,99,235,.15); }.difficulty-field { min-width: 0; padding: 0; border: 0; }.difficulty-field legend { margin-bottom: 7px; }.stars { display: flex; min-height: 44px; align-items: center; gap: 3px; }.stars button { display: grid; width: 36px; height: 40px; place-items: center; color: #c7d2df; border: 0; border-radius: 7px; background: transparent; font-size: 24px; cursor: pointer; transition: color .18s ease, background .18s ease; }.stars button.active { color: #f59e0b; }.stars button:hover { background: #fff7e5; }.stars button:focus-visible,.text-action:focus-visible,.remove-option:focus-visible,.editor-actions button:focus-visible { outline: 3px solid rgba(37,99,235,.22); outline-offset: 2px; }.options-section { margin-top: 23px; padding: 18px; border: 1px solid #e0e8f0; border-radius: 10px; background: #fbfdff; }.field-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }.field-heading h3 { margin: 0; color: #334e6b; font-size: 16px; }.text-action { display: inline-flex; min-height: 40px; align-items: center; gap: 5px; padding: 7px 10px; color: #285fae; border: 1px solid #b9d1ef; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; cursor: pointer; }.option-list { display: grid; gap: 10px; margin-top: 15px; }.option-row { display: grid; grid-template-columns: 40px 48px minmax(0,1fr) 40px; gap: 8px; align-items: center; }.option-row > label:first-child { color: #6f8398; font-size: 11px; font-weight: 700; }.option-row input { min-height: 42px; padding: 0 8px; text-align: center; }.option-row textarea { min-height: 44px; padding: 9px; resize: vertical; }.remove-option { display: grid; width: 40px; height: 40px; place-items: center; color: #7b8da0; border: 0; border-radius: 8px; background: transparent; cursor: pointer; }.remove-option:hover { color: #ae4a3d; background: #fff0ed; }.empty-options { margin: 13px 0 0; color: #71859a; font-size: 13px; }.answer-grid { margin-top: 23px; }.editor-actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 24px; padding-top: 17px; border-top: 1px solid #e0e7ee; }.editor-actions p { display: flex; align-items: flex-start; gap: 7px; margin: 0; color: #657b92; font-size: 12px; line-height: 1.5; }.editor-actions p span { color: #2f9a75; font-size: 14px; }.editor-actions > div { display: flex; gap: 9px; }.editor-actions button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 6px; padding: 9px 13px; border-radius: 8px; font-size: 13px; font-weight: 700; cursor: pointer; transition: background .18s ease, border-color .18s ease, opacity .18s ease; }.draft-button { color: #315f9b; border: 1px solid #b9cee5; background: #fff; }.draft-button:hover { background: #f3f8ff; }.confirm-button { min-width: 122px; color: #fff; border: 1px solid #f97316; background: #f97316; }.confirm-button:hover { background: #db600d; }.editor-actions button:disabled { cursor: wait; opacity: .6; }.spin { animation: rotate .8s linear infinite; }@keyframes rotate { to { transform: rotate(360deg); } }.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }@media (max-width: 760px) { .question-editor { margin-top: 18px; padding: 17px; }.editor-heading { flex-direction: column; gap: 10px; }.draft-chip { align-self: flex-start; }.editor-grid { grid-template-columns: 1fr; gap: 14px; }.wide-field { grid-column: auto; }.options-section { padding: 15px; }.option-row { grid-template-columns: 43px minmax(0,1fr) 40px; }.option-row > label:first-child { display: none; }.option-row textarea { grid-column: 1 / -1; grid-row: 2; }.option-row input { grid-column: 1; grid-row: 1; }.remove-option { grid-column: 3; grid-row: 1; }.editor-actions { align-items: stretch; flex-direction: column; }.editor-actions > div { display: grid; grid-template-columns: 1fr 1.2fr; }.editor-actions button { width: 100%; }.text-action { min-height: 44px; } }@media (prefers-reduced-motion: reduce) { .stars button,.editor-actions button { transition: none; }.spin { animation: none; } }
</style>
