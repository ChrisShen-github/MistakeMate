<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { BookOpenCheck, CircleX, FileQuestion, FileStack, Image, Printer, RefreshCw, Trash2, Upload } from '@lucide/vue'

type MistakeBatch = {
  id: string
  subject: string
  source: string
  title: string
  note: string
  status: string
  created_at: string
  file_count: number
}

const emit = defineEmits<{ upload: []; print: []; open: [batch: MistakeBatch] }>()
const subjects = ['全部学科', '数学', '语文', '英语', '其他']
const activeSubject = ref('全部学科')
const batches = ref<MistakeBatch[]>([])
const isLoading = ref(true)
const errorMessage = ref('')
const actionBatchId = ref('')
const actionMessage = ref('')
const actionError = ref('')

const totalFiles = computed(() => batches.value.reduce((total, batch) => total + batch.file_count, 0))

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function statusLabel(status: string) {
  return {
    uploaded: '待识别',
    queued: '等待识别',
    recognizing: '正在识别',
    review_ready: '待确认',
    confirmed: '已确认',
    ocr_failed: '识别失败',
    ocr_cancelled: '已取消',
  }[status] ?? status
}

function isProcessing(batch: MistakeBatch) { return ['queued', 'recognizing'].includes(batch.status) }
function isActing(batch: MistakeBatch) { return actionBatchId.value === batch.id }

async function cancelRecognition(batch: MistakeBatch) {
  if (isActing(batch)) return
  actionBatchId.value = batch.id
  actionMessage.value = ''
  actionError.value = ''
  try {
    const response = await fetch(`/api/mistakes/${batch.id}/ocr/cancel`, { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '无法取消识别。' }))
    if (!response.ok) throw new Error(payload.detail)
    actionMessage.value = '已取消识别，原图会继续保留。'
    await loadBatches()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '无法取消识别。'
  } finally {
    actionBatchId.value = ''
  }
}

async function restartRecognition(batch: MistakeBatch) {
  if (isActing(batch)) return
  if (!window.confirm('重新识别会覆盖当前题干、选项和 OCR 初稿，并清空已拆分的小问；难度、知识点和错因会保留。确定继续吗？')) return
  actionBatchId.value = batch.id
  actionMessage.value = ''
  actionError.value = ''
  try {
    const response = await fetch(`/api/mistakes/${batch.id}/ocr?replace_question=true`, { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '无法启动重新识别。' }))
    if (!response.ok) throw new Error(payload.detail)
    actionMessage.value = '已重新加入识别队列。'
    await loadBatches()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '无法启动重新识别。'
  } finally {
    actionBatchId.value = ''
  }
}

async function deleteBatch(batch: MistakeBatch) {
  if (isActing(batch)) return
  if (!window.confirm(`删除这道${batch.subject}${batch.source}错题吗？原图、OCR 结果和题目内容都会删除，无法恢复。`)) return
  actionBatchId.value = batch.id
  actionMessage.value = ''
  actionError.value = ''
  try {
    const response = await fetch(`/api/mistakes/${batch.id}`, { method: 'DELETE' })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: '无法删除错题。' }))
      throw new Error(payload.detail)
    }
    actionMessage.value = '错题已删除。'
    await loadBatches()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '无法删除错题。'
  } finally {
    actionBatchId.value = ''
  }
}

async function loadBatches() {
  isLoading.value = true
  errorMessage.value = ''
  const query = activeSubject.value === '全部学科' ? '' : `?subject=${encodeURIComponent(activeSubject.value)}`
  try {
    const response = await fetch(`/api/mistakes${query}`)
    if (!response.ok) throw new Error('暂时无法读取错题，请稍后重试。')
    batches.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '暂时无法读取错题，请稍后重试。'
  } finally {
    isLoading.value = false
  }
}

watch(activeSubject, loadBatches)
onMounted(loadBatches)
</script>

<template>
  <section class="library-page" aria-labelledby="library-heading">
    <header class="library-heading">
      <div>
        <p class="eyebrow">题目归档</p>
        <h1 id="library-heading">我的错题</h1>
        <p>这里保留原图和上传信息。AI 识别完成后，会在这里补齐题目、知识点与复练安排。</p>
      </div>
      <div class="heading-actions"><button class="library-print" type="button" @click="emit('print')"><Printer :size="18" />打印错题</button><button class="library-upload" type="button" @click="emit('upload')"><Upload :size="18" />上传错题</button></div>
    </header>

    <section class="library-summary" aria-label="错题概览">
      <div><span>上传批次</span><strong>{{ batches.length }}<small> 组</small></strong></div>
      <div><span>待处理文件</span><strong>{{ totalFiles }}<small> 个</small></strong></div>
      <p><BookOpenCheck :size="18" />先完成识别，才会进入复练计划。</p>
    </section>
    <p v-if="actionMessage" class="action-feedback success" role="status">{{ actionMessage }}</p>
    <p v-if="actionError" class="action-feedback error" role="alert">{{ actionError }}</p>

    <div class="filter-row" aria-label="按学科筛选">
      <span>学科</span>
      <button
        v-for="subject in subjects"
        :key="subject"
        type="button"
        :class="{ active: activeSubject === subject }"
        :aria-pressed="activeSubject === subject"
        @click="activeSubject = subject"
      >{{ subject }}</button>
    </div>

    <section class="library-list" aria-live="polite" :aria-busy="isLoading">
      <div v-if="isLoading" class="loading-list" aria-label="正在读取错题">
        <div v-for="index in 3" :key="index" class="loading-card"><i></i><span></span><span></span></div>
      </div>

      <div v-else-if="errorMessage" class="state-card error-state" role="alert">
        <RefreshCw :size="24" />
        <div><strong>读取失败</strong><p>{{ errorMessage }}</p></div>
        <button type="button" @click="loadBatches">重试</button>
      </div>

      <div v-else-if="!batches.length" class="state-card empty-state">
        <div class="empty-icon"><FileQuestion :size="27" /></div>
        <strong>{{ activeSubject === '全部学科' ? '还没有上传错题' : `还没有${activeSubject}错题` }}</strong>
        <p>从一张作业照片开始，系统会帮你省掉整理和手抄的时间。</p>
        <button type="button" @click="emit('upload')"><Upload :size="17" />上传第一道错题</button>
      </div>

      <article v-for="batch in batches" v-else :key="batch.id" class="batch-card">
        <div class="batch-icon"><Image :size="22" /></div>
        <div class="batch-main">
          <div class="batch-title"><span class="subject-chip">{{ batch.subject }}</span><strong>{{ batch.title || `${batch.source}错题` }}</strong><span class="status-chip" :class="batch.status">{{ statusLabel(batch.status) }}</span></div>
          <p>{{ batch.note || '暂未填写备注，可在识别结果出来后补充。' }}</p>
          <small>{{ formatDate(batch.created_at) }} · {{ batch.file_count }} 个文件</small>
        </div>
        <div class="batch-actions">
          <button class="batch-action" type="button" :aria-label="`查看${batch.subject}${batch.source}错题`" @click="emit('open', batch)">查看</button>
          <button v-if="isProcessing(batch)" class="batch-action cancel" type="button" :disabled="isActing(batch)" @click="cancelRecognition(batch)"><CircleX :size="16" />{{ isActing(batch) ? '取消中…' : '取消' }}</button>
          <button v-else class="batch-action reocr" type="button" :disabled="isActing(batch)" @click="restartRecognition(batch)"><RefreshCw :size="16" />{{ isActing(batch) ? '处理中…' : '重新识别' }}</button>
          <button class="batch-action delete" type="button" :disabled="isActing(batch)" :aria-label="`删除${batch.subject}${batch.source}错题`" @click="deleteBatch(batch)"><Trash2 :size="16" />删除</button>
        </div>
      </article>
    </section>

    <p class="library-footnote"><FileStack :size="16" />原图保存在本地存储中；删除操作会同时移除原图和识别结果。</p>
  </section>
</template>

<style scoped>
.library-page { max-width: 1200px; margin: 0 auto; padding: 34px 44px 56px; }.library-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; }.eyebrow { margin: 0 0 8px; color: #6a829e; font-size: 12px; font-weight: 700; letter-spacing: .4px; }.library-heading h1 { margin: 0; color: #1e3553; font-size: 32px; letter-spacing: -.7px; }.library-heading p:last-child { max-width: 640px; margin: 10px 0 0; color: #667b92; font-size: 14px; line-height: 1.65; }.library-upload,.empty-state button,.error-state button,.batch-action { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 44px; border: 0; border-radius: 9px; font-size: 13px; font-weight: 700; transition: background .2s ease, color .2s ease, border-color .2s ease; }.library-upload,.empty-state button { padding: 10px 15px; color: #fff; background: #f97316; }.library-upload:hover,.empty-state button:hover { background: #dc5f0b; }.library-summary { display: grid; grid-template-columns: 180px 180px minmax(0,1fr); gap: 1px; margin-top: 28px; overflow: hidden; background: #dce5ef; border: 1px solid #dce5ef; border-radius: 13px; }.library-summary > * { min-height: 106px; padding: 20px; background: #fff; }.library-summary div { display: grid; align-content: center; gap: 6px; }.library-summary span { color: #70849a; font-size: 12px; font-weight: 600; }.library-summary strong { color: #233d5d; font-size: 28px; line-height: 1; }.library-summary small { color: #6d8195; font-size: 12px; font-weight: 500; }.library-summary p { display: flex; align-items: center; gap: 9px; margin: 0; color: #47627e; font-size: 13px; line-height: 1.55; }.library-summary p svg { flex: 0 0 auto; color: #3975cf; }.filter-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 27px 0 15px; }.filter-row > span { margin-right: 4px; color: #627990; font-size: 13px; font-weight: 700; }.filter-row button { min-height: 38px; padding: 7px 12px; color: #536d89; border: 1px solid #d2dfea; border-radius: 8px; background: #fff; font: inherit; font-size: 13px; font-weight: 600; transition: background .2s ease, border-color .2s ease, color .2s ease; }.filter-row button:hover { color: #245ec5; border-color: #9dbde7; background: #f5f9ff; }.filter-row button.active { color: #fff; border-color: #2868cc; background: #2868cc; }.library-list { min-height: 230px; }.batch-card,.state-card { display: flex; align-items: center; gap: 15px; padding: 18px 20px; background: #fff; border: 1px solid #dce5ef; border-radius: 12px; }.batch-card + .batch-card { margin-top: 10px; }.batch-icon,.empty-icon { display: grid; flex: 0 0 auto; place-items: center; color: #3877d4; background: #eaf3ff; border-radius: 10px; }.batch-icon { width: 45px; height: 45px; }.batch-main { display: grid; min-width: 0; flex: 1; gap: 6px; }.batch-title { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }.batch-title strong { color: #29435f; font-size: 14px; }.subject-chip,.status-chip { padding: 3px 7px; border-radius: 5px; font-size: 11px; font-weight: 700; }.subject-chip { color: #2862b9; background: #eaf3ff; }.status-chip { color: #9a6a22; background: #fff5da; }.batch-main p { overflow: hidden; margin: 0; color: #617891; font-size: 13px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }.batch-main small { color: #8798aa; font-size: 11px; }.batch-action { flex: 0 0 auto; min-width: 62px; color: #2864c4; border: 1px solid #b5ceee; background: #fff; }.batch-action:hover { color: #154d9f; border-color: #7ba8de; background: #f6faff; }.state-card { justify-content: center; min-height: 235px; text-align: center; }.empty-state { flex-direction: column; padding: 36px 20px; }.empty-icon { width: 58px; height: 58px; margin-bottom: 2px; }.empty-state strong,.error-state strong { color: #2b4664; font-size: 16px; }.empty-state p,.error-state p { margin: 6px 0 13px; color: #6d8298; font-size: 13px; line-height: 1.6; }.error-state { justify-content: flex-start; text-align: left; }.error-state svg { color: #c24c3e; }.error-state p { margin-bottom: 0; }.error-state button { margin-left: auto; padding: 8px 12px; color: #2b64bf; background: #eff6ff; }.loading-list { display: grid; gap: 10px; }.loading-card { display: grid; grid-template-columns: 45px 1fr; grid-template-rows: 17px 13px; gap: 9px 15px; padding: 18px 20px; border: 1px solid #dce5ef; border-radius: 12px; background: #fff; }.loading-card i,.loading-card span { display: block; border-radius: 6px; background: linear-gradient(90deg,#f1f4f7,#e7edf3,#f1f4f7); background-size: 200% 100%; animation: shimmer 1.25s ease infinite; }.loading-card i { grid-row: span 2; width: 45px; height: 45px; }.loading-card span:first-of-type { width: min(230px,65%); height: 17px; }.loading-card span:last-child { width: min(330px,88%); height: 13px; }@keyframes shimmer { to { background-position: -200% 0; } }.library-footnote { display: flex; align-items: center; gap: 7px; margin: 16px 2px 0; color: #7c8fa2; font-size: 12px; }.library-footnote svg { color: #5980b6; }@media (max-width: 760px) { .library-page { padding: 23px 17px 42px; }.library-heading { align-items: flex-start; flex-direction: column; gap: 17px; }.library-heading h1 { font-size: 28px; }.library-upload { width: 100%; }.library-summary { grid-template-columns: 1fr 1fr; }.library-summary p { grid-column: 1 / -1; min-height: auto; padding: 14px 17px; }.filter-row { margin-top: 22px; }.batch-card { align-items: flex-start; padding: 16px; }.batch-action { align-self: center; min-width: 44px; padding: 7px; font-size: 12px; }.batch-main p { white-space: normal; }.error-state { align-items: flex-start; flex-wrap: wrap; }.error-state button { margin: 0; }.library-footnote { align-items: flex-start; line-height: 1.55; } }@media (prefers-reduced-motion: reduce) { .loading-card i,.loading-card span { animation: none; } }
.status-chip.confirmed { color: #23785d; background: #e8f7f0; }
.status-chip.ocr_failed { color: #a7483b; background: #fff0ed; }
.heading-actions { display: flex; gap: 9px; }
.library-print { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 7px; padding: 10px 13px; color: #315f9b; border: 1px solid #b9d0ef; border-radius: 9px; background: #fff; font-size: 13px; font-weight: 700; cursor: pointer; transition: background .2s ease,border-color .2s ease,color .2s ease; }
.library-print:hover { color: #184f9f; border-color: #789fd3; background: #f7fbff; }
@media (max-width: 760px) { .heading-actions { width: 100%; display: grid; grid-template-columns: 1fr 1fr; }.library-print,.library-upload { width: 100%; } }
.action-feedback { margin: 13px 0 -5px; padding: 10px 13px; border-radius: 9px; font-size: 13px; font-weight: 700; }.action-feedback.success { color: #24745a; border: 1px solid #bfe7d4; background: #edf9f3; }.action-feedback.error { color: #a44338; border: 1px solid #f1c7c0; background: #fff3f1; }.batch-actions { display: flex; flex: 0 0 auto; flex-wrap: wrap; justify-content: flex-end; gap: 7px; }.batch-action { gap: 5px; }.batch-action.cancel { color: #9a6a22; border-color: #e8ca91; background: #fffbef; }.batch-action.reocr { color: #315f9b; border-color: #b9d0ef; background: #f7fbff; }.batch-action.delete { color: #aa4b40; border-color: #e7b9b2; background: #fff; }.batch-action:disabled { cursor: wait; opacity: .58; }.batch-action.cancel:hover { color: #7c5113; border-color: #d6ad5e; background: #fff5d9; }.batch-action.reocr:hover { color: #184f9f; border-color: #789fd3; background: #edf5ff; }.batch-action.delete:hover { color: #8a352d; border-color: #d9988f; background: #fff4f2; }.status-chip.ocr_cancelled { color: #746248; background: #f2eee8; }
@media (max-width: 760px) { .batch-card { flex-wrap: wrap; }.batch-actions { width: 100%; justify-content: stretch; }.batch-actions .batch-action { flex: 1; } }
</style>
