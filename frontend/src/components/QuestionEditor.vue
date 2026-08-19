<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ArrowLeft, Camera, CheckCircle2, CircleAlert, FileText, ImagePlus, Layers3, LoaderCircle, Plus, Save, Sparkles, Trash2, WandSparkles } from '@lucide/vue'
import QuestionPartEditor from './QuestionPartEditor.vue'
import QuestionText from './QuestionText.vue'
import type { MistakeQuestion, QuestionPart } from '../types/questions'

export type { MistakeQuestion } from '../types/questions'

const props = defineProps<{ batchId: string; question: MistakeQuestion; canAddFigure?: boolean; canAutoExtractFigure?: boolean }>()
const emit = defineEmits<{ saved: [question: MistakeQuestion]; finished: []; 'add-figure': []; 'auto-extract-figure': []; 'remove-figure': [figureId: string] }>()

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
    parts: question.parts.map((part) => ({ ...part, answers: [...part.answers], key_points: [...part.key_points] })),
  }
}

const draft = reactive(cloneQuestion(props.question))
const isSaving = ref(false)
const savingAction = ref<'draft' | 'confirmed' | null>(null)
const isSuggesting = ref(false)
const isUploadingAnswerPhotos = ref(false)
const answerPhotoInput = ref<HTMLInputElement | null>(null)
const feedback = ref('')
const saveError = ref('')
const hasParts = computed(() => draft.parts.length > 0)
const hasMarkdownTable = computed(() => /^\s*\|?.+\|.+\|?\s*\n\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/m.test(draft.stem))
const hasLatexMath = computed(() => /\\\[|\\\(|\$\$|\$[^$\n]+\$|\\(?:frac|dfrac|min|max|left|right|sqrt|sum|prod|int)\b/.test(draft.stem))
const hasUnconfirmedText = computed(() => /[［\[]\s*无法确认\s*[］\]]|【\s*无法确认\s*】/.test(draft.stem))
const rootParts = computed(() => draft.parts.filter((part) => !part.parent_id).sort((a, b) => a.position - b.position))
const answerablePartCount = computed(() => draft.parts.filter((part) => part.part_type !== '题组说明').length)
const hasSimpleAnswer = computed(() => Boolean(draft.correct_answer.trim() || draft.explanation.trim()))
const hasAnswerPhotos = computed(() => props.question.answer_files.length > 0)
const circledLabels = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩']

watch(() => props.question, (question) => {
  Object.assign(draft, cloneQuestion(question))
}, { deep: true })

function newId() { return crypto.randomUUID() }
function normalizePositions() { draft.parts.forEach((part, index) => { part.position = index + 1 }) }
function childrenFor(parentId: string) { return draft.parts.filter((part) => part.parent_id === parentId).sort((a, b) => a.position - b.position) }

function createPart(parentId: string | null = null, partType = '计算题'): QuestionPart {
  const siblings = draft.parts.filter((part) => part.parent_id === parentId)
  const label = parentId ? (circledLabels[siblings.length] ?? `子问${siblings.length + 1}`) : `(${siblings.length + 1})`
  return {
    id: newId(), parent_id: parentId, position: draft.parts.length + 1, label, part_type: partType,
    prompt: '', answers: partType === '题组说明' ? [] : [''], solution: '', key_points: [],
    answer_lines: partType === '题组说明' ? 0 : 4, knowledge_points: '', difficulty: draft.difficulty, error_type: '',
  }
}

function addRootPart(partType = '计算题') {
  draft.parts.push(createPart(null, partType))
  normalizePositions()
}

function addChild(parentId: string) {
  const parentIndex = draft.parts.findIndex((part) => part.id === parentId)
  const siblings = childrenFor(parentId)
  const part = createPart(parentId)
  const lastSiblingIndex = siblings.length ? draft.parts.findIndex((item) => item.id === siblings[siblings.length - 1].id) : parentIndex
  draft.parts.splice(lastSiblingIndex + 1, 0, part)
  normalizePositions()
}

function removePart(partId: string) {
  const part = draft.parts.find((item) => item.id === partId)
  if (!part) return
  const childCount = childrenFor(partId).length
  const message = childCount ? `移除 ${part.label} 会同时移除下面的 ${childCount} 个子问，确定吗？` : `确定移除小问 ${part.label} 吗？`
  if (!window.confirm(message)) return
  draft.parts = draft.parts.filter((item) => item.id !== partId && item.parent_id !== partId)
  normalizePositions()
}

function addOption() {
  const nextLabel = String.fromCharCode(65 + draft.options.length)
  draft.options.push({ label: nextLabel, text: '' })
}

function removeOption(index: number) { draft.options.splice(index, 1) }

async function suggestStructure() {
  if (isSuggesting.value) return
  isSuggesting.value = true
  feedback.value = ''
  saveError.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/questions/${props.question.id}/structure-suggestion`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ stem: draft.stem }),
    })
    const payload = await response.json().catch(() => ({ detail: '暂时无法识别小问。' }))
    if (!response.ok) throw new Error(payload.detail)
    draft.stem = payload.stem
    draft.parts = payload.parts
    if (!['综合题', '计算题', '证明题'].includes(draft.question_type)) draft.question_type = '综合题'
    feedback.value = `已识别出 ${answerablePartCount.value} 个可作答小问，请核对后保存。`
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '暂时无法识别小问。'
  } finally {
    isSuggesting.value = false
  }
}

function returnToSimpleMode() {
  if (!window.confirm('切回单题模式会移除当前小问结构，尚未保存的答案会丢失，确定吗？')) return
  draft.parts = []
}

function answerPhotoUrl(answerFileId: string) {
  return `/api/mistakes/${props.batchId}/questions/${props.question.id}/answer-files/${answerFileId}`
}

function chooseAnswerPhotos() {
  answerPhotoInput.value?.click()
}

async function uploadAnswerPhotos(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length || isUploadingAnswerPhotos.value) return
  isUploadingAnswerPhotos.value = true
  saveError.value = ''
  feedback.value = ''
  try {
    const body = new FormData()
    files.forEach((file) => body.append('files', file))
    const response = await fetch(`/api/mistakes/${props.batchId}/questions/${props.question.id}/answer-files`, { method: 'POST', body })
    const payload = await response.json().catch(() => ({ detail: '答案照片上传失败，请稍后重试。' }))
    if (!response.ok) throw new Error(payload.detail || '答案照片上传失败，请稍后重试。')
    emit('saved', payload)
    feedback.value = `已添加 ${files.length} 张答案照片。`
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '答案照片上传失败，请稍后重试。'
  } finally {
    isUploadingAnswerPhotos.value = false
  }
}

async function removeAnswerPhoto(answerFileId: string) {
  if (!window.confirm('确定删除这张答案照片吗？')) return
  saveError.value = ''
  feedback.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/questions/${props.question.id}/answer-files/${answerFileId}`, { method: 'DELETE' })
    const payload = await response.json().catch(() => ({ detail: '答案照片删除失败，请稍后重试。' }))
    if (!response.ok) throw new Error(payload.detail || '答案照片删除失败，请稍后重试。')
    emit('saved', payload)
    feedback.value = '已删除答案照片。'
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '答案照片删除失败，请稍后重试。'
  }
}

async function save(status: 'draft' | 'confirmed') {
  if (isSaving.value) return
  isSaving.value = true
  savingAction.value = status
  feedback.value = ''
  saveError.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/questions/${props.question.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...draft, status }),
    })
    const payload = await response.json().catch(() => ({ detail: '保存失败，请稍后重试。' }))
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '请检查小问内容后重试。')
    emit('saved', payload)
    feedback.value = status === 'confirmed' ? '题目已确认，可以进入错题集并用于后续打印。' : '已保存为草稿。'
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '保存失败，请稍后重试。'
  } finally {
    isSaving.value = false
    savingAction.value = null
  }
}
</script>

<template>
  <article class="question-editor" :aria-labelledby="`question-${question.id}`">
    <header class="editor-heading">
      <div><p class="eyebrow">题目 {{ question.position }} · 可编辑初稿</p><h2 :id="`question-${question.id}`">确认这道错题</h2><p>先核对 OCR 文字，再补充学习信息。原图始终保留在下方可对照。</p></div>
      <span class="draft-chip" :class="{ confirmed: question.status === 'confirmed' }">{{ question.status === 'confirmed' ? '已确认' : '待确认' }}</span>
    </header>

    <p v-if="saveError" class="editor-error" role="alert"><CircleAlert :size="17" />{{ saveError }}</p>
    <p v-else-if="feedback" class="editor-success" role="status" aria-live="polite"><CheckCircle2 :size="17" />{{ feedback }}</p>
    <p class="answer-optional-note"><FileText :size="17" /><span><strong>答案不是必填项</strong>只要题干和小问完整，就能确认并用于练习版打印；答案以后可以随时补充。</span></p>

    <section class="figure-section" aria-label="题图">
      <div><strong>题图</strong><small>坐标轴、几何图、统计图等会随题目打印。AI 可先自动找图；边界不准时再手动截取。</small></div>
      <div class="figure-actions"><button v-if="canAutoExtractFigure" type="button" :disabled="!canAddFigure" @click="emit('auto-extract-figure')"><WandSparkles :size="17" />AI 自动提取</button><button type="button" :disabled="!canAddFigure" @click="emit('add-figure')"><ImagePlus :size="17" />手动截取</button></div>
      <p v-if="!canAddFigure" class="figure-empty">这组题没有可裁切的原始图片。</p>
      <div v-if="question.figures.length" class="figure-list"><figure v-for="figure in question.figures" :key="figure.id"><img :src="`/api/mistakes/${batchId}/questions/${question.id}/figures/${figure.id}`" alt="题目图形" /><button type="button" :aria-label="`删除第 ${figure.position} 张题图`" @click="emit('remove-figure', figure.id)"><Trash2 :size="16" />删除</button></figure></div>
    </section>

    <div class="editor-grid">
      <div class="wide-field stem-field"><label :for="`question-stem-${question.id}`">{{ hasParts ? '公共题干' : '题干' }} <span>必填</span></label><textarea :id="`question-stem-${question.id}`" v-model="draft.stem" rows="5" :placeholder="hasParts ? '填写所有小问共同使用的题目背景和条件' : '补充或修正题干文字'"></textarea><p v-if="hasUnconfirmedText" class="unconfirmed-warning" role="alert"><CircleAlert :size="17" /><span><strong>这里有 AI 无法确认的内容</strong>请对照下方原图，把“［无法确认］”替换为正确文字；看不清时可重新裁切该区域后再识别。</span></p><section v-if="hasMarkdownTable || hasLatexMath" class="table-preview formula-preview" aria-label="题目排版预览"><div><strong>{{ hasLatexMath ? '公式排版预览' : '识别出的表格' }}</strong><small>{{ hasLatexMath ? '上方保留可编辑的公式源码；这里和打印页会显示为正常数学排版。' : '已按原生表格显示和打印；如需修改，请直接编辑上方题干。' }}</small></div><QuestionText :text="draft.stem" /></section></div>
      <label>题型<select v-model="draft.question_type"><option>单选题</option><option>多选题</option><option>判断题</option><option>填空题</option><option>计算题</option><option>证明题</option><option>综合题</option><option>简答题</option><option>其他</option></select></label>
      <fieldset class="difficulty-field"><legend>整题难度</legend><div class="stars" aria-label="整题难度星级"><button v-for="star in 5" :key="star" type="button" :class="{ active: star <= draft.difficulty }" :aria-label="`${star} 星难度`" :aria-pressed="star === draft.difficulty" @click="draft.difficulty = star">★</button></div></fieldset>
    </div>

    <section v-if="!hasParts" class="options-section" aria-labelledby="options-heading">
      <div class="field-heading"><div><p class="eyebrow">选择题可编辑</p><h3 id="options-heading">选项</h3></div><button class="text-action" type="button" @click="addOption"><Plus :size="17" />添加选项</button></div>
      <p v-if="!draft.options.length" class="empty-options">这不是选择题？可以不添加选项，直接保存完整题干，需要时再补答案。</p>
      <div v-else class="option-list"><div v-for="(option, index) in draft.options" :key="`${option.label}-${index}`" class="option-row"><label :for="`option-label-${question.id}-${index}`">编号</label><input :id="`option-label-${question.id}-${index}`" v-model="option.label" maxlength="8" /><label :for="`option-text-${question.id}-${index}`" class="sr-only">选项内容</label><textarea :id="`option-text-${question.id}-${index}`" v-model="option.text" rows="2" placeholder="选项内容"></textarea><button class="remove-option" type="button" :aria-label="`移除选项 ${option.label || index + 1}`" @click="removeOption(index)"><Trash2 :size="17" /></button></div></div>
    </section>

    <section class="structure-section" aria-labelledby="structure-heading">
      <div class="structure-heading">
        <div><p class="eyebrow">答案结构</p><h3 id="structure-heading">{{ hasParts ? `${answerablePartCount} 个可作答小问` : '当前按一道简单题填写' }}</h3><p>{{ hasParts ? '公共题干只显示一次，每个小问分别保存答案和过程。' : '遇到 (1)、(2)、①、② 等多问题型，可以自动识别或手动添加。' }}</p></div>
        <div class="structure-actions">
          <button v-if="!hasParts" class="suggest-button" type="button" :disabled="isSuggesting" @click="suggestStructure"><LoaderCircle v-if="isSuggesting" class="spin" :size="17" /><Sparkles v-else :size="17" />{{ isSuggesting ? '正在识别…' : '识别小问' }}</button>
          <button class="add-part-button" type="button" @click="addRootPart()"><Plus :size="17" />添加小问</button>
          <button v-if="hasParts" class="add-group-button" type="button" @click="addRootPart('题组说明')"><Layers3 :size="17" />添加分组</button>
        </div>
      </div>

      <div v-if="hasParts" class="part-list">
        <template v-for="part in rootParts" :key="part.id">
          <QuestionPartEditor :part="part" @remove="removePart(part.id)" @add-child="addChild(part.id)" />
          <QuestionPartEditor v-for="child in childrenFor(part.id)" :key="child.id" :part="child" child @remove="removePart(child.id)" />
        </template>
        <button class="simple-mode-button" type="button" @click="returnToSimpleMode">切回单题模式</button>
      </div>
    </section>

    <details v-if="!hasParts" class="simple-answer-details" :open="hasSimpleAnswer || hasAnswerPhotos">
      <summary>答案与解析 <span>可选，不填写也能确认题目</span><small v-if="hasSimpleAnswer || hasAnswerPhotos">已填写</small></summary>
      <div class="editor-grid answer-grid"><label>正确答案 <span>可选</span><input v-model="draft.correct_answer" maxlength="128" placeholder="有答案时再填写"></label><label class="wide-field">解析 <span>可选</span><textarea v-model="draft.explanation" rows="5" placeholder="有解析时再补充；公式和图形仍建议以原图为准。"></textarea></label></div>
    </details>

    <section class="answer-photo-section" aria-labelledby="answer-photo-heading">
      <div class="answer-photo-heading"><div><p class="eyebrow">手写答案可选</p><h3 id="answer-photo-heading">答案照片</h3><p>解题过程跨页时可以一次添加多张照片，按上传顺序保存；不影响题目和练习版打印。</p></div><input ref="answerPhotoInput" class="sr-only" type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" multiple @change="uploadAnswerPhotos" /><button type="button" :disabled="isUploadingAnswerPhotos" @click="chooseAnswerPhotos"><LoaderCircle v-if="isUploadingAnswerPhotos" class="spin" :size="17" /><Camera v-else :size="17" />{{ isUploadingAnswerPhotos ? '正在上传…' : '拍照或选择照片' }}</button></div>
      <p v-if="!hasAnswerPhotos" class="answer-photo-empty">暂未添加答案照片。适合保留孩子的手写步骤、演算纸或跨页答案。</p>
      <div v-else class="answer-photo-list"><figure v-for="answerFile in question.answer_files" :key="answerFile.id"><a :href="answerPhotoUrl(answerFile.id)" target="_blank" rel="noreferrer"><img :src="answerPhotoUrl(answerFile.id)" :alt="`答案照片 ${answerFile.position}：${answerFile.original_name}`" loading="lazy" /><figcaption>第 {{ answerFile.position }} 张 · {{ answerFile.original_name }}</figcaption></a><button type="button" :aria-label="`删除第 ${answerFile.position} 张答案照片`" @click="removeAnswerPhoto(answerFile.id)"><Trash2 :size="16" />删除</button></figure></div>
    </section>

    <div class="editor-grid metadata-grid">
      <label>整题错因<select v-model="draft.error_type"><option value="">暂不填写</option><option>计算错误</option><option>审题不清</option><option>概念不牢</option><option>方法不会</option><option>粗心遗漏</option><option>其他</option></select></label>
      <label>整题知识点 <span>用逗号分隔</span><input v-model="draft.knowledge_points" maxlength="1000" placeholder="例如：数的表示，整式运算"></label>
    </div>

    <footer class="editor-actions">
      <p v-if="saveError" class="action-message error" role="alert"><CircleAlert :size="17" />{{ saveError }}</p>
      <p v-else-if="feedback" class="action-message success" role="status" aria-live="polite"><CheckCircle2 :size="17" />{{ feedback }}</p>
      <p v-else><span aria-hidden="true">●</span>{{ question.status === 'confirmed' ? '已确认，可继续修改后重新确认。' : '保存草稿后可随时回来继续编辑。' }}</p>
      <div>
        <button v-if="question.status === 'confirmed' && feedback" class="back-library-button" type="button" @click="emit('finished')"><ArrowLeft :size="17" />返回我的错题</button>
        <button class="draft-button" type="button" :disabled="isSaving" @click="save('draft')"><LoaderCircle v-if="savingAction === 'draft'" class="spin" :size="17" /><Save v-else :size="17" />{{ savingAction === 'draft' ? '正在保存…' : '保存草稿' }}</button>
        <button class="confirm-button" type="button" :disabled="isSaving" @click="save('confirmed')"><LoaderCircle v-if="savingAction === 'confirmed'" class="spin" :size="17" /><CheckCircle2 v-else :size="17" />{{ savingAction === 'confirmed' ? '正在确认…' : question.status === 'confirmed' ? '重新确认' : '确认题目' }}</button>
      </div>
    </footer>
  </article>
</template>

<style scoped>
.question-editor { margin-top: 27px; padding: 24px; border: 1px solid #d9e4ef; border-radius: 14px; background: #fff; }
.editor-heading,.structure-heading,.field-heading,.editor-actions { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.eyebrow { margin: 0 0 6px; color: #7189a3; font-size: 12px; font-weight: 700; letter-spacing: .35px; }
.editor-heading h2,.structure-heading h3,.field-heading h3 { margin: 0; color: #29435f; }
.editor-heading h2 { font-size: 20px; }.structure-heading h3,.field-heading h3 { font-size: 16px; }
.editor-heading p:last-child,.structure-heading p { max-width: 680px; margin: 7px 0 0; color: #617991; font-size: 13px; line-height: 1.55; }
.draft-chip { flex: 0 0 auto; padding: 6px 9px; color: #92651e; border-radius: 6px; background: #fff4d7; font-size: 11px; font-weight: 700; }.draft-chip.confirmed { color: #23785d; background: #e8f7f0; }
.editor-error,.editor-success { display: flex; align-items: center; gap: 7px; margin: 16px 0 0; padding: 11px; border-radius: 8px; font-size: 13px; }.editor-error { color: #a84436; background: #fff4f2; }.editor-success { color: #247358; background: #edf9f3; }
.answer-optional-note { display: flex; align-items: flex-start; gap: 9px; margin: 16px 0 0; padding: 12px 14px; color: #4e6d8a; border: 1px solid #d7e6f5; border-radius: 9px; background: #f6faff; font-size: 12px; line-height: 1.55; }.answer-optional-note svg { flex: 0 0 auto; margin-top: 1px; color: #3975cf; }.answer-optional-note span { display: grid; gap: 2px; }.answer-optional-note strong { color: #294f78; font-size: 13px; }
.figure-section { display: grid; grid-template-columns: 1fr auto; gap: 10px 16px; align-items: center; margin-top: 16px; padding: 13px 14px; border: 1px solid #d8e7f5; border-radius: 9px; background: #fbfdff; }.figure-section > div:first-child { display: grid; gap: 3px; }.figure-section strong { color: #355875; font-size: 13px; }.figure-section small,.figure-empty { color: #6d849b; font-size: 11px; font-weight: 500; line-height: 1.5; }.figure-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }.figure-actions button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 6px; padding: 8px 11px; color: #285fae; border: 1px solid #b9d1ef; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; cursor: pointer; }.figure-actions button:first-child { color: #6547bc; border-color: #cfc2f5; background: #faf9ff; }.figure-actions button:disabled { cursor: not-allowed; opacity: .5; }.figure-empty,.figure-list { grid-column: 1 / -1; margin: 0; }.figure-list { display: flex; flex-wrap: wrap; gap: 10px; }.figure-list figure { position: relative; width: min(250px,100%); margin: 0; overflow: hidden; border: 1px solid #d9e4ef; border-radius: 8px; background: #fff; }.figure-list img { display: block; width: 100%; max-height: 180px; object-fit: contain; background: #f3f6f9; }.figure-list figure button { display: inline-flex; min-height: 36px; align-items: center; gap: 4px; margin: 7px; padding: 5px 8px; color: #a84b3d; border: 1px solid #e5bbb4; border-radius: 6px; background: #fff; font-size: 11px; font-weight: 700; cursor: pointer; }
.editor-grid { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 15px; margin-top: 20px; }
.editor-grid > label,.stem-field,.difficulty-field { display: grid; gap: 7px; color: #405a75; font-size: 12px; font-weight: 700; }.editor-grid span { color: #8597a8; font-size: 11px; font-weight: 500; }.wide-field { grid-column: 1 / -1; }
.editor-grid input,.editor-grid textarea,.editor-grid select,.option-row input,.option-row textarea { box-sizing: border-box; width: 100%; color: #2d4662; border: 1px solid #c9d8e6; border-radius: 8px; background: #fff; font: inherit; font-size: 14px; line-height: 1.55; }.editor-grid input,.editor-grid select { min-height: 44px; padding: 0 11px; }.editor-grid textarea { padding: 10px 11px; resize: vertical; }
.table-preview { display: grid; gap: 8px; margin-top: 3px; padding: 12px; border: 1px solid #d7e6f5; border-radius: 9px; background: #f7fbff; }.table-preview > div { display: grid; gap: 3px; }.table-preview strong { color: #355b82; font-size: 12px; }.table-preview small { color: #667f98; font-size: 11px; font-weight: 500; line-height: 1.5; }.formula-preview { background: #fbfdff; }.unconfirmed-warning { display: flex; align-items: flex-start; gap: 8px; margin: 3px 0 0; padding: 10px 12px; color: #a85b19; border: 1px solid #f1cb9d; border-radius: 8px; background: #fff8ec; font-size: 12px; line-height: 1.55; }.unconfirmed-warning svg { flex: 0 0 auto; margin-top: 1px; }.unconfirmed-warning span { display: grid; gap: 2px; }.unconfirmed-warning strong { color: #8a4b14; }
.editor-grid input:focus,.editor-grid textarea:focus,.editor-grid select:focus,.option-row input:focus,.option-row textarea:focus,button:focus-visible { border-color: #2563eb; outline: 3px solid rgba(37,99,235,.17); outline-offset: 1px; }
.difficulty-field { min-width: 0; padding: 0; border: 0; }.difficulty-field legend { margin-bottom: 7px; }.stars { display: flex; min-height: 44px; align-items: center; gap: 3px; }.stars button { display: grid; width: 40px; height: 44px; place-items: center; color: #c7d2df; border: 0; border-radius: 7px; background: transparent; font-size: 24px; cursor: pointer; transition: color .18s ease, background .18s ease; }.stars button.active { color: #f59e0b; }.stars button:hover { background: #fff7e5; }
.options-section,.structure-section { margin-top: 23px; padding: 18px; border: 1px solid #e0e8f0; border-radius: 10px; background: #fbfdff; }
.text-action,.structure-actions button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 5px; padding: 8px 11px; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; cursor: pointer; }
.text-action,.add-part-button,.add-group-button { color: #285fae; border: 1px solid #b9d1ef; }.suggest-button { color: #fff; border: 1px solid #2563eb; background: #2563eb !important; }.structure-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }.structure-actions button:disabled { cursor: wait; opacity: .65; }
.option-list,.part-list { display: grid; gap: 11px; margin-top: 15px; }.option-row { display: grid; grid-template-columns: 40px 48px minmax(0,1fr) 44px; gap: 8px; align-items: center; }.option-row > label:first-child { color: #6f8398; font-size: 11px; font-weight: 700; }.option-row input { min-height: 44px; padding: 0 8px; text-align: center; }.option-row textarea { min-height: 44px; padding: 9px; resize: vertical; }.remove-option { display: grid; width: 44px; height: 44px; place-items: center; color: #9f4b40; border: 0; border-radius: 8px; background: #fff3f0; cursor: pointer; }.empty-options { margin: 13px 0 0; color: #71859a; font-size: 13px; }
.simple-mode-button { justify-self: start; min-height: 44px; padding: 8px 12px; color: #8b534b; border: 1px solid #e5c2bc; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; cursor: pointer; }
.simple-answer-details { margin-top: 23px; overflow: hidden; border: 1px solid #d8e5f2; border-radius: 10px; background: #f8fbff; }.simple-answer-details summary { display: flex; min-height: 46px; box-sizing: border-box; align-items: center; gap: 7px; padding: 12px 16px; color: #355875; font-size: 13px; font-weight: 700; cursor: pointer; }.simple-answer-details summary span { color: #71879c; font-size: 11px; font-weight: 500; }.simple-answer-details summary small { margin-left: auto; padding: 3px 6px; color: #247358; border-radius: 5px; background: #e8f7f0; }.simple-answer-details .answer-grid { margin: 0; padding: 2px 16px 16px; }.answer-photo-section { margin-top: 23px; padding: 17px; border: 1px solid #d8e5f2; border-radius: 10px; background: #fbfdff; }.answer-photo-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }.answer-photo-heading h3 { margin: 0; color: #29435f; font-size: 16px; }.answer-photo-heading p:last-child { max-width: 640px; margin: 6px 0 0; color: #667f98; font-size: 12px; line-height: 1.55; }.answer-photo-heading > button { display: inline-flex; min-height: 44px; flex: 0 0 auto; align-items: center; justify-content: center; gap: 6px; padding: 9px 12px; color: #285fae; border: 1px solid #b9d1ef; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; cursor: pointer; }.answer-photo-heading > button:disabled { cursor: wait; opacity: .6; }.answer-photo-empty { margin: 14px 0 0; padding: 10px 11px; color: #71869a; border-radius: 8px; background: #f4f8fc; font-size: 12px; line-height: 1.55; }.answer-photo-list { display: grid; grid-template-columns: repeat(auto-fill,minmax(170px,1fr)); gap: 11px; margin-top: 14px; }.answer-photo-list figure { margin: 0; overflow: hidden; border: 1px solid #d9e4ef; border-radius: 8px; background: #fff; }.answer-photo-list a { display: block; color: inherit; text-decoration: none; }.answer-photo-list img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; background: #f2f5f8; }.answer-photo-list figcaption { overflow: hidden; padding: 8px 9px; color: #5f7690; font-size: 11px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }.answer-photo-list button { display: inline-flex; width: calc(100% - 16px); min-height: 44px; align-items: center; justify-content: center; gap: 5px; margin: 0 8px 8px; color: #a84b3d; border: 1px solid #e5bbb4; border-radius: 7px; background: #fff; font-size: 11px; font-weight: 700; cursor: pointer; }.metadata-grid { margin-top: 23px; }.editor-actions { align-items: center; margin-top: 24px; padding-top: 17px; border-top: 1px solid #e0e7ee; }.editor-actions p { display: flex; align-items: flex-start; gap: 7px; margin: 0; color: #657b92; font-size: 12px; line-height: 1.5; }.editor-actions p span { color: #2f9a75; font-size: 14px; }.editor-actions p.action-message { max-width: 560px; padding: 9px 11px; border-radius: 8px; font-weight: 700; }.editor-actions p.action-message svg { flex: 0 0 auto; }.editor-actions p.action-message.success { color: #247358; background: #e8f7f0; }.editor-actions p.action-message.error { color: #a7483b; background: #fff0ed; }.editor-actions > div { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 9px; }.editor-actions button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 6px; padding: 9px 13px; border-radius: 8px; font-size: 13px; font-weight: 700; cursor: pointer; }.back-library-button,.draft-button { color: #315f9b; border: 1px solid #b9cee5; background: #fff; }.confirm-button { min-width: 122px; color: #fff; border: 1px solid #f97316; background: #f97316; }.editor-actions button:disabled { cursor: wait; opacity: .6; }
.spin { animation: rotate .8s linear infinite; }@keyframes rotate { to { transform: rotate(360deg); } }.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media (max-width: 760px) {
  .question-editor { margin-top: 18px; padding: 17px; }.editor-heading,.structure-heading,.editor-actions,.answer-photo-heading { align-items: stretch; flex-direction: column; }.draft-chip { align-self: flex-start; }.editor-grid { grid-template-columns: 1fr; gap: 14px; }.wide-field { grid-column: auto; }.figure-section { grid-template-columns: 1fr; }.figure-actions { display: grid; grid-template-columns: 1fr; }.figure-actions button,.answer-photo-heading > button { width: 100%; }.options-section,.structure-section,.answer-photo-section { padding: 15px; }.structure-actions { display: grid; grid-template-columns: 1fr 1fr; }.suggest-button { grid-column: 1 / -1; }.option-row { grid-template-columns: 43px minmax(0,1fr) 44px; }.option-row > label:first-child { display: none; }.option-row textarea { grid-column: 1 / -1; grid-row: 2; }.option-row input { grid-column: 1; grid-row: 1; }.remove-option { grid-column: 3; grid-row: 1; }.answer-photo-list { grid-template-columns: repeat(2,minmax(0,1fr)); }.editor-actions > div { display: grid; grid-template-columns: 1fr 1fr; }.back-library-button { grid-column: 1 / -1; }.editor-actions button { width: 100%; }
}
@media (prefers-reduced-motion: reduce) { .stars button { transition: none; }.spin { animation: none; } }
</style>
