<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, CircleAlert, FileImage, FileText, ImageOff, Info, LoaderCircle, RefreshCw, ScanText } from '@lucide/vue'
import QuestionEditor, { type MistakeQuestion } from './QuestionEditor.vue'

type UploadedFile = { id: string; original_name: string; content_type: string; size: number }
type OcrRun = { engine: string; status: string; text: string; error_message: string; started_at: string | null; completed_at: string | null }
type BatchDetail = { id: string; subject: string; source: string; note: string; status: string; created_at: string; file_count: number; files: UploadedFile[]; ocr: OcrRun | null; questions: MistakeQuestion[] }

const props = defineProps<{ batchId: string }>()
const emit = defineEmits<{ back: [] }>()
const batch = ref<BatchDetail | null>(null)
const isLoading = ref(true)
const isRequestingOcr = ref(false)
const errorMessage = ref('')
let refreshTimer: number | undefined

const imageFiles = computed(() => batch.value?.files.filter((file) => file.content_type.startsWith('image/') && !['image/heic', 'image/heif'].includes(file.content_type)) ?? [])
const otherFiles = computed(() => batch.value?.files.filter((file) => !imageFiles.value.some((image) => image.id === file.id)) ?? [])

function formatSize(size: number) { return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB` }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
function fileUrl(file: UploadedFile) { return `/api/mistakes/${props.batchId}/files/${file.id}` }
function ocrLabel(status?: string) { return ({ queued: '等待识别', running: '正在识别', completed: '识别完成', confirmed: '题目已确认', failed: '识别失败' } as Record<string, string>)[status ?? ''] ?? '尚未识别' }
function clearRefreshTimer() { if (refreshTimer) window.clearTimeout(refreshTimer); refreshTimer = undefined }
function scheduleRefresh() { clearRefreshTimer(); if (batch.value?.ocr && ['queued', 'running'].includes(batch.value.ocr.status)) refreshTimer = window.setTimeout(loadBatch, 2500) }

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

async function startOcr() {
  if (isRequestingOcr.value) return
  isRequestingOcr.value = true
  errorMessage.value = ''
  try {
    const response = await fetch(`/api/mistakes/${props.batchId}/ocr`, { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '无法启动本地识别。' }))
    if (!response.ok) throw new Error(payload.detail)
    await loadBatch()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '无法启动本地识别。'
  } finally {
    isRequestingOcr.value = false
  }
}

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
        <span class="status-chip">{{ ocrLabel(batch.ocr?.status) }}</span>
      </header>

      <section class="review-tip"><Info :size="19" /><div><strong>{{ batch.ocr?.status === 'completed' ? '本地识别已完成，请核对文字' : '原图已保存，可开始本地识别' }}</strong><p>{{ batch.ocr?.status === 'completed' ? '识别结果仅作初稿，尤其是手写字符、公式和步骤，请在后续题目确认页核对。' : '使用开源 PaddleOCR 在本机处理，不会把题图上传到第三方服务。首次识别会下载模型，时间会更长。' }}</p></div><button v-if="!batch.ocr || batch.ocr.status === 'failed'" class="ocr-button" type="button" :disabled="isRequestingOcr" @click="startOcr"><ScanText :size="17" />{{ isRequestingOcr ? '正在启动…' : '开始识别' }}</button><span v-else-if="['queued', 'running'].includes(batch.ocr.status)" class="ocr-progress"><LoaderCircle class="spin" :size="17" />{{ ocrLabel(batch.ocr.status) }}</span></section>

      <template v-if="batch.ocr?.status === 'completed'">
        <QuestionEditor v-for="question in batch.questions" :key="question.id" :batch-id="batch.id" :question="question" @saved="updateQuestion" />
        <section v-if="!batch.questions.length" class="ocr-result" aria-labelledby="ocr-result-heading"><div class="section-heading"><div><p class="eyebrow">OCR 初稿</p><h2 id="ocr-result-heading">识别出的文字</h2></div><span>{{ batch.ocr.engine }}</span></div><p class="empty-draft">正在生成可编辑题目，请稍后刷新。</p></section>
        <details class="ocr-raw"><summary>查看 OCR 原始文字</summary><pre>{{ batch.ocr.text || '没有识别出可编辑文字，请检查图片清晰度后重试。' }}</pre></details>
      </template>
      <section v-else-if="batch.ocr?.status === 'failed'" class="ocr-failed" role="alert"><CircleAlert :size="19" /><div><strong>本地识别未完成</strong><p>{{ batch.ocr.error_message || '请检查模型下载与文件格式后重试。' }}</p></div><button type="button" @click="startOcr"><RefreshCw :size="16" />重试</button></section>

      <section v-if="imageFiles.length" class="preview-section" aria-labelledby="preview-heading"><div class="section-heading"><div><p class="eyebrow">原图预览</p><h2 id="preview-heading">可直接查看的图片</h2></div><span>{{ imageFiles.length }} 张</span></div><div class="image-grid"><a v-for="file in imageFiles" :key="file.id" class="image-card" :href="fileUrl(file)" target="_blank" rel="noreferrer"><img :src="fileUrl(file)" :alt="`原图：${file.original_name}`" /><span>{{ file.original_name }}</span></a></div></section>

      <section v-if="otherFiles.length" class="file-section" aria-labelledby="file-heading"><div class="section-heading"><div><p class="eyebrow">其他原始文件</p><h2 id="file-heading">PDF 与暂不支持预览的图片</h2></div><span>{{ otherFiles.length }} 个</span></div><div class="file-list"><a v-for="file in otherFiles" :key="file.id" :href="fileUrl(file)" target="_blank" rel="noreferrer"><div class="file-icon"><FileText v-if="file.content_type === 'application/pdf'" :size="20" /><FileImage v-else :size="20" /></div><div><strong>{{ file.original_name }}</strong><small>{{ formatSize(file.size) }} · 点击打开原文件</small></div></a></div></section>

      <p v-if="batch.note" class="note"><strong>上传备注</strong>{{ batch.note }}</p>
    </template>
  </section>
</template>

<style scoped>
.review-page { max-width: 1200px; margin: 0 auto; padding: 32px 44px 56px; }.back-button { display: inline-flex; align-items: center; gap: 7px; min-height: 44px; padding: 0; color: #315f9b; border: 0; background: transparent; font-size: 13px; font-weight: 700; }.review-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-top: 18px; }.eyebrow { margin: 0 0 7px; color: #7189a3; font-size: 12px; font-weight: 700; letter-spacing: .4px; }.review-heading h1 { margin: 0; color: #1e3553; font-size: 31px; letter-spacing: -.7px; }.review-heading p:last-child { margin: 10px 0 0; color: #687f97; font-size: 13px; }.status-chip,.section-heading > span { flex: 0 0 auto; padding: 5px 8px; color: #92651e; border-radius: 6px; background: #fff4d7; font-size: 11px; font-weight: 700; }.review-tip { display: flex; align-items: flex-start; gap: 11px; margin-top: 26px; padding: 17px; color: #405f80; border: 1px solid #cfe1f4; border-radius: 12px; background: #f5faff; }.review-tip > svg { flex: 0 0 auto; margin-top: 1px; color: #3975cf; }.review-tip > div { flex: 1; }.review-tip strong { font-size: 13px; }.review-tip p { margin: 5px 0 0; color: #66809a; font-size: 12px; line-height: 1.6; }.ocr-button,.ocr-failed button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 42px; padding: 9px 12px; color: #fff; border: 0; border-radius: 8px; background: #f97316; font-size: 12px; font-weight: 700; }.ocr-button:disabled { cursor: wait; opacity: .65; }.ocr-progress { display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto; min-height: 42px; color: #486a90; font-size: 12px; font-weight: 700; }.ocr-result,.ocr-failed,.preview-section,.file-section,.ocr-raw { margin-top: 27px; padding: 22px; background: #fff; border: 1px solid #dce5ef; border-radius: 13px; }.ocr-result pre,.ocr-raw pre { max-height: 330px; margin: 14px 0 0; padding: 15px; overflow: auto; color: #344e69; border-radius: 9px; background: #f6f9fc; font: 13px/1.7 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; }.ocr-raw { padding: 0; overflow: hidden; }.ocr-raw summary { min-height: 44px; padding: 14px 18px; color: #42617f; font-size: 13px; font-weight: 700; cursor: pointer; }.ocr-raw pre { margin: 0 16px 16px; }.empty-draft { margin: 0; color: #5d7690; font-size: 13px; }.ocr-failed { display: flex; align-items: flex-start; gap: 10px; color: #b04b3d; border-color: #f0d0ca; background: #fffaf9; }.ocr-failed > div { flex: 1; }.ocr-failed strong { color: #864034; font-size: 13px; }.ocr-failed p { margin: 5px 0 0; color: #8d625b; font-size: 12px; line-height: 1.55; }.ocr-failed button { color: #ad493b; background: #fff; border: 1px solid #e1aaa0; }.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 17px; }.section-heading h2 { margin: 0; color: #29435f; font-size: 18px; }.section-heading > span { color: #527395; background: #eef5fd; }.image-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }.image-card { overflow: hidden; color: inherit; border: 1px solid #dfe8f1; border-radius: 10px; background: #fbfdff; text-decoration: none; transition: border-color .2s ease, box-shadow .2s ease; }.image-card:hover { border-color: #92b7e4; box-shadow: 0 5px 14px rgba(39,90,158,.1); }.image-card img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; background: #eef3f8; }.image-card span { display: block; overflow: hidden; padding: 10px; color: #526d89; font-size: 12px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }.file-list { display: grid; gap: 9px; }.file-list a { display: flex; align-items: center; gap: 11px; min-height: 62px; padding: 10px; color: inherit; border: 1px solid #e0e8f0; border-radius: 9px; text-decoration: none; transition: border-color .2s ease, background .2s ease; }.file-list a:hover { border-color: #a9c6e9; background: #f8fbff; }.file-icon { display: grid; width: 38px; height: 38px; place-items: center; color: #3975cf; background: #eaf3ff; border-radius: 9px; }.file-list div:last-child { display: grid; gap: 4px; min-width: 0; }.file-list strong { overflow: hidden; color: #36506c; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.file-list small { color: #8092a4; font-size: 11px; }.note { display: grid; gap: 6px; margin: 18px 2px 0; color: #617891; font-size: 13px; line-height: 1.6; }.note strong { color: #3e5874; font-size: 12px; }.review-loading,.review-error { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 230px; margin-top: 20px; color: #5c748d; background: #fff; border: 1px solid #dce5ef; border-radius: 13px; }.review-error { justify-content: flex-start; padding: 24px; color: #ad4e40; }.review-error div { display: grid; gap: 5px; flex: 1; }.review-error strong { color: #394f68; }.review-error p { margin: 0; color: #6d8298; font-size: 13px; }.review-error button { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 8px 11px; color: #2d64ba; border: 1px solid #b7cfed; border-radius: 8px; background: #fff; font-weight: 700; }.spin { animation: rotate .8s linear infinite; }@keyframes rotate { to { transform: rotate(360deg); } }@media (max-width: 760px) { .review-page { padding: 22px 17px 42px; }.review-heading { align-items: flex-start; flex-direction: column; gap: 12px; }.review-heading h1 { font-size: 27px; }.review-tip,.ocr-result,.ocr-failed,.preview-section,.file-section,.ocr-raw { margin-top: 18px; }.ocr-result,.ocr-failed,.preview-section,.file-section { padding: 17px; }.review-tip { flex-wrap: wrap; }.ocr-button,.ocr-progress { width: 100%; }.image-grid { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 9px; }.review-error { align-items: flex-start; flex-wrap: wrap; }.review-error button { margin-left: 34px; } }@media (prefers-reduced-motion: reduce) { .spin { animation: none; }.image-card,.file-list a { transition: none; } }
</style>
