<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, CheckCircle2, CircleAlert, Eraser, FileImage, FileText, ImageOff, Info, LoaderCircle, RefreshCw, ScanText, Sparkles, Trash2, WandSparkles, X } from '@lucide/vue'
import QuestionEditor from './QuestionEditor.vue'
import ImageCropper, { type CropRegion } from './ImageCropper.vue'
import type { MistakeQuestion } from '../types/questions'

type CleanImage = { id: string; created_at: string; approved_at: string | null }
type UploadedFile = { id: string; original_name: string; content_type: string; size: number; clean_image: CleanImage | null }
type OcrRun = { engine: string; status: string; text: string; error_message: string; started_at: string | null; completed_at: string | null; ai_status: string; ai_text: string; ai_error_message: string; ai_model: string; ai_started_at: string | null; ai_completed_at: string | null }
type BatchDetail = { id: string; subject: string; source: string; note: string; status: string; created_at: string; file_count: number; files: UploadedFile[]; ocr: OcrRun | null; questions: MistakeQuestion[] }

const props = defineProps<{ batchId: string }>()
const emit = defineEmits<{ back: []; 'configure-ai': [] }>()
const batch = ref<BatchDetail | null>(null)
const isLoading = ref(true)
const isRequestingOcr = ref(false)
const isRequestingAi = ref(false)
const aiConfigured = ref(false)
const imageEditConfigured = ref(false)
const cleaningFileId = ref('')
const approvingFileId = ref('')
const compareFile = ref<UploadedFile | null>(null)
const errorMessage = ref('')
const figureTargetQuestionId = ref('')
const figureSource = ref<UploadedFile | null>(null)
const figureCropFile = ref<File | null>(null)
const isSavingFigure = ref(false)
const isAutoExtractingFigure = ref(false)
const figureCaptureMode = ref<'manual' | 'ai'>('manual')
let refreshTimer: number | undefined

const imageFiles = computed(() => batch.value?.files.filter((file) => file.content_type.startsWith('image/') && !['image/heic', 'image/heif'].includes(file.content_type)) ?? [])
const otherFiles = computed(() => batch.value?.files.filter((file) => !imageFiles.value.some((image) => image.id === file.id)) ?? [])
const isCleanWorkflowRunning = computed(() => isCleanWorkflow(batch.value?.ocr) && ['queued', 'running'].includes(batch.value?.ocr?.status ?? ''))

function formatSize(size: number) { return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB` }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
function fileUrl(file: UploadedFile) { return `/api/mistakes/${props.batchId}/files/${file.id}` }
function cleanImageUrl(file: UploadedFile) { return `/api/mistakes/${props.batchId}/files/${file.id}/clean-image` }
function isAiRecognition(ocr?: OcrRun | null) { return ocr?.engine === 'AI 视觉识别' }
function isCleanWorkflow(ocr?: OcrRun | null) { return ocr?.engine === '清洁原图' }
function recognitionName(ocr?: OcrRun | null) { return isCleanWorkflow(ocr) ? '清洁原图' : isAiRecognition(ocr) ? 'AI 视觉识别' : '本地 OCR' }
function ocrLabel(status?: string, ocr?: OcrRun | null) {
  const name = recognitionName(ocr)
  return ({ queued: `${name}等待中`, running: `${name}正在识别`, completed: `${name}已完成`, confirmed: '题目已确认', failed: `${name}识别失败`, cancelled: '识别已取消' } as Record<string, string>)[status ?? ''] ?? '尚未识别'
}
function clearRefreshTimer() { if (refreshTimer) window.clearTimeout(refreshTimer); refreshTimer = undefined }
function scheduleRefresh() { clearRefreshTimer(); if (batch.value?.ocr && ['queued', 'running'].includes(batch.value.ocr.status) || ['queued', 'running'].includes(batch.value?.ocr?.ai_status ?? '')) refreshTimer = window.setTimeout(loadBatch, 2500) }

async function loadBatch() {
  if (!batch.value) isLoading.value = true
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}`)
    const payload = await response.json().catch(() => ({ detail: '暂时无法读取这组错题。' }))
    if (!response.ok) throw new Error(payload.detail)
    batch.value = payload
    void loadAiAvailability()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '暂时无法读取这组错题。'
  } finally {
    isLoading.value = false
    scheduleRefresh()
  }
}

async function loadAiAvailability() {
  try {
    const response = await fetch('/api/settings/ai')
    if (!response.ok) return
    const payload = await response.json()
    aiConfigured.value = Boolean(payload.model && payload.api_key_configured)
    imageEditConfigured.value = Boolean(payload.image_edit_model && payload.api_key_configured)
  } catch {
    aiConfigured.value = false
    imageEditConfigured.value = false
  }
}

function replaceFile(updatedFile: UploadedFile) {
  if (!batch.value) return
  const index = batch.value.files.findIndex((file) => file.id === updatedFile.id)
  if (index >= 0) batch.value.files.splice(index, 1, updatedFile)
}

async function createCleanImage(file: UploadedFile) {
  if (cleaningFileId.value) return
  if (!imageEditConfigured.value) {
    errorMessage.value = '请先在 AI 设置中选择图片修复模型并保存。'
    return
  }
  const action = file.clean_image ? '重新生成会替换当前清洁图，但绝不会覆盖原图。继续吗？' : '原图会发送给你配置的图片修复模型，只生成一张独立的清洁图。请先在生成后核对内容，再用于打印。继续吗？'
  if (!window.confirm(action)) return
  cleaningFileId.value = file.id
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/files/${file.id}/clean-image`, { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '去除笔迹失败，请稍后重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    replaceFile(payload)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '去除笔迹失败，请稍后重试。'
  } finally {
    cleaningFileId.value = ''
  }
}

async function deleteCleanImage(file: UploadedFile) {
  if (!file.clean_image || !window.confirm('删除这张清洁图吗？原图会保留，之后可以重新生成。')) return
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/files/${file.id}/clean-image`, { method: 'DELETE' })
    const payload = await response.json().catch(() => ({ detail: '无法删除清洁图。' }))
    if (!response.ok) throw new Error(payload.detail)
    replaceFile({ ...file, clean_image: null })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '无法删除清洁图。'
  }
}

async function approveCleanImage(file: UploadedFile) {
  if (!file.clean_image || approvingFileId.value) return
  approvingFileId.value = file.id
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/files/${file.id}/clean-image/approve`, { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '确认清洁图失败，请稍后重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    replaceFile(payload)
    if (compareFile.value?.id === file.id) compareFile.value = payload
    if (batch.value && imageFiles.value.every((item) => item.id === file.id ? Boolean(payload.clean_image?.approved_at) : Boolean(item.clean_image?.approved_at))) batch.value.status = 'confirmed'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '确认清洁图失败，请稍后重试。'
  } finally {
    approvingFileId.value = ''
  }
}

async function startOcr(replaceQuestion = false) {
  if (isRequestingOcr.value) return
  if (replaceQuestion && !window.confirm('重新识别会覆盖当前题干、选项和 OCR 答案初稿，并清空已拆分的小问；难度、知识点和错因会保留。确定继续吗？')) return
  isRequestingOcr.value = true
  errorMessage.value = ''
  try {
    const query = replaceQuestion ? '?replace_question=true' : ''
    const response = await fetch(`/api/mistakes/${props.batchId}/ocr${query}`, { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: `无法启动${recognitionName(batch.value?.ocr)}。` }))
    if (!response.ok) throw new Error(payload.detail)
    await loadBatch()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : `无法启动${recognitionName(batch.value?.ocr)}。`
  } finally {
    isRequestingOcr.value = false
  }
}

async function startAiAssist() {
  if (isRequestingAi.value || !batch.value?.ocr) return
  if (!window.confirm('AI 会读取这组原图和本地 OCR 初稿，并将结果单独展示，不会自动覆盖当前题目。继续吗？')) return
  isRequestingAi.value = true
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/ai-ocr`, { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '无法启动 AI 复核。' }))
    if (!response.ok) throw new Error(payload.detail)
    await loadBatch()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '无法启动 AI 复核。'
  } finally {
    isRequestingAi.value = false
  }
}

async function applyAiAssist() {
  if (!batch.value?.ocr?.ai_text || !window.confirm('采用 AI 初稿会覆盖当前题干、选项和小问，但保留原始 OCR 文字。确定继续吗？')) return
  isRequestingAi.value = true
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/ai-ocr/apply`, { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '无法采用 AI 初稿。' }))
    if (!response.ok) throw new Error(payload.detail)
    batch.value = payload
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '无法采用 AI 初稿。'
  } finally {
    isRequestingAi.value = false
  }
}

function aiLabel(status?: string) { return ({ queued: '等待 AI 复核', running: 'AI 正在复核', completed: 'AI 复核完成', failed: 'AI 复核失败' } as Record<string, string>)[status ?? ''] ?? '尚未请求 AI' }

function updateQuestion(question: MistakeQuestion) {
  if (!batch.value) return
  const index = batch.value.questions.findIndex((item) => item.id === question.id)
  if (index >= 0) batch.value.questions.splice(index, 1, question)
  batch.value.status = question.status === 'confirmed' ? 'confirmed' : 'review_ready'
}

function startFigureCapture(questionId: string, mode: 'manual' | 'ai' = 'manual') {
  if (!imageFiles.value.length) return
  figureTargetQuestionId.value = questionId
  figureSource.value = null
  figureCropFile.value = null
  figureCaptureMode.value = mode
  errorMessage.value = ''
  if (mode === 'ai' && imageFiles.value.length === 1) void autoExtractFigure(imageFiles.value[0])
}

function clearFigureCapture() {
  figureTargetQuestionId.value = ''
  figureSource.value = null
  figureCropFile.value = null
  isSavingFigure.value = false
  isAutoExtractingFigure.value = false
  figureCaptureMode.value = 'manual'
}

async function chooseFigureSource(file: UploadedFile) {
  if (figureCaptureMode.value === 'ai') {
    await autoExtractFigure(file)
    return
  }
  errorMessage.value = ''
  try {
    const response = await fetch(fileUrl(file))
    if (!response.ok) throw new Error('无法读取原图，请稍后重试。')
    const blob = await response.blob()
    figureSource.value = file
    figureCropFile.value = new File([blob], file.original_name, { type: blob.type || file.content_type })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '无法读取原图，请稍后重试。'
  }
}

async function autoExtractFigure(file: UploadedFile) {
  if (!figureTargetQuestionId.value || isAutoExtractingFigure.value) return
  isAutoExtractingFigure.value = true
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/questions/${figureTargetQuestionId.value}/figures/ai`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_id: file.id }),
    })
    const payload = await response.json().catch(() => ({ detail: 'AI 自动提取题图失败，请稍后重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    updateQuestion(payload)
    clearFigureCapture()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'AI 自动提取题图失败，请稍后重试。'
  } finally {
    isAutoExtractingFigure.value = false
  }
}

async function saveFigure(region: CropRegion | null) {
  if (!figureTargetQuestionId.value || !figureSource.value || isSavingFigure.value) return
  isSavingFigure.value = true
  errorMessage.value = ''
  const box = region ?? { x: 0, y: 0, width: 1, height: 1 }
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/questions/${figureTargetQuestionId.value}/figures`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_id: figureSource.value.id, ...box }),
    })
    const payload = await response.json().catch(() => ({ detail: '题图保存失败，请稍后重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    updateQuestion(payload)
    clearFigureCapture()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '题图保存失败，请稍后重试。'
    figureCropFile.value = null
  } finally {
    isSavingFigure.value = false
  }
}

async function removeFigure(questionId: string, figureId: string) {
  if (!window.confirm('删除这张题图吗？删除后不会出现在打印页。')) return
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/questions/${questionId}/figures/${figureId}`, { method: 'DELETE' })
    const payload = await response.json().catch(() => ({ detail: '无法删除题图。' }))
    if (!response.ok) throw new Error(payload.detail)
    updateQuestion(payload)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '无法删除题图。'
  }
}

watch(() => props.batchId, () => { clearRefreshTimer(); loadBatch() })
onMounted(loadBatch)
onBeforeUnmount(clearRefreshTimer)
</script>

<template>
  <section class="review-page" aria-labelledby="review-heading">
    <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回我的错题</button>

    <div v-if="isLoading" class="review-loading" aria-live="polite"><LoaderCircle class="spin" :size="22" />正在读取原始文件…</div>

    <section v-else-if="errorMessage" class="review-error" role="alert"><ImageOff :size="24" /><div><strong>无法打开这组错题</strong><p>{{ errorMessage }}</p></div><button type="button" @click="loadBatch"><RefreshCw :size="16" />重试</button></section>

    <template v-else-if="batch">
      <header class="review-heading">
        <div><p class="eyebrow">题目确认</p><h1 id="review-heading">{{ batch.subject }} · {{ batch.source }}错题</h1><p>上传于 {{ formatDate(batch.created_at) }}，共 {{ batch.file_count }} 个原始文件。</p></div>
        <span class="status-chip" :class="{ confirmed: batch.status === 'confirmed' }">{{ batch.status === 'confirmed' ? '题目已确认' : ocrLabel(batch.ocr?.status, batch.ocr) }}</span>
      </header>

      <section class="review-tip" :class="{ confirmed: batch.status === 'confirmed' }"><CheckCircle2 v-if="batch.status === 'confirmed'" :size="19" /><Info v-else :size="19" /><div><strong>{{ batch.status === 'confirmed' ? '题目已确认，已进入错题库' : batch.ocr?.status === 'completed' ? isCleanWorkflow(batch.ocr ?? undefined) ? '清洁原图已生成，请核对图片' : `${recognitionName(batch.ocr)}已完成，请核对文字` : `原图已保存，等待${recognitionName(batch.ocr)}` }}</strong><p>{{ batch.status === 'confirmed' ? '可以继续修改并重新确认；如果识别内容不完整，也可以重新识别原图。' : batch.ocr?.status === 'completed' ? isCleanWorkflow(batch.ocr ?? undefined) ? '这次没有生成可编辑文字；请在下方对照原图和清洁打印图，确认无误后再使用。' : '识别结果仅作初稿，尤其是手写字符、公式和步骤，请在后续题目确认页核对。' : isCleanWorkflow(batch.ocr ?? undefined) ? '原图会发送给你配置的图片修复模型，生成独立的清洁打印图。' : isAiRecognition(batch.ocr) ? '题图将发送到你配置的 AI 服务，直接由视觉模型识别。' : '使用开源 PaddleOCR 在本机处理，不会把题图上传到第三方服务。首次识别会下载模型，时间会更长。' }}</p></div><button v-if="(!batch.ocr || batch.ocr.status === 'failed') && !isCleanWorkflow(batch.ocr ?? undefined)" class="ocr-button" type="button" :disabled="isRequestingOcr" @click="startOcr(false)"><ScanText :size="17" />{{ isRequestingOcr ? '正在启动…' : `开始${recognitionName(batch.ocr)}` }}</button><button v-else-if="batch.ocr?.status === 'completed' && !isCleanWorkflow(batch.ocr ?? undefined)" class="reocr-button" type="button" :disabled="isRequestingOcr" @click="startOcr(true)"><LoaderCircle v-if="isRequestingOcr" class="spin" :size="17" /><RefreshCw v-else :size="17" />{{ isRequestingOcr ? '正在启动…' : `重新${recognitionName(batch.ocr)}` }}</button><span v-else-if="['queued', 'running'].includes(batch.ocr?.status ?? '')" class="ocr-progress"><LoaderCircle class="spin" :size="17" />{{ ocrLabel(batch.ocr?.status, batch.ocr) }}</span></section>

      <section v-if="figureTargetQuestionId && !figureCropFile" class="figure-source-picker" aria-label="选择题图来源"><div><p class="eyebrow">{{ figureCaptureMode === 'ai' ? 'AI 自动提取' : '添加题图' }}</p><h2>{{ figureCaptureMode === 'ai' ? '选择要让 AI 找图的原图' : '选择包含图形的原图' }}</h2><p>{{ figureCaptureMode === 'ai' ? 'AI 会找出坐标轴、几何图或统计图并裁为题图；若没有找到或边界不准，可改用手动截取。' : '选择后可框选坐标轴、几何图或统计图；文字题干仍保留为可编辑文本。' }}</p></div><button type="button" :disabled="isAutoExtractingFigure" @click="clearFigureCapture">取消</button><p v-if="isAutoExtractingFigure" class="figure-extracting" aria-live="polite"><LoaderCircle class="spin" :size="18" />AI 正在分析图片并截取题图，通常需要几秒钟…</p><div class="figure-source-list"><button v-for="file in imageFiles" :key="file.id" type="button" :disabled="isAutoExtractingFigure" @click="chooseFigureSource(file)"><img :src="fileUrl(file)" :alt="`选择原图 ${file.original_name}`" /><span>{{ file.original_name }}</span></button></div></section>

      <template v-if="batch.ocr?.status === 'completed' && !isCleanWorkflow(batch.ocr)">
        <section v-if="!isAiRecognition(batch.ocr)" class="ai-assist-card" aria-labelledby="ai-assist-heading">
          <div class="ai-assist-copy"><div class="ai-icon"><Sparkles :size="19" /></div><div><div class="section-heading"><div><p class="eyebrow">可选步骤</p><h2 id="ai-assist-heading">AI 补全 OCR</h2></div><span>{{ aiLabel(batch.ocr.ai_status) }}</span></div><p>如果本地 OCR 漏了手写字、公式或小问，可以把原图和 OCR 初稿交给你配置的视觉模型复核。AI 结果会单独显示，确认后才会替换题目初稿。</p></div></div>
          <div class="ai-assist-actions"><button v-if="!['queued', 'running'].includes(batch.ocr.ai_status)" class="ai-button" type="button" :disabled="isRequestingAi" @click="startAiAssist"><LoaderCircle v-if="isRequestingAi" class="spin" :size="17" /><WandSparkles v-else :size="17" />{{ isRequestingAi ? '正在启动…' : batch.ocr.ai_status === 'failed' ? '重新 AI 复核' : 'AI 补全识别' }}</button><span v-else class="ocr-progress"><LoaderCircle class="spin" :size="17" />{{ aiLabel(batch.ocr.ai_status) }}</span><button v-if="batch.ocr.ai_status === 'not_requested' && !batch.ocr.ai_text" class="link-button" type="button" @click="emit('configure-ai')">先配置 AI</button></div>
          <p v-if="batch.ocr.ai_status === 'failed'" class="ai-error" role="alert">{{ batch.ocr.ai_error_message || 'AI 复核未完成，请检查设置或服务商返回。' }}</p>
          <template v-if="batch.ocr.ai_status === 'completed' && batch.ocr.ai_text"><details class="ai-result" open><summary>查看 AI 复核结果</summary><pre>{{ batch.ocr.ai_text }}</pre></details><button class="apply-ai-button" type="button" :disabled="isRequestingAi" @click="applyAiAssist"><CheckCircle2 :size="17" />采用 AI 初稿并重新生成题目</button></template>
        </section>
        <QuestionEditor v-for="question in batch.questions" :key="question.id" :batch-id="batch.id" :question="question" :can-add-figure="imageFiles.length > 0" :can-auto-extract-figure="aiConfigured" @saved="updateQuestion" @finished="emit('back')" @add-figure="startFigureCapture(question.id)" @auto-extract-figure="startFigureCapture(question.id, 'ai')" @remove-figure="removeFigure(question.id, $event)" />
        <section v-if="!batch.questions.length" class="ocr-result" aria-labelledby="ocr-result-heading"><div class="section-heading"><div><p class="eyebrow">OCR 初稿</p><h2 id="ocr-result-heading">识别出的文字</h2></div><span>{{ batch.ocr.engine }}</span></div><p class="empty-draft">正在生成可编辑题目，请稍后刷新。</p></section>
        <details class="ocr-raw"><summary>查看{{ recognitionName(batch.ocr) }}原始文字</summary><pre>{{ batch.ocr.text || '没有识别出可编辑文字，请检查图片清晰度后重试。' }}</pre></details>
      </template>
      <section v-else-if="batch.ocr?.status === 'failed'" class="ocr-failed" role="alert"><CircleAlert :size="19" /><div><strong>{{ recognitionName(batch.ocr) }}未完成</strong><p>{{ batch.ocr.error_message || '请检查识别设置、网络和文件格式后重试。' }}</p></div><button type="button" @click="startOcr(false)"><RefreshCw :size="16" />重试</button></section>

      <section v-if="imageFiles.length" class="preview-section" aria-labelledby="preview-heading"><div class="section-heading"><div><p class="eyebrow">原图与清洁打印图</p><h2 id="preview-heading">原图与结果并排核对</h2></div><span>{{ imageFiles.length }} 张</span></div><p class="clean-intro">先检查题干、数字、公式、表格和图形是否完整；确认无误后，点击“确认此清洁图可用”。原图始终保留。</p><p v-if="!imageEditConfigured" class="clean-unavailable">尚未启用图片修复模型。请先前往 AI 设置，加载模型后在“图片修复模型”中选择包含 image 的模型并保存。</p><div class="image-grid"><article v-for="file in imageFiles" :key="file.id" class="image-card" :class="{ paired: Boolean(file.clean_image) }"><div class="image-original"><a class="image-link" :href="fileUrl(file)" target="_blank" rel="noreferrer"><img :src="fileUrl(file)" :alt="`原图：${file.original_name}`" /><span>原图 · {{ file.original_name }}</span></a><div v-if="isCleanWorkflowRunning" class="clean-progress"><LoaderCircle class="spin" :size="16" />{{ file.clean_image ? '正在处理其余原图…' : '正在自动去除笔迹…' }}</div><div v-else class="image-actions"><button class="clean-button" type="button" :disabled="Boolean(cleaningFileId) || !imageEditConfigured" @click="createCleanImage(file)"><LoaderCircle v-if="cleaningFileId === file.id" class="spin" :size="16" /><Eraser v-else :size="16" />{{ cleaningFileId === file.id ? '正在去除笔迹…' : file.clean_image ? '重新生成清洁图' : '去除笔迹' }}</button></div></div><div v-if="file.clean_image" class="clean-result"><a :href="cleanImageUrl(file)" target="_blank" rel="noreferrer"><img :src="cleanImageUrl(file)" :alt="`清洁打印图：${file.original_name}`" /><span>清洁打印图</span></a><div class="clean-result-actions"><button class="compare-button" type="button" @click="compareFile = file">原图与结果对照</button><button v-if="!file.clean_image.approved_at" class="approve-button" type="button" :disabled="Boolean(approvingFileId)" @click="approveCleanImage(file)"><LoaderCircle v-if="approvingFileId === file.id" class="spin" :size="16" /><CheckCircle2 v-else :size="16" />{{ approvingFileId === file.id ? '正在确认…' : '确认此清洁图可用' }}</button><p v-else class="approved-status"><CheckCircle2 :size="16" />已确认清洁图</p><button class="delete-clean-button" type="button" @click="deleteCleanImage(file)"><Trash2 :size="15" />删除清洁图</button></div></div></article></div></section>

      <section v-if="otherFiles.length" class="file-section" aria-labelledby="file-heading"><div class="section-heading"><div><p class="eyebrow">其他原始文件</p><h2 id="file-heading">PDF 与暂不支持预览的图片</h2></div><span>{{ otherFiles.length }} 个</span></div><div class="file-list"><a v-for="file in otherFiles" :key="file.id" :href="fileUrl(file)" target="_blank" rel="noreferrer"><div class="file-icon"><FileText v-if="file.content_type === 'application/pdf'" :size="20" /><FileImage v-else :size="20" /></div><div><strong>{{ file.original_name }}</strong><small>{{ formatSize(file.size) }} · 点击打开原文件</small></div></a></div></section>

      <p v-if="batch.note" class="note"><strong>上传备注</strong>{{ batch.note }}</p>
    </template>
    <div v-if="compareFile?.clean_image" class="compare-overlay" role="dialog" aria-modal="true" aria-label="原图与清洁图对照" @click.self="compareFile = null"><section class="compare-dialog"><header><div><p class="eyebrow">核对图片</p><h2>原图与清洁图</h2><p>重点检查题干、数字、公式、图形和表格有没有遗漏或被改动。</p></div><button type="button" aria-label="关闭对照" @click="compareFile = null"><X :size="20" /></button></header><div class="compare-images"><figure><figcaption>原图</figcaption><img :src="fileUrl(compareFile)" :alt="`原图：${compareFile.original_name}`" /></figure><figure><figcaption>清洁打印图</figcaption><img :src="cleanImageUrl(compareFile)" :alt="`清洁打印图：${compareFile.original_name}`" /></figure></div><footer><button class="secondary-compare-button" type="button" @click="compareFile = null">继续检查</button><button v-if="!compareFile.clean_image.approved_at" class="approve-button" type="button" :disabled="Boolean(approvingFileId)" @click="approveCleanImage(compareFile)"><CheckCircle2 :size="16" />确认此清洁图可用</button><p v-else class="approved-status"><CheckCircle2 :size="16" />已确认清洁图</p></footer></section></div>
    <ImageCropper v-if="figureCropFile" :file="figureCropFile" :initial-region="null" @cancel="clearFigureCapture" @confirm="saveFigure" />
  </section>
</template>

<style scoped>
.review-page { max-width: 1200px; margin: 0 auto; padding: 32px 44px 56px; }.back-button { display: inline-flex; align-items: center; gap: 7px; min-height: 44px; padding: 0; color: #315f9b; border: 0; background: transparent; font-size: 13px; font-weight: 700; }.review-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-top: 18px; }.eyebrow { margin: 0 0 7px; color: #7189a3; font-size: 12px; font-weight: 700; letter-spacing: .4px; }.review-heading h1 { margin: 0; color: #1e3553; font-size: 31px; letter-spacing: -.7px; }.review-heading p:last-child { margin: 10px 0 0; color: #687f97; font-size: 13px; }.status-chip,.section-heading > span { flex: 0 0 auto; padding: 5px 8px; color: #92651e; border-radius: 6px; background: #fff4d7; font-size: 11px; font-weight: 700; }.review-tip { display: flex; align-items: flex-start; gap: 11px; margin-top: 26px; padding: 17px; color: #405f80; border: 1px solid #cfe1f4; border-radius: 12px; background: #f5faff; }.review-tip > svg { flex: 0 0 auto; margin-top: 1px; color: #3975cf; }.review-tip > div { flex: 1; }.review-tip strong { font-size: 13px; }.review-tip p { margin: 5px 0 0; color: #66809a; font-size: 12px; line-height: 1.6; }.ocr-button,.ocr-failed button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 42px; padding: 9px 12px; color: #fff; border: 0; border-radius: 8px; background: #f97316; font-size: 12px; font-weight: 700; }.ocr-button:disabled { cursor: wait; opacity: .65; }.ocr-progress { display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto; min-height: 42px; color: #486a90; font-size: 12px; font-weight: 700; }.ocr-result,.ocr-failed,.preview-section,.file-section,.ocr-raw { margin-top: 27px; padding: 22px; background: #fff; border: 1px solid #dce5ef; border-radius: 13px; }.ocr-result pre,.ocr-raw pre { max-height: 330px; margin: 14px 0 0; padding: 15px; overflow: auto; color: #344e69; border-radius: 9px; background: #f6f9fc; font: 13px/1.7 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; }.ocr-raw { padding: 0; overflow: hidden; }.ocr-raw summary { min-height: 44px; padding: 14px 18px; color: #42617f; font-size: 13px; font-weight: 700; cursor: pointer; }.ocr-raw pre { margin: 0 16px 16px; }.empty-draft { margin: 0; color: #5d7690; font-size: 13px; }.ocr-failed { display: flex; align-items: flex-start; gap: 10px; color: #b04b3d; border-color: #f0d0ca; background: #fffaf9; }.ocr-failed > div { flex: 1; }.ocr-failed strong { color: #864034; font-size: 13px; }.ocr-failed p { margin: 5px 0 0; color: #8d625b; font-size: 12px; line-height: 1.55; }.ocr-failed button { color: #ad493b; background: #fff; border: 1px solid #e1aaa0; }.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 17px; }.section-heading h2 { margin: 0; color: #29435f; font-size: 18px; }.section-heading > span { color: #527395; background: #eef5fd; }.image-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }.image-card { overflow: hidden; color: inherit; border: 1px solid #dfe8f1; border-radius: 10px; background: #fbfdff; text-decoration: none; transition: border-color .2s ease, box-shadow .2s ease; }.image-card:hover { border-color: #92b7e4; box-shadow: 0 5px 14px rgba(39,90,158,.1); }.image-card img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; background: #eef3f8; }.image-card span { display: block; overflow: hidden; padding: 10px; color: #526d89; font-size: 12px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }.file-list { display: grid; gap: 9px; }.file-list a { display: flex; align-items: center; gap: 11px; min-height: 62px; padding: 10px; color: inherit; border: 1px solid #e0e8f0; border-radius: 9px; text-decoration: none; transition: border-color .2s ease, background .2s ease; }.file-list a:hover { border-color: #a9c6e9; background: #f8fbff; }.file-icon { display: grid; width: 38px; height: 38px; place-items: center; color: #3975cf; background: #eaf3ff; border-radius: 9px; }.file-list div:last-child { display: grid; gap: 4px; min-width: 0; }.file-list strong { overflow: hidden; color: #36506c; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.file-list small { color: #8092a4; font-size: 11px; }.note { display: grid; gap: 6px; margin: 18px 2px 0; color: #617891; font-size: 13px; line-height: 1.6; }.note strong { color: #3e5874; font-size: 12px; }.review-loading,.review-error { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 230px; margin-top: 20px; color: #5c748d; background: #fff; border: 1px solid #dce5ef; border-radius: 13px; }.review-error { justify-content: flex-start; padding: 24px; color: #ad4e40; }.review-error div { display: grid; gap: 5px; flex: 1; }.review-error strong { color: #394f68; }.review-error p { margin: 0; color: #6d8298; font-size: 13px; }.review-error button { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 8px 11px; color: #2d64ba; border: 1px solid #b7cfed; border-radius: 8px; background: #fff; font-weight: 700; }.spin { animation: rotate .8s linear infinite; }@keyframes rotate { to { transform: rotate(360deg); } }@media (max-width: 760px) { .review-page { padding: 22px 17px 42px; }.review-heading { align-items: flex-start; flex-direction: column; gap: 12px; }.review-heading h1 { font-size: 27px; }.review-tip,.ocr-result,.ocr-failed,.preview-section,.file-section,.ocr-raw { margin-top: 18px; }.ocr-result,.ocr-failed,.preview-section,.file-section { padding: 17px; }.review-tip { flex-wrap: wrap; }.ocr-button,.ocr-progress { width: 100%; }.image-grid { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 9px; }.review-error { align-items: flex-start; flex-wrap: wrap; }.review-error button { margin-left: 34px; } }@media (prefers-reduced-motion: reduce) { .spin { animation: none; }.image-card,.file-list a { transition: none; } }
.status-chip.confirmed { color: #23785d; background: #e8f7f0; }
.figure-source-picker { display: grid; grid-template-columns: 1fr auto; gap: 12px; margin-top: 20px; padding: 18px; border: 1px solid #b9d7f1; border-radius: 12px; background: #f6fbff; }.figure-source-picker h2 { margin: 0; color: #294f78; font-size: 17px; }.figure-source-picker p:last-child { margin: 6px 0 0; color: #617b95; font-size: 12px; line-height: 1.55; }.figure-source-picker > button { align-self: start; min-height: 40px; padding: 8px 11px; color: #526e89; border: 1px solid #c9d9e8; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; cursor: pointer; }.figure-source-picker > button:disabled,.figure-source-list button:disabled { cursor: wait; opacity: .6; }.figure-extracting { display: flex; grid-column: 1 / -1; align-items: center; gap: 7px; margin: 0; padding: 11px; color: #6547bc; border: 1px solid #ded5fb; border-radius: 8px; background: #fbfaff; font-size: 12px; font-weight: 700; }.figure-source-list { display: grid; grid-column: 1 / -1; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; }.figure-source-list button { display: grid; min-width: 0; overflow: hidden; padding: 0; color: #496784; border: 1px solid #d5e3ef; border-radius: 9px; background: #fff; text-align: left; cursor: pointer; transition: border-color .18s ease, box-shadow .18s ease; }.figure-source-list button:hover { border-color: #6fa1dc; box-shadow: 0 3px 10px rgba(45,94,157,.12); }.figure-source-list img { width: 100%; aspect-ratio: 4 / 3; object-fit: cover; background: #e8eef4; }.figure-source-list span { overflow: hidden; padding: 8px; font-size: 11px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }@media (max-width: 760px) { .figure-source-picker { grid-template-columns: 1fr; }.figure-source-picker > button { width: 100%; }.figure-source-list { grid-template-columns: repeat(2,minmax(0,1fr)); } }@media (prefers-reduced-motion: reduce) { .figure-source-list button { transition: none; } }
.ai-assist-card { margin-top: 27px; padding: 20px 22px; color: #385571; border: 1px solid #ddd4f7; border-radius: 13px; background: #fbfaff; }
.ai-assist-copy { display: flex; gap: 12px; }
.ai-icon { display: grid; width: 38px; height: 38px; flex: 0 0 auto; place-items: center; color: #7558d5; border-radius: 10px; background: #eee8ff; }
.ai-assist-copy > div:last-child { min-width: 0; flex: 1; }
.ai-assist-copy .section-heading { margin-bottom: 7px; }
.ai-assist-card p { margin: 0; color: #6d7593; font-size: 12px; line-height: 1.65; }
.ai-assist-actions { display: flex; align-items: center; gap: 10px; margin: 15px 0 0 50px; }
.ai-button,.apply-ai-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 42px; padding: 9px 13px; color: #fff; border: 0; border-radius: 8px; background: #7558d5; font-size: 12px; font-weight: 800; cursor: pointer; }
.ai-button:hover,.apply-ai-button:hover { background: #6245c3; }
.ai-button:disabled,.apply-ai-button:disabled { cursor: wait; opacity: .65; }
.link-button { min-height: 42px; padding: 8px 6px; color: #5e46ae; border: 0; background: transparent; font-size: 12px; font-weight: 800; cursor: pointer; }
.ai-error { margin: 12px 0 0 50px !important; color: #a34b3e !important; }
.ai-result { margin: 16px 0 0 50px; padding: 0; overflow: hidden; border: 1px solid #e0d9f4; border-radius: 9px; background: #fff; }
.ai-result summary { min-height: 44px; padding: 14px 16px; color: #57468d; font-size: 12px; font-weight: 800; cursor: pointer; }
.ai-result pre { max-height: 330px; margin: 0 15px 15px; padding: 14px; overflow: auto; color: #394b6a; border-radius: 8px; background: #f7f5fd; font: 13px/1.7 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; }
.apply-ai-button { margin: 12px 0 0 50px; color: #fff; background: #2f9a75; }
.apply-ai-button:hover { background: #237d5d; }
.review-tip.confirmed { color: #2a6552; border-color: #bee5d5; background: #f1fbf7; }
.review-tip.confirmed > svg { color: #2f9a75; }
.reocr-button { display: inline-flex; min-height: 44px; flex: 0 0 auto; align-items: center; justify-content: center; gap: 6px; padding: 9px 12px; color: #315f9b; border: 1px solid #a9c6e9; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; cursor: pointer; }
.reocr-button:hover { color: #184f9f; border-color: #789fd3; background: #f7fbff; }
@media (max-width: 760px) { .reocr-button { width: 100%; } .ai-assist-card { padding: 17px; } .ai-assist-actions,.ai-error,.ai-result,.apply-ai-button { margin-left: 0; } .ai-assist-actions { flex-wrap: wrap; } .ai-button { width: 100%; } .link-button { width: 100%; } }
.clean-intro { max-width: 760px; margin: -5px 0 15px; color: #607992; font-size: 12px; line-height: 1.65; }
.clean-unavailable { margin: 0 0 15px; padding: 10px 11px; color: #755b31; border: 1px solid #f0d99b; border-radius: 8px; background: #fff9e9; font-size: 12px; line-height: 1.55; }
.image-link,.clean-result a { display: block; color: inherit; text-decoration: none; }
.image-actions { padding: 0 10px 10px; }
.clean-button,.delete-clean-button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 40px; font-size: 12px; font-weight: 800; cursor: pointer; }
.clean-button { width: 100%; color: #5f42ba; border: 1px solid #cdbef1; border-radius: 8px; background: #fff; }
.clean-button:hover { border-color: #9e84df; background: #faf8ff; }
.clean-button:disabled { cursor: not-allowed; opacity: .55; }
.clean-result { border-top: 1px solid #dfe8f1; background: #f8fbff; }
.clean-result img { border-bottom: 1px solid #e0e8f1; }
.clean-result span { color: #26725b; }
.delete-clean-button { width: calc(100% - 20px); margin: 0 10px 10px; color: #a34b3e; border: 1px solid #ecc6c0; border-radius: 8px; background: #fff; }
.delete-clean-button:hover { background: #fff8f7; }
.image-grid { grid-template-columns: 1fr; }
.image-card.paired { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); }
.image-original { min-width: 0; }
.image-card.paired .clean-result { border-top: 0; border-left: 1px solid #dfe8f1; }
.clean-progress { display: flex; min-height: 44px; align-items: center; justify-content: center; gap: 7px; margin: 0 10px 10px; color: #7253bb; border: 1px solid #d9cdf8; border-radius: 8px; background: #fbfaff; font-size: 12px; font-weight: 800; }
.clean-result-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 10px; }
.clean-result-actions .delete-clean-button { grid-column: 1 / -1; width: 100%; margin: 0; }
.compare-button,.approve-button,.secondary-compare-button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 6px; padding: 8px 10px; border-radius: 8px; font-size: 12px; font-weight: 800; cursor: pointer; }
.compare-button,.secondary-compare-button { color: #315f9b; border: 1px solid #b7cdea; background: #fff; }
.compare-button:hover,.secondary-compare-button:hover { border-color: #7ea8d9; background: #f7fbff; }
.approve-button { color: #fff; border: 1px solid #2b8a67; background: #2b8a67; }
.approve-button:hover { background: #237657; }.approve-button:disabled { cursor: wait; opacity: .65; }
.approved-status { display: flex; grid-column: 1 / -1; min-height: 44px; align-items: center; justify-content: center; gap: 6px; margin: 0; color: #237657; border: 1px solid #bfe3d4; border-radius: 8px; background: #f2fbf7; font-size: 12px; font-weight: 800; }
.compare-overlay { position: fixed; z-index: 100; inset: 0; display: grid; place-items: center; padding: 24px; overflow: auto; background: rgba(20,37,56,.56); }
.compare-dialog { width: min(1100px,100%); max-height: calc(100dvh - 48px); overflow: auto; border-radius: 14px; background: #fff; box-shadow: 0 18px 58px rgba(12,26,43,.32); }.compare-dialog header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 22px 24px 18px; border-bottom: 1px solid #e2e9f0; }.compare-dialog h2 { margin: 0; color: #29435f; font-size: 20px; }.compare-dialog header p:last-child { max-width: 650px; margin: 6px 0 0; color: #688098; font-size: 12px; line-height: 1.6; }.compare-dialog header button { display: grid; width: 42px; height: 42px; flex: 0 0 auto; place-items: center; color: #526d89; border: 1px solid #d8e2eb; border-radius: 8px; background: #fff; cursor: pointer; }.compare-images { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 20px 24px; }.compare-images figure { min-width: 0; margin: 0; overflow: hidden; border: 1px solid #dbe5ee; border-radius: 10px; background: #f8fafc; }.compare-images figcaption { padding: 10px 12px; color: #435f7c; border-bottom: 1px solid #dbe5ee; background: #fff; font-size: 12px; font-weight: 800; }.compare-images img { display: block; width: 100%; max-height: 58dvh; object-fit: contain; background: #eef2f6; }.compare-dialog footer { display: flex; justify-content: flex-end; gap: 9px; padding: 0 24px 22px; }.compare-dialog footer .approved-status { width: auto; padding: 0 12px; }
@media (max-width: 760px) { .image-grid { grid-template-columns: 1fr; }.image-card.paired { grid-template-columns: 1fr; }.image-card.paired .clean-result { border-top: 1px solid #dfe8f1; border-left: 0; }.compare-overlay { align-items: start; padding: 12px; }.compare-dialog { max-height: calc(100dvh - 24px); }.compare-dialog header,.compare-images,.compare-dialog footer { padding-right: 16px; padding-left: 16px; }.compare-images { grid-template-columns: 1fr; gap: 12px; }.compare-images img { max-height: none; }.compare-dialog footer { align-items: stretch; flex-direction: column; }.compare-dialog footer .approve-button,.compare-dialog footer .secondary-compare-button { width: 100%; }.compare-dialog footer .approved-status { width: auto; }.clean-result-actions { grid-template-columns: 1fr; }.approved-status { grid-column: auto; } }
</style>
