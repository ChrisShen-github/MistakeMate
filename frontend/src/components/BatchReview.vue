<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, CheckCircle2, CircleAlert, FileImage, FileText, ImageOff, Info, LoaderCircle, RefreshCw, ScanText, Sparkles, WandSparkles } from '@lucide/vue'
import QuestionEditor from './QuestionEditor.vue'
import type { MistakeQuestion } from '../types/questions'

type UploadedFile = { id: string; original_name: string; content_type: string; size: number }
type OcrRun = { engine: string; status: string; text: string; error_message: string; started_at: string | null; completed_at: string | null; ai_status: string; ai_text: string; ai_error_message: string; ai_model: string; ai_started_at: string | null; ai_completed_at: string | null }
type BatchDetail = { id: string; subject: string; source: string; note: string; status: string; created_at: string; file_count: number; files: UploadedFile[]; ocr: OcrRun | null; questions: MistakeQuestion[] }

const props = defineProps<{ batchId: string }>()
const emit = defineEmits<{ back: []; 'configure-ai': [] }>()
const batch = ref<BatchDetail | null>(null)
const isLoading = ref(true)
const isRequestingOcr = ref(false)
const isRequestingAi = ref(false)
const errorMessage = ref('')
let refreshTimer: number | undefined

const imageFiles = computed(() => batch.value?.files.filter((file) => file.content_type.startsWith('image/') && !['image/heic', 'image/heif'].includes(file.content_type)) ?? [])
const otherFiles = computed(() => batch.value?.files.filter((file) => !imageFiles.value.some((image) => image.id === file.id)) ?? [])

function formatSize(size: number) { return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB` }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
function fileUrl(file: UploadedFile) { return `/api/mistakes/${props.batchId}/files/${file.id}` }
function isAiRecognition(ocr?: OcrRun | null) { return ocr?.engine === 'AI 视觉识别' }
function recognitionName(ocr?: OcrRun | null) { return isAiRecognition(ocr) ? 'AI 视觉识别' : '本地 OCR' }
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
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '暂时无法读取这组错题。'
  } finally {
    isLoading.value = false
    scheduleRefresh()
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

      <section class="review-tip" :class="{ confirmed: batch.status === 'confirmed' }"><CheckCircle2 v-if="batch.status === 'confirmed'" :size="19" /><Info v-else :size="19" /><div><strong>{{ batch.status === 'confirmed' ? '题目已确认，已进入错题库' : batch.ocr?.status === 'completed' ? `${recognitionName(batch.ocr)}已完成，请核对文字` : `原图已保存，等待${recognitionName(batch.ocr)}` }}</strong><p>{{ batch.status === 'confirmed' ? '可以继续修改并重新确认；如果识别内容不完整，也可以重新识别原图。' : batch.ocr?.status === 'completed' ? '识别结果仅作初稿，尤其是手写字符、公式和步骤，请在后续题目确认页核对。' : isAiRecognition(batch.ocr) ? '题图将发送到你配置的 AI 服务，直接由视觉模型识别。' : '使用开源 PaddleOCR 在本机处理，不会把题图上传到第三方服务。首次识别会下载模型，时间会更长。' }}</p></div><button v-if="!batch.ocr || batch.ocr.status === 'failed'" class="ocr-button" type="button" :disabled="isRequestingOcr" @click="startOcr(false)"><ScanText :size="17" />{{ isRequestingOcr ? '正在启动…' : `开始${recognitionName(batch.ocr)}` }}</button><button v-else-if="batch.ocr.status === 'completed'" class="reocr-button" type="button" :disabled="isRequestingOcr" @click="startOcr(true)"><LoaderCircle v-if="isRequestingOcr" class="spin" :size="17" /><RefreshCw v-else :size="17" />{{ isRequestingOcr ? '正在启动…' : `重新${recognitionName(batch.ocr)}` }}</button><span v-else-if="['queued', 'running'].includes(batch.ocr.status)" class="ocr-progress"><LoaderCircle class="spin" :size="17" />{{ ocrLabel(batch.ocr.status, batch.ocr) }}</span></section>

      <template v-if="batch.ocr?.status === 'completed'">
        <section v-if="!isAiRecognition(batch.ocr)" class="ai-assist-card" aria-labelledby="ai-assist-heading">
          <div class="ai-assist-copy"><div class="ai-icon"><Sparkles :size="19" /></div><div><div class="section-heading"><div><p class="eyebrow">可选步骤</p><h2 id="ai-assist-heading">AI 补全 OCR</h2></div><span>{{ aiLabel(batch.ocr.ai_status) }}</span></div><p>如果本地 OCR 漏了手写字、公式或小问，可以把原图和 OCR 初稿交给你配置的视觉模型复核。AI 结果会单独显示，确认后才会替换题目初稿。</p></div></div>
          <div class="ai-assist-actions"><button v-if="!['queued', 'running'].includes(batch.ocr.ai_status)" class="ai-button" type="button" :disabled="isRequestingAi" @click="startAiAssist"><LoaderCircle v-if="isRequestingAi" class="spin" :size="17" /><WandSparkles v-else :size="17" />{{ isRequestingAi ? '正在启动…' : batch.ocr.ai_status === 'failed' ? '重新 AI 复核' : 'AI 补全识别' }}</button><span v-else class="ocr-progress"><LoaderCircle class="spin" :size="17" />{{ aiLabel(batch.ocr.ai_status) }}</span><button v-if="batch.ocr.ai_status === 'not_requested' && !batch.ocr.ai_text" class="link-button" type="button" @click="emit('configure-ai')">先配置 AI</button></div>
          <p v-if="batch.ocr.ai_status === 'failed'" class="ai-error" role="alert">{{ batch.ocr.ai_error_message || 'AI 复核未完成，请检查设置或服务商返回。' }}</p>
          <template v-if="batch.ocr.ai_status === 'completed' && batch.ocr.ai_text"><details class="ai-result" open><summary>查看 AI 复核结果</summary><pre>{{ batch.ocr.ai_text }}</pre></details><button class="apply-ai-button" type="button" :disabled="isRequestingAi" @click="applyAiAssist"><CheckCircle2 :size="17" />采用 AI 初稿并重新生成题目</button></template>
        </section>
        <QuestionEditor v-for="question in batch.questions" :key="question.id" :batch-id="batch.id" :question="question" @saved="updateQuestion" @finished="emit('back')" />
        <section v-if="!batch.questions.length" class="ocr-result" aria-labelledby="ocr-result-heading"><div class="section-heading"><div><p class="eyebrow">OCR 初稿</p><h2 id="ocr-result-heading">识别出的文字</h2></div><span>{{ batch.ocr.engine }}</span></div><p class="empty-draft">正在生成可编辑题目，请稍后刷新。</p></section>
        <details class="ocr-raw"><summary>查看{{ recognitionName(batch.ocr) }}原始文字</summary><pre>{{ batch.ocr.text || '没有识别出可编辑文字，请检查图片清晰度后重试。' }}</pre></details>
      </template>
      <section v-else-if="batch.ocr?.status === 'failed'" class="ocr-failed" role="alert"><CircleAlert :size="19" /><div><strong>{{ recognitionName(batch.ocr) }}未完成</strong><p>{{ batch.ocr.error_message || '请检查识别设置、网络和文件格式后重试。' }}</p></div><button type="button" @click="startOcr(false)"><RefreshCw :size="16" />重试</button></section>

      <section v-if="imageFiles.length" class="preview-section" aria-labelledby="preview-heading"><div class="section-heading"><div><p class="eyebrow">原图预览</p><h2 id="preview-heading">可直接查看的图片</h2></div><span>{{ imageFiles.length }} 张</span></div><div class="image-grid"><a v-for="file in imageFiles" :key="file.id" class="image-card" :href="fileUrl(file)" target="_blank" rel="noreferrer"><img :src="fileUrl(file)" :alt="`原图：${file.original_name}`" /><span>{{ file.original_name }}</span></a></div></section>

      <section v-if="otherFiles.length" class="file-section" aria-labelledby="file-heading"><div class="section-heading"><div><p class="eyebrow">其他原始文件</p><h2 id="file-heading">PDF 与暂不支持预览的图片</h2></div><span>{{ otherFiles.length }} 个</span></div><div class="file-list"><a v-for="file in otherFiles" :key="file.id" :href="fileUrl(file)" target="_blank" rel="noreferrer"><div class="file-icon"><FileText v-if="file.content_type === 'application/pdf'" :size="20" /><FileImage v-else :size="20" /></div><div><strong>{{ file.original_name }}</strong><small>{{ formatSize(file.size) }} · 点击打开原文件</small></div></a></div></section>

      <p v-if="batch.note" class="note"><strong>上传备注</strong>{{ batch.note }}</p>
    </template>
  </section>
</template>

<style scoped>
.review-page { max-width: 1200px; margin: 0 auto; padding: 32px 44px 56px; }.back-button { display: inline-flex; align-items: center; gap: 7px; min-height: 44px; padding: 0; color: #315f9b; border: 0; background: transparent; font-size: 13px; font-weight: 700; }.review-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-top: 18px; }.eyebrow { margin: 0 0 7px; color: #7189a3; font-size: 12px; font-weight: 700; letter-spacing: .4px; }.review-heading h1 { margin: 0; color: #1e3553; font-size: 31px; letter-spacing: -.7px; }.review-heading p:last-child { margin: 10px 0 0; color: #687f97; font-size: 13px; }.status-chip,.section-heading > span { flex: 0 0 auto; padding: 5px 8px; color: #92651e; border-radius: 6px; background: #fff4d7; font-size: 11px; font-weight: 700; }.review-tip { display: flex; align-items: flex-start; gap: 11px; margin-top: 26px; padding: 17px; color: #405f80; border: 1px solid #cfe1f4; border-radius: 12px; background: #f5faff; }.review-tip > svg { flex: 0 0 auto; margin-top: 1px; color: #3975cf; }.review-tip > div { flex: 1; }.review-tip strong { font-size: 13px; }.review-tip p { margin: 5px 0 0; color: #66809a; font-size: 12px; line-height: 1.6; }.ocr-button,.ocr-failed button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 42px; padding: 9px 12px; color: #fff; border: 0; border-radius: 8px; background: #f97316; font-size: 12px; font-weight: 700; }.ocr-button:disabled { cursor: wait; opacity: .65; }.ocr-progress { display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto; min-height: 42px; color: #486a90; font-size: 12px; font-weight: 700; }.ocr-result,.ocr-failed,.preview-section,.file-section,.ocr-raw { margin-top: 27px; padding: 22px; background: #fff; border: 1px solid #dce5ef; border-radius: 13px; }.ocr-result pre,.ocr-raw pre { max-height: 330px; margin: 14px 0 0; padding: 15px; overflow: auto; color: #344e69; border-radius: 9px; background: #f6f9fc; font: 13px/1.7 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; }.ocr-raw { padding: 0; overflow: hidden; }.ocr-raw summary { min-height: 44px; padding: 14px 18px; color: #42617f; font-size: 13px; font-weight: 700; cursor: pointer; }.ocr-raw pre { margin: 0 16px 16px; }.empty-draft { margin: 0; color: #5d7690; font-size: 13px; }.ocr-failed { display: flex; align-items: flex-start; gap: 10px; color: #b04b3d; border-color: #f0d0ca; background: #fffaf9; }.ocr-failed > div { flex: 1; }.ocr-failed strong { color: #864034; font-size: 13px; }.ocr-failed p { margin: 5px 0 0; color: #8d625b; font-size: 12px; line-height: 1.55; }.ocr-failed button { color: #ad493b; background: #fff; border: 1px solid #e1aaa0; }.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 17px; }.section-heading h2 { margin: 0; color: #29435f; font-size: 18px; }.section-heading > span { color: #527395; background: #eef5fd; }.image-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }.image-card { overflow: hidden; color: inherit; border: 1px solid #dfe8f1; border-radius: 10px; background: #fbfdff; text-decoration: none; transition: border-color .2s ease, box-shadow .2s ease; }.image-card:hover { border-color: #92b7e4; box-shadow: 0 5px 14px rgba(39,90,158,.1); }.image-card img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; background: #eef3f8; }.image-card span { display: block; overflow: hidden; padding: 10px; color: #526d89; font-size: 12px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }.file-list { display: grid; gap: 9px; }.file-list a { display: flex; align-items: center; gap: 11px; min-height: 62px; padding: 10px; color: inherit; border: 1px solid #e0e8f0; border-radius: 9px; text-decoration: none; transition: border-color .2s ease, background .2s ease; }.file-list a:hover { border-color: #a9c6e9; background: #f8fbff; }.file-icon { display: grid; width: 38px; height: 38px; place-items: center; color: #3975cf; background: #eaf3ff; border-radius: 9px; }.file-list div:last-child { display: grid; gap: 4px; min-width: 0; }.file-list strong { overflow: hidden; color: #36506c; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.file-list small { color: #8092a4; font-size: 11px; }.note { display: grid; gap: 6px; margin: 18px 2px 0; color: #617891; font-size: 13px; line-height: 1.6; }.note strong { color: #3e5874; font-size: 12px; }.review-loading,.review-error { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 230px; margin-top: 20px; color: #5c748d; background: #fff; border: 1px solid #dce5ef; border-radius: 13px; }.review-error { justify-content: flex-start; padding: 24px; color: #ad4e40; }.review-error div { display: grid; gap: 5px; flex: 1; }.review-error strong { color: #394f68; }.review-error p { margin: 0; color: #6d8298; font-size: 13px; }.review-error button { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 8px 11px; color: #2d64ba; border: 1px solid #b7cfed; border-radius: 8px; background: #fff; font-weight: 700; }.spin { animation: rotate .8s linear infinite; }@keyframes rotate { to { transform: rotate(360deg); } }@media (max-width: 760px) { .review-page { padding: 22px 17px 42px; }.review-heading { align-items: flex-start; flex-direction: column; gap: 12px; }.review-heading h1 { font-size: 27px; }.review-tip,.ocr-result,.ocr-failed,.preview-section,.file-section,.ocr-raw { margin-top: 18px; }.ocr-result,.ocr-failed,.preview-section,.file-section { padding: 17px; }.review-tip { flex-wrap: wrap; }.ocr-button,.ocr-progress { width: 100%; }.image-grid { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 9px; }.review-error { align-items: flex-start; flex-wrap: wrap; }.review-error button { margin-left: 34px; } }@media (prefers-reduced-motion: reduce) { .spin { animation: none; }.image-card,.file-list a { transition: none; } }
.status-chip.confirmed { color: #23785d; background: #e8f7f0; }
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
</style>
