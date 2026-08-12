<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowLeft, CheckCircle2, CircleAlert, Download, HardDriveDownload, LoaderCircle, RotateCcw, Server, X } from '@lucide/vue'

type OcrModel = { id: string; name: string; installed: boolean; size_bytes: number }
type OcrModelStatus = {
  status: 'not_installed' | 'downloading' | 'extracting' | 'ready' | 'failed' | 'cancelled'
  message: string
  source: string
  current_model: string
  current_model_name: string
  completed_models: number
  total_models: number
  downloaded_bytes: number
  total_bytes: number | null
  speed_bytes_per_second: number
  models: OcrModel[]
}

const emit = defineEmits<{ back: [] }>()
const status = ref<OcrModelStatus | null>(null)
const isLoading = ref(true)
const actionError = ref('')
let refreshTimer: number | undefined

const isWorking = computed(() => ['downloading', 'extracting'].includes(status.value?.status || ''))
const isReady = computed(() => status.value?.status === 'ready')
const progress = computed(() => {
  if (!status.value?.total_bytes) return null
  return Math.min(100, Math.round(status.value.downloaded_bytes / status.value.total_bytes * 100))
})

function formatBytes(value: number) {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** exponent).toFixed(exponent ? 1 : 0)} ${units[exponent]}`
}

function formatSpeed(value: number) {
  return value > 0 ? `${formatBytes(value)}/秒` : '正在连接…'
}

async function loadStatus(silent = false) {
  if (!silent) isLoading.value = true
  try {
    const response = await fetch('/api/settings/ocr-models')
    const payload = await response.json().catch(() => ({ detail: '无法读取 OCR 模型状态。' }))
    if (!response.ok) throw new Error(payload.detail)
    status.value = payload
    if (!isWorking.value && refreshTimer) {
      window.clearInterval(refreshTimer)
      refreshTimer = undefined
    }
  } catch (error) { actionError.value = error instanceof Error ? error.message : '无法读取 OCR 模型状态。' }
  finally { isLoading.value = false }
}

function startPolling() {
  if (refreshTimer) return
  refreshTimer = window.setInterval(() => { void loadStatus(true) }, 800)
}

async function startDownload() {
  actionError.value = ''
  try {
    const response = await fetch('/api/settings/ocr-models/download', { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '无法开始下载。' }))
    if (!response.ok) throw new Error(payload.detail)
    status.value = payload
    startPolling()
  } catch (error) { actionError.value = error instanceof Error ? error.message : '无法开始下载。' }
}

async function cancelDownload() {
  actionError.value = ''
  try {
    const response = await fetch('/api/settings/ocr-models/cancel', { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '无法取消下载。' }))
    if (!response.ok) throw new Error(payload.detail)
    status.value = payload
    startPolling()
  } catch (error) { actionError.value = error instanceof Error ? error.message : '无法取消下载。' }
}

onMounted(async () => {
  await loadStatus()
  if (isWorking.value) startPolling()
})
onBeforeUnmount(() => { if (refreshTimer) window.clearInterval(refreshTimer) })
</script>

<template>
  <section class="ocr-model-page" aria-labelledby="ocr-model-title">
    <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回</button>
    <header class="page-heading"><p>本地识别</p><h1 id="ocr-model-title">OCR 模型</h1><span>模型只下载到本机，不会包含在 MistakeMate 镜像中；下载完成后可离线识别题图。</span></header>

    <div v-if="isLoading" class="loading" aria-live="polite"><LoaderCircle class="spin" :size="20" />正在检查模型状态…</div>
    <template v-else-if="status">
      <section class="status-card" :class="status.status">
        <div class="status-icon"><CheckCircle2 v-if="isReady" :size="24" /><HardDriveDownload v-else-if="isWorking" :size="24" /><CircleAlert v-else :size="24" /></div>
        <div class="status-copy"><p class="eyebrow">{{ isReady ? '已准备就绪' : isWorking ? '正在准备本地识别' : '首次使用需要下载' }}</p><h2>{{ status.message }}</h2><span v-if="isWorking && status.current_model_name">当前：{{ status.current_model_name }}（{{ status.completed_models + 1 }} / {{ status.total_models }}）</span><span v-else-if="isReady">共 {{ status.total_models }} 个模型，{{ formatBytes(status.models.reduce((total, model) => total + model.size_bytes, 0)) }} 已保存到本机。</span><span v-else>共 {{ status.total_models }} 个必要模型，解压后约 180 MB。</span></div>
        <button v-if="isWorking" class="cancel-button" type="button" @click="cancelDownload"><X :size="17" />取消</button>
        <button v-else-if="!isReady" class="primary-button" type="button" @click="startDownload"><Download :size="17" />{{ status.status === 'failed' || status.status === 'cancelled' ? '继续下载' : '下载本地 OCR 模型' }}</button>
      </section>

      <section v-if="isWorking" class="progress-card" aria-live="polite">
        <div class="progress-heading"><strong>{{ progress === null ? '正在连接官方源…' : `下载进度 ${progress}%` }}</strong><span>{{ status.total_bytes ? `${formatBytes(status.downloaded_bytes)} / ${formatBytes(status.total_bytes)}` : '正在获取文件大小' }}</span></div>
        <div class="progress-track" role="progressbar" :aria-valuenow="progress ?? undefined" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${progress ?? 12}%` }"></i></div>
        <p><LoaderCircle v-if="status.status === 'extracting'" class="spin" :size="16" /><Server v-else :size="16" />{{ status.status === 'extracting' ? '正在校验并安装模型文件…' : `当前速度：${formatSpeed(status.speed_bytes_per_second)}` }}</p>
      </section>

      <section class="model-card" aria-labelledby="model-list-title">
        <div class="section-heading"><div><p class="eyebrow">下载内容</p><h2 id="model-list-title">中文题目识别所需模型</h2></div><span>{{ status.completed_models }} / {{ status.total_models }} 已完成</span></div>
        <ul>
          <li v-for="model in status.models" :key="model.id"><CheckCircle2 v-if="model.installed" :size="18" /><span v-else class="pending-dot"></span><div><strong>{{ model.name }}</strong><small>{{ model.installed ? `${formatBytes(model.size_bytes)} · 已安装` : '等待下载' }}</small></div></li>
        </ul>
      </section>

      <section class="source-card"><Server :size="19" /><div><strong>下载来源：{{ status.source }}</strong><p>使用 PaddleOCR 官方百度对象存储（BOS）。它是国内源，通常无需代理；实际速度取决于部署机器的网络。若有用户持续下载失败，再根据反馈增加临时代理设置。</p></div></section>
      <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
      <button class="refresh-button" type="button" @click="loadStatus()"><RotateCcw :size="16" />刷新状态</button>
    </template>
  </section>
</template>

<style scoped>
.ocr-model-page{max-width:920px;margin:0 auto;padding:32px 44px 64px;color:#263f5a}.back-button{display:flex;align-items:center;gap:7px;min-height:44px;padding:0;color:#315f9b;border:0;background:transparent;font-size:13px;font-weight:700;cursor:pointer}.page-heading{margin:15px 0 26px}.page-heading>p,.eyebrow{margin:0 0 6px;color:#7189a3;font-size:12px;font-weight:800;letter-spacing:.3px}.page-heading h1{margin:0;color:#1e3553;font-size:32px;letter-spacing:-.8px}.page-heading>span{display:block;margin-top:9px;color:#687f97;font-size:13px;line-height:1.6}.status-card,.progress-card,.model-card,.source-card{border:1px solid #dce5ef;border-radius:15px;background:#fff;box-shadow:0 3px 12px rgba(33,72,113,.035)}.status-card{display:flex;align-items:center;gap:16px;padding:24px}.status-icon{display:grid;width:48px;height:48px;flex:0 0 auto;place-items:center;color:#426fbb;border-radius:13px;background:#edf4ff}.status-card.ready .status-icon{color:#27785d;background:#eaf8f1}.status-card.failed .status-icon,.status-card.cancelled .status-icon{color:#a5483d;background:#fff1ee}.status-copy{min-width:0;flex:1}.status-copy h2{margin:0;color:#29435f;font-size:18px}.status-copy span{display:block;margin-top:6px;color:#71869c;font-size:12px;line-height:1.55}.primary-button,.cancel-button,.refresh-button{display:flex;min-height:44px;align-items:center;justify-content:center;gap:7px;padding:0 15px;border-radius:8px;font-size:13px;font-weight:800;cursor:pointer}.primary-button{flex:0 0 auto;color:#fff;border:1px solid #2f6de1;background:#2f6de1}.primary-button:hover{background:#245cc3}.cancel-button{flex:0 0 auto;color:#9f4b40;border:1px solid #e1b7b0;background:#fff}.progress-card{margin-top:15px;padding:20px}.progress-heading{display:flex;justify-content:space-between;gap:14px;color:#47627e;font-size:12px}.progress-heading strong{color:#31516f}.progress-track{height:10px;margin-top:11px;overflow:hidden;border-radius:999px;background:#e7eef6}.progress-track i{display:block;height:100%;min-width:12%;border-radius:inherit;background:linear-gradient(90deg,#2f6de1,#5b92ea);transition:width .2s ease-out}.progress-card p{display:flex;align-items:center;gap:6px;margin:12px 0 0;color:#617991;font-size:12px}.model-card{margin-top:15px;padding:23px}.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.section-heading h2{margin:0;color:#29435f;font-size:17px}.section-heading>span{padding:6px 8px;color:#315f9b;border-radius:7px;background:#eef5ff;font-size:11px;font-weight:800}.model-card ul{display:grid;gap:0;margin:16px 0 0;padding:0;list-style:none;border-top:1px solid #e7edf3}.model-card li{display:flex;align-items:center;gap:10px;min-height:55px;border-bottom:1px solid #e7edf3}.model-card li>svg{color:#23805e}.pending-dot{width:18px;height:18px;box-sizing:border-box;border:2px solid #b9c8d7;border-radius:50%}.model-card li div{display:grid;gap:3px}.model-card strong{color:#42607d;font-size:13px}.model-card small{color:#8191a1;font-size:11px}.source-card{display:flex;align-items:flex-start;gap:10px;margin-top:15px;padding:15px;color:#4c7086;background:#f5f9fd;font-size:12px;line-height:1.6}.source-card>svg{flex:0 0 auto;margin-top:1px;color:#3975cf}.source-card strong{color:#335874}.source-card p{margin:3px 0 0}.refresh-button{margin-top:14px;color:#315f9b;border:1px solid #b9cee5;background:#fff}.refresh-button:hover{background:#f8fbff}.error{margin:14px 0 0;padding:10px 12px;color:#9e4033;border-radius:8px;background:#fff3f1;font-size:12px;line-height:1.5}.loading{display:flex;align-items:center;gap:9px;min-height:180px;color:#687f97}.spin{animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:760px){.ocr-model-page{padding:22px 17px 44px}.page-heading h1{font-size:28px}.status-card{align-items:stretch;flex-wrap:wrap;padding:19px}.status-icon{width:42px;height:42px}.status-copy{flex-basis:calc(100% - 58px)}.primary-button,.cancel-button{width:100%}.progress-card,.model-card{padding:18px}.progress-heading{align-items:flex-start;flex-direction:column;gap:4px}.source-card{padding:14px}}@media(prefers-reduced-motion:reduce){.spin{animation:none}.progress-track i{transition:none}}
</style>
