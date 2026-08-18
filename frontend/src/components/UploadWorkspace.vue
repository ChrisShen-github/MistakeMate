<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, CheckCircle2, Crop, FileImage, FileText, ImagePlus, Link2, LoaderCircle, LockKeyhole, ScanText, Sparkles, Trash2, Unlink, UploadCloud } from '@lucide/vue'
import ImageCropper, { type CropRegion } from './ImageCropper.vue'

const props = defineProps<{ notebookName: string }>()
const emit = defineEmits<{ back: []; queued: [count: number]; 'configure-ai': [] }>()
const input = ref<HTMLInputElement | null>(null)
const files = ref<File[]>([])
const cropRegions = ref<(CropRegion | null)[]>([])
const mergedGroups = ref<number[][]>([])
const isSelectingMerge = ref(false)
const selectedMergeIndexes = ref<number[]>([])
const activeCropIndex = ref<number | null>(null)
const isDragging = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')
const subject = ref('数学')
const source = ref('作业')
const note = ref('')
const recognitionMode = ref<'local' | 'ai'>('ai')
const aiConfigured = ref(false)
const canSubmit = computed(() => files.value.length > 0 && !isSubmitting.value && (recognitionMode.value === 'local' || aiConfigured.value))
const uploadGroups = computed(() => {
  const included = new Set<number>()
  const groups = mergedGroups.value
    .map((group) => [...new Set(group)].filter((index) => index >= 0 && index < files.value.length).sort((a, b) => a - b))
    .filter((group) => group.length > 1)
    .map((group) => { group.forEach((index) => included.add(index)); return group })
  files.value.forEach((_, index) => { if (!included.has(index)) groups.push([index]) })
  return groups.sort((left, right) => left[0] - right[0])
})
const questionCount = computed(() => uploadGroups.value.length)
const selectedMergeCount = computed(() => selectedMergeIndexes.value.length)
const canApplyMerge = computed(() => selectedMergeCount.value >= 2 && selectedMergeCount.value <= 8)
const mergeSelectionDescription = computed(() => {
  if (selectedMergeCount.value === 0) return '勾选要合并成同一道题的图片。'
  if (selectedMergeCount.value === 1) return '再选择至少 1 张图片。'
  if (selectedMergeCount.value > 8) return '同一道题最多可合并 8 张图片。'
  return `已选 ${selectedMergeCount.value} 张，将按上传顺序合并为 1 道题。`
})
const groupByFileIndex = computed(() => {
  const groups = new Map<number, number[]>()
  mergedGroups.value.forEach((group) => group.forEach((index) => groups.set(index, group)))
  return groups
})

function chooseFiles() { input.value?.click() }
function addFiles(incoming: FileList | File[]) {
  errorMessage.value = ''
  const supportedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif', 'application/pdf']
  const supportedExtensions = ['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif', 'pdf']
  const validFiles = Array.from(incoming).filter((file) => supportedTypes.includes(file.type) || supportedExtensions.includes(file.name.split('.').pop()?.toLowerCase() ?? '')).filter((file) => file.size <= 20 * 1024 * 1024)
  if (validFiles.length !== incoming.length) errorMessage.value = '仅支持图片或 PDF，单个文件不能超过 20 MB。'
  const unique = validFiles.filter((file) => !files.value.some((saved) => saved.name === file.name && saved.size === file.size))
  files.value = [...files.value, ...unique].slice(0, 12)
  cropRegions.value = [...cropRegions.value, ...unique.map(() => null)].slice(0, 12)
  if (files.value.length === 12 && unique.length > 0) errorMessage.value = '一次最多添加 12 个文件，其余文件未加入。'
}
function onInputChange(event: Event) { const target = event.target as HTMLInputElement; if (target.files) addFiles(target.files); target.value = '' }
function onDrop(event: DragEvent) { isDragging.value = false; if (event.dataTransfer?.files) addFiles(event.dataTransfer.files) }
function removeFile(index: number) {
  files.value.splice(index, 1)
  cropRegions.value.splice(index, 1)
  mergedGroups.value = mergedGroups.value
    .map((group) => group.filter((item) => item !== index).map((item) => item > index ? item - 1 : item))
    .filter((group) => group.length > 1)
  selectedMergeIndexes.value = selectedMergeIndexes.value.filter((item) => item !== index).map((item) => item > index ? item - 1 : item)
  errorMessage.value = ''
}
function startMergeSelection() { isSelectingMerge.value = true; selectedMergeIndexes.value = [] }
function cancelMergeSelection() { isSelectingMerge.value = false; selectedMergeIndexes.value = [] }
function toggleMergeSelection(index: number) {
  selectedMergeIndexes.value = selectedMergeIndexes.value.includes(index)
    ? selectedMergeIndexes.value.filter((item) => item !== index)
    : [...selectedMergeIndexes.value, index].sort((left, right) => left - right)
}
function applyMergeSelection() {
  if (!canApplyMerge.value) return
  const selected = [...selectedMergeIndexes.value].sort((left, right) => left - right)
  const selectedSet = new Set(selected)
  mergedGroups.value = [
    ...mergedGroups.value.map((group) => group.filter((index) => !selectedSet.has(index))).filter((group) => group.length > 1),
    selected,
  ].sort((left, right) => left[0] - right[0])
  cancelMergeSelection()
}
function mergeGroupFor(index: number) { return groupByFileIndex.value.get(index) }
function isMergeGroupStart(index: number) {
  const group = mergeGroupFor(index)
  return Boolean(group && group[0] === index)
}
function splitMergeGroup(index: number) {
  const group = mergeGroupFor(index)
  if (!group) return
  mergedGroups.value = mergedGroups.value.filter((candidate) => candidate !== group)
}
function canCrop(file: File) { return ['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || ['jpg', 'jpeg', 'png', 'webp'].includes(file.name.split('.').pop()?.toLowerCase() ?? '') }
function openCrop(index: number) { activeCropIndex.value = index }
function saveCrop(region: CropRegion | null) { if (activeCropIndex.value !== null) cropRegions.value[activeCropIndex.value] = region; activeCropIndex.value = null }
function formatSize(size: number) { return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB` }
function selectRecognitionMode(mode: 'local' | 'ai') { recognitionMode.value = mode; errorMessage.value = '' }
async function loadAiAvailability() {
  try {
    const response = await fetch('/api/settings/ai')
    if (!response.ok) return
    const payload = await response.json()
    aiConfigured.value = Boolean(payload.model && payload.api_key_configured)
  } catch { /* The backend validates again when the upload starts. */ }
}
async function queueRecognition() {
  if (!canSubmit.value) return
  isSubmitting.value = true
  errorMessage.value = ''
  const formData = new FormData()
  formData.set('subject', subject.value)
  formData.set('source', source.value)
  formData.set('note', note.value.trim())
  formData.set('recognition_mode', recognitionMode.value)
  formData.set('crop_regions', JSON.stringify(cropRegions.value))
  formData.set('merge_groups', JSON.stringify(uploadGroups.value))
  files.value.forEach((file) => formData.append('files', file))
  try {
    const response = await fetch('/api/uploads', { method: 'POST', body: formData })
    const payload = await response.json().catch(() => ({ detail: '上传失败，请稍后重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    const count = Array.isArray(payload.batch_ids) ? payload.batch_ids.length : payload.file_count as number
    files.value = []
    cropRegions.value = []
    mergedGroups.value = []
    cancelMergeSelection()
    emit('queued', count)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '上传失败，请稍后重试。'
  } finally {
    isSubmitting.value = false
  }
}

onMounted(loadAiAvailability)
</script>

<template>
  <section class="upload-page" aria-labelledby="upload-heading">
    <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回今日任务</button>
    <header class="upload-intro"><p class="eyebrow">添加到{{ props.notebookName }}</p><h1 id="upload-heading">上传错题</h1><p>上传试卷、作业或错题照片。默认每张图片生成一道题；需要时可任选多张图片合并后再识别。</p></header>
    <ol class="upload-steps" aria-label="上传步骤"><li class="active"><span>1</span><strong>上传文件</strong><small>图片或 PDF</small></li><li><span>2</span><strong>检查题目</strong><small>裁切与补充信息</small></li><li><span>3</span><strong>整理归档</strong><small>知识点与复练建议</small></li></ol>

    <div class="upload-layout">
      <section class="upload-card" aria-labelledby="file-heading">
        <div class="section-title"><div><p class="section-kicker">第一步</p><h2 id="file-heading">选择错题图片</h2></div><span class="file-count">{{ files.length }}/12</span></div>
        <div class="drop-zone" :class="{ dragging: isDragging }" aria-describedby="upload-tip upload-error" @dragenter.prevent="isDragging = true" @dragover.prevent="isDragging = true" @dragleave.prevent="isDragging = false" @drop.prevent="onDrop">
          <div class="drop-icon"><UploadCloud :size="27" /></div><strong>拖入图片，或点这里选择文件</strong><span id="upload-tip">支持 JPG、PNG、WebP、HEIC、PDF；需要时可任选图片组合为一道题</span><button class="choose-button" type="button" @click.stop="chooseFiles"><ImagePlus :size="17" />选择文件</button><input ref="input" class="sr-only" type="file" accept=".jpg,.jpeg,.png,.webp,.heic,.heif,.pdf" multiple @change="onInputChange" />
        </div>
        <p v-if="errorMessage" id="upload-error" class="upload-error" role="alert">{{ errorMessage }}</p>
        <div v-if="files.length" class="file-list" aria-label="待识别文件">
          <div class="file-list-head">
            <div><strong>{{ isSelectingMerge ? '选择要合并的图片' : '待识别文件' }}</strong><span>{{ isSelectingMerge ? '可任选图片，系统会按上传顺序合并' : `共 ${files.length} 张图片，将生成 ${questionCount} 道题` }}</span></div>
            <button v-if="!isSelectingMerge" class="merge-mode-button" type="button" :disabled="files.length < 2" @click="startMergeSelection"><Link2 :size="16" />合并图片</button>
            <button v-else class="cancel-merge-button" type="button" @click="cancelMergeSelection">取消</button>
          </div>
          <template v-for="(file, index) in files" :key="`${file.name}-${file.size}`">
            <div v-if="!isSelectingMerge && isMergeGroupStart(index)" class="merge-group-label"><span><Link2 :size="15" />已合并 {{ mergeGroupFor(index)?.length }} 张图片 · 识别为 1 道题</span><button type="button" @click="splitMergeGroup(index)"><Unlink :size="14" />拆分</button></div>
            <article class="file-row" :class="{ selected: selectedMergeIndexes.includes(index), grouped: Boolean(mergeGroupFor(index)) }">
              <label v-if="isSelectingMerge" class="merge-file-checkbox"><input type="checkbox" :checked="selectedMergeIndexes.includes(index)" @change="toggleMergeSelection(index)" /><span>选择第 {{ index + 1 }} 张</span></label>
              <div class="file-icon"><FileText v-if="file.type === 'application/pdf'" :size="20" /><FileImage v-else :size="20" /></div>
              <div class="file-info"><strong>{{ file.name }}</strong><span>{{ formatSize(file.size) }} · {{ cropRegions[index] ? '已截取识别范围' : '识别整张图片' }}</span></div>
              <button v-if="canCrop(file)" class="crop-button" type="button" :aria-label="`截取 ${file.name} 的识别范围`" @click="openCrop(index)"><Crop :size="16" />{{ cropRegions[index] ? '调整范围' : '截取范围' }}</button><button class="remove-button" type="button" :aria-label="`移除 ${file.name}`" @click="removeFile(index)"><Trash2 :size="17" /></button>
            </article>
          </template>
          <div v-if="isSelectingMerge" class="merge-selection-bar" aria-live="polite"><span>{{ mergeSelectionDescription }}</span><button type="button" :disabled="!canApplyMerge" @click="applyMergeSelection"><Link2 :size="17" />合并为 1 道题</button></div>
        </div>
      </section>
      <aside class="details-column">
        <section class="details-card" aria-labelledby="details-heading"><div class="section-title"><div><p class="section-kicker">第二步</p><h2 id="details-heading">补充一点信息</h2></div></div><p class="details-tip">这能让 AI 更准确地判断知识点。其余信息可在识别后再修改。</p><div class="form-grid"><label>学科<select v-model="subject"><option>数学</option><option>语文</option><option>英语</option><option>其他</option></select></label><label>题目来源<select v-model="source"><option>作业</option><option>试卷</option><option>练习册</option><option>其他</option></select></label></div><label class="note-label">给自己留个备注 <span>可选</span><textarea v-model="note" placeholder="例如：第 2 单元周测，孩子说这题当时没看懂。"></textarea></label><fieldset class="recognition-mode"><legend>识别方式</legend><button type="button" class="mode-choice" :class="{ active: recognitionMode === 'local' }" :aria-pressed="recognitionMode === 'local'" @click="selectRecognitionMode('local')"><ScanText :size="18" /><span><strong>本地 OCR</strong><small>免费、题图不离开设备</small></span></button><button type="button" class="mode-choice" :class="{ active: recognitionMode === 'ai' }" :aria-pressed="recognitionMode === 'ai'" @click="selectRecognitionMode('ai')"><Sparkles :size="18" /><span><strong>AI 视觉识别</strong><small>{{ aiConfigured ? '跳过本地 OCR，直接使用视觉模型' : '需要先完成 AI 设置' }}</small></span></button><p v-if="recognitionMode === 'ai'" class="mode-tip" :class="{ warning: !aiConfigured }">{{ aiConfigured ? '图片会发送给你配置的 AI 服务，适合手写、公式和复杂版面。' : '尚未配置视觉模型，请先完成 AI 设置后再上传。' }}<button v-if="!aiConfigured" type="button" @click="emit('configure-ai')">去配置 AI</button></p></fieldset></section>
        <section class="privacy-note"><LockKeyhole :size="19" /><div><strong>题目只用于生成你的错题本</strong><p>原图会保留，AI 识别结果可随时修改或删除。</p></div></section>
      </aside>
    </div>
    <footer class="upload-footer"><p><CheckCircle2 :size="17" />将由 {{ files.length }} 张图片生成 {{ questionCount }} 道题；合并的图片会一起识别并确认。</p><button class="recognize-button" type="button" :disabled="!canSubmit" @click="queueRecognition"><LoaderCircle v-if="isSubmitting" class="spin" :size="18" />{{ isSubmitting ? '正在上传…' : recognitionMode === 'ai' ? (aiConfigured ? `使用 AI 识别 ${questionCount} 道题` : '请先配置 AI') : `生成 ${questionCount} 道题并识别` }}</button></footer>
    <ImageCropper v-if="activeCropIndex !== null && files[activeCropIndex]" :key="`${files[activeCropIndex].name}-${activeCropIndex}`" :file="files[activeCropIndex]" :initial-region="cropRegions[activeCropIndex]" @cancel="activeCropIndex = null" @confirm="saveCrop" />
  </section>
</template>

<style scoped>
.upload-page { max-width: 1200px; margin: 0 auto; padding: 32px 44px 56px; }.back-button { display: inline-flex; align-items: center; gap: 7px; min-height: 44px; padding: 0; color: #315f9b; border: 0; background: transparent; font-size: 13px; font-weight: 700; }.upload-intro { margin-top: 18px; }.upload-intro h1 { margin: 0; color: #1e3553; font-size: 32px; letter-spacing: -.7px; }.upload-intro > p:last-child { max-width: 590px; margin: 10px 0 0; color: #667b92; line-height: 1.65; }.eyebrow,.section-kicker { margin: 0 0 7px; color: #788da5; font-size: 12px; font-weight: 700; letter-spacing: .35px; }.upload-steps { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; padding: 0; margin: 31px 0 23px; list-style: none; }.upload-steps li { display: grid; grid-template-columns: 31px 1fr; column-gap: 9px; align-items: center; padding: 12px; color: #718198; border: 1px solid #dfe6ed; border-radius: 10px; background: #fff; }.upload-steps li.active { color: #275dba; border-color: #a8c7ee; background: #f4f8ff; }.upload-steps li span { grid-row: span 2; display: grid; width: 30px; height: 30px; place-items: center; color: #64788e; background: #edf1f5; border-radius: 50%; font-size: 12px; font-weight: 700; }.upload-steps li.active span { color: #fff; background: #2563eb; }.upload-steps strong { font-size: 13px; }.upload-steps small { margin-top: 2px; font-size: 11px; }.upload-layout { display: grid; grid-template-columns: minmax(0,1.35fr) minmax(300px,.8fr); gap: 20px; }.upload-card,.details-card { padding: 24px; background: #fff; border: 1px solid #dfe6ed; border-radius: 14px; }.section-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }.section-title h2 { margin: 0; color: #203954; font-size: 19px; }.file-count { padding: 4px 7px; color: #526f93; background: #eff5fd; border-radius: 5px; font-size: 11px; font-weight: 700; }.drop-zone { display: grid; justify-items: center; margin-top: 19px; padding: 33px 20px; color: #50677f; border: 2px dashed #b9cae0; border-radius: 12px; background: #fbfdff; text-align: center; transition: border-color .18s ease, background .18s ease; cursor: pointer; }.drop-zone:hover,.drop-zone.dragging { border-color: #2563eb; background: #f3f8ff; }.drop-zone strong { margin-top: 11px; color: #2b4664; font-size: 15px; }.drop-zone > span { margin-top: 6px; font-size: 12px; }.drop-icon { display: grid; width: 52px; height: 52px; place-items: center; color: #2563eb; background: #e8f1ff; border-radius: 14px; }.choose-button { display: inline-flex; align-items: center; gap: 6px; min-height: 40px; margin-top: 17px; padding: 8px 11px; color: #255ba9; border: 1px solid #b9d0ef; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; }.upload-error { margin: 10px 0 0; color: #b54636; font-size: 12px; }.file-list { display: grid; gap: 8px; margin-top: 16px; }.file-row { display: flex; align-items: center; gap: 9px; padding: 10px 8px; border: 1px solid #e4eaf0; border-radius: 9px; }.file-icon { display: grid; width: 34px; height: 34px; flex: 0 0 auto; place-items: center; color: #356fca; background: #edf4ff; border-radius: 8px; }.file-info { display: grid; min-width: 0; gap: 3px; flex: 1; }.file-info strong { overflow: hidden; color: #344b65; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.file-info span { color: #72849a; font-size: 11px; }.crop-button { display: inline-flex; min-height: 40px; align-items: center; justify-content: center; gap: 5px; padding: 7px 9px; color: #275dba; border: 1px solid #b9d0ef; border-radius: 7px; background: #f7fbff; font-size: 11px; font-weight: 700; white-space: nowrap; cursor: pointer; transition: border-color .18s ease, background .18s ease; }.crop-button:hover { border-color: #78a7df; background: #edf5ff; }.remove-button { display: grid; width: 40px; height: 40px; flex: 0 0 auto; place-items: center; color: #718198; border: 0; border-radius: 7px; background: transparent; cursor: pointer; }.remove-button:hover { color: #b54636; background: #fff1ef; }.crop-button:focus-visible,.remove-button:focus-visible { outline: 3px solid rgba(37,99,235,.2); outline-offset: 2px; }.details-column { display: grid; align-content: start; gap: 14px; }.details-tip { margin: 12px 0 16px; color: #667b92; font-size: 12px; line-height: 1.6; }.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }.form-grid label,.note-label { display: grid; gap: 7px; color: #405a75; font-size: 12px; font-weight: 700; }.form-grid select,.note-label textarea { width: 100%; color: #2d4662; border: 1px solid #cbd8e6; border-radius: 8px; background: #fff; font: inherit; font-size: 14px; }.form-grid select { min-height: 44px; padding: 0 11px; }.note-label { margin-top: 15px; }.note-label span { color: #8596a8; font-size: 11px; font-weight: 500; }.note-label textarea { min-height: 91px; padding: 11px; resize: vertical; line-height: 1.5; }.form-grid select:focus,.note-label textarea:focus { border-color: #2563eb; outline: 3px solid rgba(37,99,235,.16); }.privacy-note { display: flex; gap: 10px; padding: 15px; color: #456789; border: 1px solid #d7e5f6; border-radius: 12px; background: #f5faff; }.privacy-note svg { flex: 0 0 auto; margin-top: 1px; color: #2c68ca; }.privacy-note strong { font-size: 12px; }.privacy-note p { margin: 4px 0 0; color: #607993; font-size: 11px; line-height: 1.5; }.upload-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 22px; padding: 17px 0 0; border-top: 1px solid #e0e7ee; }.upload-footer p { display: flex; align-items: flex-start; gap: 7px; margin: 0; color: #61768d; font-size: 12px; line-height: 1.5; }.upload-footer p svg { flex: 0 0 auto; color: #32866a; }.recognize-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-width: 137px; min-height: 46px; padding: 10px 15px; color: #fff; border: 0; border-radius: 9px; background: #f97316; font-size: 13px; font-weight: 700; transition: background .18s ease, opacity .18s ease; }.recognize-button:hover:not(:disabled) { background: #dc5f0b; }.recognize-button:disabled { cursor: not-allowed; opacity: .46; }.spin { animation: rotate .8s linear infinite; }@keyframes rotate { to { transform: rotate(360deg); } }@media (max-width: 760px) { .upload-page { padding: 22px 17px 42px; }.upload-intro h1 { font-size: 27px; }.upload-steps { gap: 7px; margin-top: 25px; }.upload-steps li { grid-template-columns: 27px 1fr; padding: 9px 7px; column-gap: 6px; }.upload-steps li span { width: 26px; height: 26px; }.upload-steps strong { font-size: 11px; }.upload-steps small { display: none; }.upload-layout { grid-template-columns: 1fr; gap: 13px; }.upload-card,.details-card { padding: 19px 16px; }.drop-zone { padding: 28px 14px; }.file-row { align-items: center; flex-wrap: wrap; }.file-info { flex-basis: calc(100% - 88px); }.crop-button { min-height: 44px; margin-left: 43px; flex: 1; }.remove-button { width: 44px; height: 44px; }.upload-footer { align-items: stretch; flex-direction: column; }.recognize-button { width: 100%; }.upload-footer p { padding: 0 2px; } }@media (prefers-reduced-motion: reduce) { .drop-zone,.crop-button,.recognize-button { transition: none; }.spin { animation: none; } }
.recognition-mode { display: grid; gap: 8px; margin: 18px 0 0; padding: 0; border: 0; }.recognition-mode legend { padding: 0; color: #405a75; font-size: 12px; font-weight: 700; }.mode-choice { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 58px; padding: 10px; color: #516a84; border: 1px solid #d6e1ec; border-radius: 9px; background: #fff; text-align: left; cursor: pointer; transition: border-color .18s ease, background .18s ease; }.mode-choice:hover { border-color: #9ebce4; background: #f8fbff; }.mode-choice.active { color: #255da8; border-color: #72a4e1; background: #f2f7ff; box-shadow: 0 0 0 3px rgba(65,123,209,.1); }.mode-choice > svg { flex: 0 0 auto; }.mode-choice > span { display: grid; gap: 2px; }.mode-choice strong { font-size: 12px; }.mode-choice small,.mode-tip { color: #71859c; font-size: 11px; line-height: 1.45; }.mode-tip { margin: 0; }.mode-tip.warning { color: #9a6a22; }.mode-tip button { min-height: 32px; margin: 7px 0 0; padding: 5px 8px; color: #2e63b6; border: 0; border-radius: 6px; background: #eaf3ff; font: inherit; font-size: 11px; font-weight: 700; cursor: pointer; }
.file-list-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 3px 1px 6px; }.file-list-head > div { display: grid; gap: 3px; }.file-list-head strong { color: #39536f; font-size: 12px; }.file-list-head span { color: #74879b; font-size: 11px; }.merge-mode-button,.cancel-merge-button { display: inline-flex; min-height: 40px; flex: 0 0 auto; align-items: center; justify-content: center; gap: 5px; padding: 7px 10px; color: #315f9b; border: 1px solid #bad0ec; border-radius: 8px; background: #f7fbff; font-size: 11px; font-weight: 700; cursor: pointer; transition: border-color .18s ease, background .18s ease; }.merge-mode-button:hover:not(:disabled),.cancel-merge-button:hover { border-color: #7da7da; background: #edf5ff; }.merge-mode-button:disabled { cursor: not-allowed; opacity: .45; }.cancel-merge-button { color: #61758b; border-color: #d5e0eb; background: #fff; }.merge-group-label { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 5px; padding: 8px 10px; color: #287158; border: 1px solid #b7ddca; border-radius: 8px; background: #f1faf5; font-size: 11px; font-weight: 700; }.merge-group-label span,.merge-group-label button { display: inline-flex; align-items: center; gap: 5px; }.merge-group-label button { min-height: 32px; padding: 4px 7px; color: #287158; border: 0; border-radius: 6px; background: transparent; font: inherit; font-size: 11px; font-weight: 700; cursor: pointer; }.merge-group-label button:hover { background: #dff3e8; }.file-row { transition: border-color .18s ease, background .18s ease; }.file-row.grouped { border-color: #c6e4d4; }.file-row.selected { border-color: #78a7df; background: #f4f8ff; }.merge-file-checkbox { display: inline-flex; min-width: 92px; min-height: 40px; align-items: center; gap: 6px; color: #315f9b; font-size: 11px; font-weight: 700; cursor: pointer; }.merge-file-checkbox input { width: 18px; height: 18px; margin: 0; accent-color: #2563eb; }.merge-selection-bar { position: sticky; bottom: 12px; display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 6px; padding: 10px 11px; color: #315f9b; border: 1px solid #a9c9ee; border-radius: 9px; background: #eff6ff; box-shadow: 0 3px 10px rgba(49,95,155,.11); font-size: 11px; font-weight: 700; }.merge-selection-bar button { display: inline-flex; min-height: 40px; flex: 0 0 auto; align-items: center; justify-content: center; gap: 5px; padding: 7px 10px; color: #fff; border: 0; border-radius: 7px; background: #2563eb; font: inherit; font-size: 11px; font-weight: 700; cursor: pointer; }.merge-selection-bar button:disabled { cursor: not-allowed; opacity: .45; }.merge-mode-button:focus-visible,.cancel-merge-button:focus-visible,.merge-group-label button:focus-visible,.merge-file-checkbox:focus-within { outline: 3px solid rgba(37,99,235,.2); outline-offset: 2px; }@media (max-width: 760px) { .file-list-head { align-items: flex-start; }.merge-file-checkbox { flex-basis: 100%; min-height: 44px; padding-bottom: 4px; border-bottom: 1px solid #e1eaf4; }.merge-group-label { margin-top: 8px; }.merge-selection-bar { align-items: stretch; flex-direction: column; bottom: 8px; }.merge-selection-bar button { width: 100%; min-height: 44px; } }@media (prefers-reduced-motion: reduce) { .merge-mode-button,.cancel-merge-button,.file-row { transition: none; } }
</style>
