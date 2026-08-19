<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, CheckCircle2, ChevronDown, Eye, EyeOff, KeyRound, LoaderCircle, RefreshCw, ShieldCheck, Sparkles } from '@lucide/vue'

const emit = defineEmits<{ back: [] }>()
const baseUrl = ref('https://api.openai.com/v1')
const model = ref('')
const imageEditModel = ref('')
const apiKey = ref('')
const apiKeyConfigured = ref(false)
const clearApiKey = ref(false)
const availableModels = ref<string[]>([])
const useManualModel = ref(false)
const showApiKey = ref(false)
const isLoading = ref(true)
const isLoadingModels = ref(false)
const isSaving = ref(false)
const isTesting = ref(false)
const message = ref('')
const errorMessage = ref('')

const canLoadModels = computed(() => Boolean(baseUrl.value.trim() && (apiKey.value.trim() || apiKeyConfigured.value)))

async function loadConfig() {
  try {
    const response = await fetch('/api/settings/ai')
    const payload = await response.json().catch(() => ({ detail: '无法读取 AI 配置。' }))
    if (!response.ok) throw new Error(payload.detail)
    baseUrl.value = payload.base_url
    model.value = payload.model
    imageEditModel.value = payload.image_edit_model ?? ''
    apiKeyConfigured.value = payload.api_key_configured
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '无法读取 AI 配置。' }
  finally { isLoading.value = false }
}

async function loadModels() {
  if (!canLoadModels.value || isLoadingModels.value) {
    if (!canLoadModels.value) errorMessage.value = '请先填写接口地址和 API 密钥。'
    return
  }
  isLoadingModels.value = true; message.value = ''; errorMessage.value = ''
  try {
    const response = await fetch('/api/settings/ai/models', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: baseUrl.value, api_key: apiKey.value }) })
    const payload = await response.json().catch(() => ({ detail: '无法读取模型列表。' }))
    if (!response.ok) throw new Error(payload.detail)
    availableModels.value = payload.models
    useManualModel.value = false
    message.value = `已读取 ${payload.models.length} 个可用模型，请选择一个视觉模型。`
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '无法读取模型列表。' }
  finally { isLoadingModels.value = false }
}

function maybeLoadModels() {
  if (canLoadModels.value) void loadModels()
}

async function saveConfig() {
  if (!model.value.trim()) { errorMessage.value = '请选择或填写视觉模型。'; return }
  isSaving.value = true; message.value = ''; errorMessage.value = ''
  try {
    const response = await fetch('/api/settings/ai', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: baseUrl.value, model: model.value, image_edit_model: imageEditModel.value, api_key: apiKey.value, clear_api_key: clearApiKey.value }) })
    const payload = await response.json().catch(() => ({ detail: '保存失败，请重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    apiKeyConfigured.value = payload.api_key_configured; apiKey.value = ''; clearApiKey.value = false
    message.value = 'AI 配置已安全保存。'
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '保存失败，请重试。' }
  finally { isSaving.value = false }
}

async function testConnection() {
  isTesting.value = true; message.value = ''; errorMessage.value = ''
  try {
    const response = await fetch('/api/settings/ai/test', { method: 'POST' })
    const payload = await response.json().catch(() => ({ detail: '连接测试失败。' }))
    if (!response.ok) throw new Error(payload.detail)
    message.value = `连接正常：${payload.message}`
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '连接测试失败。' }
  finally { isTesting.value = false }
}

onMounted(loadConfig)
</script>

<template>
  <section class="ai-settings-page" aria-labelledby="ai-settings-title">
    <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回</button>
    <header class="page-heading"><p>识别增强</p><h1 id="ai-settings-title">AI 设置</h1><span>连接兼容 OpenAI 的视觉模型，用于上传时直接识别和后续题目复核。</span></header>
    <div v-if="isLoading" class="loading" aria-live="polite"><LoaderCircle class="spin" :size="20" />正在读取 AI 设置…</div>
    <form v-else class="ai-card" @submit.prevent="saveConfig">
      <div class="card-heading"><div class="icon"><Sparkles :size="20" /></div><div><h2>连接你的 AI 服务</h2><span>输入地址和密钥后，MistakeMate 会读取该服务的模型列表，供你直接选择。</span></div></div>
      <ol class="steps" aria-label="配置步骤"><li><b>1</b>填写接口与密钥</li><li><b>2</b>加载并选择模型</li><li><b>3</b>保存后测试连接</li></ol>
      <div class="form-grid">
        <label for="ai-base-url">接口地址<span class="required">必填</span><input id="ai-base-url" v-model.trim="baseUrl" type="url" required placeholder="https://api.openai.com/v1" @blur="maybeLoadModels" /><small>通常是服务商提供的 API Base URL，例如以 <code>/v1</code> 结尾的地址。</small></label>
        <label for="ai-key">API 密钥<span class="required">必填</span><div class="input-shell"><KeyRound :size="18" /><input id="ai-key" v-model="apiKey" :type="showApiKey ? 'text' : 'password'" autocomplete="new-password" :placeholder="apiKeyConfigured ? '已保存；留空表示不修改' : '粘贴服务商提供的密钥'" @blur="maybeLoadModels" /><button class="icon-button" type="button" :aria-label="showApiKey ? '隐藏密钥' : '显示密钥'" @click="showApiKey = !showApiKey"><EyeOff v-if="showApiKey" :size="17" /><Eye v-else :size="17" /></button></div><small>密钥只用于本次读取模型和保存加密配置，之后不会在页面显示。</small></label>
      </div>

      <section class="model-section" aria-labelledby="model-heading"><div class="section-top"><div><h3 id="model-heading">视觉模型</h3><p>不确定填什么？先加载模型，再从列表中选择。</p></div><button class="secondary load-button" type="button" :disabled="!canLoadModels || isLoadingModels" @click="loadModels"><LoaderCircle v-if="isLoadingModels" class="spin" :size="17" /><RefreshCw v-else :size="17" />{{ isLoadingModels ? '正在加载…' : availableModels.length ? '重新加载模型' : '加载可用模型' }}</button></div>
        <label v-if="availableModels.length && !useManualModel" for="ai-model">选择模型<select id="ai-model" v-model="model" required><option value="" disabled>请选择支持图片输入的视觉模型</option><option v-for="item in availableModels" :key="item" :value="item">{{ item }}</option></select><ChevronDown class="select-icon" :size="18" /></label>
        <label v-else for="ai-model">模型 ID<input id="ai-model" v-model.trim="model" required placeholder="先加载模型；若服务不提供列表，也可手动填写" /><small>填写服务商文档中标注的模型 ID，例如 <code>gpt-4o</code>。请确认该模型支持图片输入。</small></label>
        <button class="text-button" type="button" @click="useManualModel = !useManualModel">{{ useManualModel ? '返回模型列表选择' : '列表没有需要的模型？手动填写模型 ID' }}</button>
      </section>

      <section class="image-edit-section" aria-labelledby="image-edit-heading"><div class="section-top"><div><h3 id="image-edit-heading">图片修复模型 <span>可选</span></h3><p>用于后续去除笔迹、生成清洁打印图；不参与文字识别，也不会覆盖原图。</p></div></div><label for="image-edit-model">图片编辑模型 ID<input id="image-edit-model" v-model.trim="imageEditModel" placeholder="例如 gpt-image-1；留空则暂不启用" /><small>填写支持 OpenAI Images Edit 的模型 ID。和上方共用接口地址与 API 密钥。</small></label><p class="image-edit-note"><ShieldCheck :size="17" /><span>清洁图会作为单独版本保存，生成后需由你确认是否用于打印。</span></p></section>

      <label v-if="apiKeyConfigured" class="checkbox clear-key"><input v-model="clearApiKey" type="checkbox" />清除当前保存的 API 密钥</label>
      <div class="privacy-note"><ShieldCheck :size="18" /><span>密钥会加密保存在本机的 MistakeMate 数据库中。只有你在题目页点击“AI 补全识别”时，原图和 OCR 初稿才会发送给所选服务。</span></div>
      <p v-if="message" class="success" role="status"><CheckCircle2 :size="16" />{{ message }}</p><p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
      <div class="actions"><button class="secondary" type="button" :disabled="isTesting || isSaving || !apiKeyConfigured" @click="testConnection"><LoaderCircle v-if="isTesting" class="spin" :size="17" />{{ isTesting ? '正在测试…' : '测试已保存连接' }}</button><button class="primary" type="submit" :disabled="isSaving"><LoaderCircle v-if="isSaving" class="spin" :size="17" />{{ isSaving ? '保存中…' : '保存 AI 设置' }}</button></div>
    </form>
  </section>
</template>

<style scoped>
.image-edit-section{margin-top:16px;padding:19px;border:1px solid #ded5f7;border-radius:12px;background:#fcfbff}.image-edit-section h3{margin:0;color:#4f3d83;font-size:15px}.image-edit-section h3 span{margin-left:5px;color:#7b6aa7;font-size:11px;font-weight:600}.image-edit-section label{display:grid;gap:7px;color:#4c4663;font-size:13px;font-weight:700}.image-edit-section input{width:100%;min-height:46px;padding:0 12px;color:#2b435d;border:1px solid #d3c9ed;border-radius:9px;background:#fff;font:inherit}.image-edit-section input:focus{outline:0;border-color:#795dd1;box-shadow:0 0 0 3px rgba(121,93,209,.12)}.image-edit-note{display:flex;align-items:flex-start;gap:8px;margin:13px 0 0;padding:10px 11px;color:#5f5b74;border-radius:8px;background:#f4f1fd;font-size:12px;line-height:1.55}.image-edit-note svg{flex:0 0 auto;margin-top:1px;color:#7053c8}
.ai-settings-page{max-width:920px;margin:0 auto;padding:32px 44px 64px;color:#263f5a}.back-button{display:flex;align-items:center;gap:7px;min-height:44px;padding:0;color:#315f9b;border:0;background:transparent;font-size:13px;font-weight:700;cursor:pointer}.page-heading{margin:15px 0 26px}.page-heading>p{margin:0 0 6px;color:#7189a3;font-size:12px;font-weight:800;letter-spacing:.3px}.page-heading h1{margin:0;color:#1e3553;font-size:32px;letter-spacing:-.8px}.page-heading>span{display:block;margin-top:9px;color:#687f97;font-size:13px;line-height:1.6}.ai-card{padding:27px;border:1px solid #dce5ef;border-radius:15px;background:#fff;box-shadow:0 3px 12px rgba(33,72,113,.035)}.card-heading{display:flex;align-items:flex-start;gap:13px;margin-bottom:20px}.icon{display:grid;width:42px;height:42px;flex:0 0 auto;place-items:center;color:#6d4fd0;border-radius:11px;background:#f0ebff}.card-heading h2{margin:0;color:#29435f;font-size:19px;letter-spacing:-.2px}.card-heading span{display:block;margin-top:4px;color:#72869a;font-size:12px;line-height:1.55}.steps{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 20px;padding:0;list-style:none}.steps li{display:flex;align-items:center;gap:7px;padding:7px 10px;color:#496a83;border-radius:8px;background:#f3f7fc;font-size:12px;font-weight:700}.steps b{display:grid;width:18px;height:18px;place-items:center;color:#fff;border-radius:50%;background:#3975cf;font-size:11px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.form-grid label,.model-section label{position:relative;display:grid;gap:7px;color:#3b5570;font-size:13px;font-weight:700}.required{margin-left:5px;color:#b64d41;font-size:11px}.form-grid input,.model-section input,.model-section select,.input-shell{width:100%;min-height:46px;color:#2b435d;border:1px solid #ccd9e7;border-radius:9px;background:#fbfdff;font:inherit}.form-grid input,.model-section input,.model-section select{padding:0 12px}.form-grid input:focus,.model-section input:focus,.model-section select:focus,.input-shell:focus-within{outline:0;border-color:#3975cf;box-shadow:0 0 0 3px rgba(57,117,207,.12)}small{color:#71869c;font-size:11px;font-weight:500;line-height:1.55}code{font-family:ui-monospace,monospace;font-size:.95em}.input-shell{display:flex;align-items:center;gap:9px;padding:0 7px 0 12px;color:#7890a8}.input-shell input{width:0;min-width:0;flex:1;height:42px;padding:0;border:0!important;outline:0;background:transparent;box-shadow:none!important}.icon-button{display:grid;width:38px;height:38px;flex:0 0 auto;place-items:center;color:#3975cf;border:0;border-radius:7px;background:transparent;cursor:pointer}.icon-button:hover{background:#eaf3ff}.model-section{margin-top:24px;padding:19px;border:1px solid #dce7f3;border-radius:12px;background:#f9fbfe}.section-top{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px}.section-top h3{margin:0;color:#2d4a68;font-size:15px}.section-top p{margin:5px 0 0;color:#71869c;font-size:12px;line-height:1.5}.secondary,.primary{display:flex;align-items:center;justify-content:center;gap:7px;min-height:44px;padding:0 15px;border-radius:8px;font-size:13px;font-weight:800;cursor:pointer}.secondary{color:#315f9b;border:1px solid #adc5df;background:#fff}.secondary:hover{border-color:#78a1cf;background:#f8fbff}.secondary:disabled,.primary:disabled{cursor:not-allowed;opacity:.55}.load-button{flex:0 0 auto}.model-section select{appearance:none;padding-right:40px}.select-icon{position:absolute;right:12px;bottom:14px;color:#63819d;pointer-events:none}.text-button{margin-top:12px;padding:5px 0;color:#315f9b;border:0;background:transparent;font-size:12px;font-weight:700;cursor:pointer}.text-button:hover{text-decoration:underline}.checkbox{display:flex!important;align-items:center;gap:8px;min-height:36px;margin-top:6px;color:#526a81!important;font-size:12px!important;font-weight:600!important}.checkbox input{width:17px;height:17px;margin:0;accent-color:#2f6de1}.privacy-note{display:flex;align-items:flex-start;gap:9px;margin-top:16px;padding:12px 13px;color:#496c62;border-radius:9px;background:#eff9f5;font-size:12px;line-height:1.6}.privacy-note svg{flex:0 0 auto;margin-top:1px}.success{display:flex;align-items:center;gap:7px;margin:14px 0 0;color:#23775c;font-size:12px;font-weight:600}.error{margin:14px 0 0;padding:10px 12px;color:#9e4033;border-radius:8px;background:#fff3f1;font-size:12px;line-height:1.5}.actions{display:flex;justify-content:flex-end;gap:9px;margin-top:21px}.primary{color:#fff;border:1px solid #2f6de1;background:#2f6de1}.primary:hover{background:#245cc3}.loading{display:flex;align-items:center;gap:9px;min-height:180px;color:#687f97}.spin{animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:760px){.ai-settings-page{padding:22px 17px 44px}.page-heading h1{font-size:28px}.ai-card{padding:19px}.form-grid{grid-template-columns:1fr}.steps{display:grid;grid-template-columns:1fr}.steps li{padding:8px 10px}.section-top,.actions{align-items:stretch;flex-direction:column}.load-button,.actions button{width:100%}}@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
