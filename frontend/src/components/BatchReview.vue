<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, FileImage, FileText, ImageOff, Info, LoaderCircle, RefreshCw } from '@lucide/vue'

type UploadedFile = { id: string; original_name: string; content_type: string; size: number }
type BatchDetail = { id: string; subject: string; source: string; note: string; status: string; created_at: string; file_count: number; files: UploadedFile[] }

const props = defineProps<{ batchId: string }>()
const emit = defineEmits<{ back: [] }>()
const batch = ref<BatchDetail | null>(null)
const isLoading = ref(true)
const errorMessage = ref('')

const imageFiles = computed(() => batch.value?.files.filter((file) => file.content_type.startsWith('image/') && !['image/heic', 'image/heif'].includes(file.content_type)) ?? [])
const otherFiles = computed(() => batch.value?.files.filter((file) => !imageFiles.value.some((image) => image.id === file.id)) ?? [])

function formatSize(size: number) { return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB` }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
function fileUrl(file: UploadedFile) { return `/api/mistakes/${props.batchId}/files/${file.id}` }

async function loadBatch() {
  isLoading.value = true
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
  }
}

watch(() => props.batchId, loadBatch)
onMounted(loadBatch)
</script>

<template>
  <section class="review-page" aria-labelledby="review-heading">
    <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回我的错题</button>

    <div v-if="isLoading" class="review-loading" aria-live="polite"><LoaderCircle class="spin" :size="22" />正在读取原始文件…</div>

    <section v-else-if="errorMessage" class="review-error" role="alert"><ImageOff :size="24" /><div><strong>无法打开这组错题</strong><p>{{ errorMessage }}</p></div><button type="button" @click="loadBatch"><RefreshCw :size="16" />重试</button></section>

    <template v-else-if="batch">
      <header class="review-heading">
        <div><p class="eyebrow">题目确认</p><h1 id="review-heading">{{ batch.subject }} · {{ batch.source }}错题</h1><p>上传于 {{ formatDate(batch.created_at) }}，共 {{ batch.file_count }} 个原始文件。</p></div>
        <span class="status-chip">{{ batch.status === 'queued' ? '等待识别' : batch.status }}</span>
      </header>

      <section class="review-tip"><Info :size="19" /><div><strong>原图已保存，等待接入识别服务</strong><p>这里会在 OCR 与题目拆分接入后显示可编辑的题干、答案和知识点。现在你可以先核对上传文件是否完整。</p></div></section>

      <section v-if="imageFiles.length" class="preview-section" aria-labelledby="preview-heading"><div class="section-heading"><div><p class="eyebrow">原图预览</p><h2 id="preview-heading">可直接查看的图片</h2></div><span>{{ imageFiles.length }} 张</span></div><div class="image-grid"><a v-for="file in imageFiles" :key="file.id" class="image-card" :href="fileUrl(file)" target="_blank" rel="noreferrer"><img :src="fileUrl(file)" :alt="`原图：${file.original_name}`" /><span>{{ file.original_name }}</span></a></div></section>

      <section v-if="otherFiles.length" class="file-section" aria-labelledby="file-heading"><div class="section-heading"><div><p class="eyebrow">其他原始文件</p><h2 id="file-heading">PDF 与暂不支持预览的图片</h2></div><span>{{ otherFiles.length }} 个</span></div><div class="file-list"><a v-for="file in otherFiles" :key="file.id" :href="fileUrl(file)" target="_blank" rel="noreferrer"><div class="file-icon"><FileText v-if="file.content_type === 'application/pdf'" :size="20" /><FileImage v-else :size="20" /></div><div><strong>{{ file.original_name }}</strong><small>{{ formatSize(file.size) }} · 点击打开原文件</small></div></a></div></section>

      <p v-if="batch.note" class="note"><strong>上传备注</strong>{{ batch.note }}</p>
    </template>
  </section>
</template>

<style scoped>
.review-page { max-width: 1200px; margin: 0 auto; padding: 32px 44px 56px; }.back-button { display: inline-flex; align-items: center; gap: 7px; min-height: 44px; padding: 0; color: #315f9b; border: 0; background: transparent; font-size: 13px; font-weight: 700; }.review-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-top: 18px; }.eyebrow { margin: 0 0 7px; color: #7189a3; font-size: 12px; font-weight: 700; letter-spacing: .4px; }.review-heading h1 { margin: 0; color: #1e3553; font-size: 31px; letter-spacing: -.7px; }.review-heading p:last-child { margin: 10px 0 0; color: #687f97; font-size: 13px; }.status-chip,.section-heading > span { flex: 0 0 auto; padding: 5px 8px; color: #92651e; border-radius: 6px; background: #fff4d7; font-size: 11px; font-weight: 700; }.review-tip { display: flex; gap: 11px; margin-top: 26px; padding: 17px; color: #405f80; border: 1px solid #cfe1f4; border-radius: 12px; background: #f5faff; }.review-tip svg { flex: 0 0 auto; margin-top: 1px; color: #3975cf; }.review-tip strong { font-size: 13px; }.review-tip p { margin: 5px 0 0; color: #66809a; font-size: 12px; line-height: 1.6; }.preview-section,.file-section { margin-top: 27px; padding: 22px; background: #fff; border: 1px solid #dce5ef; border-radius: 13px; }.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 17px; }.section-heading h2 { margin: 0; color: #29435f; font-size: 18px; }.section-heading > span { color: #527395; background: #eef5fd; }.image-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }.image-card { overflow: hidden; color: inherit; border: 1px solid #dfe8f1; border-radius: 10px; background: #fbfdff; text-decoration: none; transition: border-color .2s ease, box-shadow .2s ease; }.image-card:hover { border-color: #92b7e4; box-shadow: 0 5px 14px rgba(39,90,158,.1); }.image-card img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; background: #eef3f8; }.image-card span { display: block; overflow: hidden; padding: 10px; color: #526d89; font-size: 12px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }.file-list { display: grid; gap: 9px; }.file-list a { display: flex; align-items: center; gap: 11px; min-height: 62px; padding: 10px; color: inherit; border: 1px solid #e0e8f0; border-radius: 9px; text-decoration: none; transition: border-color .2s ease, background .2s ease; }.file-list a:hover { border-color: #a9c6e9; background: #f8fbff; }.file-icon { display: grid; width: 38px; height: 38px; place-items: center; color: #3975cf; background: #eaf3ff; border-radius: 9px; }.file-list div:last-child { display: grid; gap: 4px; min-width: 0; }.file-list strong { overflow: hidden; color: #36506c; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.file-list small { color: #8092a4; font-size: 11px; }.note { display: grid; gap: 6px; margin: 18px 2px 0; color: #617891; font-size: 13px; line-height: 1.6; }.note strong { color: #3e5874; font-size: 12px; }.review-loading,.review-error { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 230px; margin-top: 20px; color: #5c748d; background: #fff; border: 1px solid #dce5ef; border-radius: 13px; }.review-error { justify-content: flex-start; padding: 24px; color: #ad4e40; }.review-error div { display: grid; gap: 5px; flex: 1; }.review-error strong { color: #394f68; }.review-error p { margin: 0; color: #6d8298; font-size: 13px; }.review-error button { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 8px 11px; color: #2d64ba; border: 1px solid #b7cfed; border-radius: 8px; background: #fff; font-weight: 700; }.spin { animation: rotate .8s linear infinite; }@keyframes rotate { to { transform: rotate(360deg); } }@media (max-width: 760px) { .review-page { padding: 22px 17px 42px; }.review-heading { align-items: flex-start; flex-direction: column; gap: 12px; }.review-heading h1 { font-size: 27px; }.review-tip,.preview-section,.file-section { margin-top: 18px; }.preview-section,.file-section { padding: 17px; }.image-grid { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 9px; }.review-error { align-items: flex-start; flex-wrap: wrap; }.review-error button { margin-left: 34px; } }@media (prefers-reduced-motion: reduce) { .spin { animation: none; }.image-card,.file-list a { transition: none; } }
</style>
