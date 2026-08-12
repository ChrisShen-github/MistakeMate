<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, CheckCircle2, KeyRound, LoaderCircle, LogOut, ShieldCheck, Sparkles } from '@lucide/vue'
import type { SignedInUser } from './AuthWorkspace.vue'

const props = defineProps<{ user: SignedInUser }>()
const emit = defineEmits<{ back: []; logout: [] }>()
const baseUrl = ref('https://api.openai.com/v1')
const model = ref('')
const apiKey = ref('')
const apiKeyConfigured = ref(false)
const clearApiKey = ref(false)
const isLoading = ref(true)
const isSaving = ref(false)
const isTesting = ref(false)
const message = ref('')
const errorMessage = ref('')

async function loadConfig() {
  try {
    const response = await fetch('/api/settings/ai')
    const payload = await response.json().catch(() => ({ detail: '无法读取 AI 配置。' }))
    if (!response.ok) throw new Error(payload.detail)
    baseUrl.value = payload.base_url
    model.value = payload.model
    apiKeyConfigured.value = payload.api_key_configured
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '无法读取 AI 配置。'
  } finally {
    isLoading.value = false
  }
}

async function saveConfig() {
  isSaving.value = true; message.value = ''; errorMessage.value = ''
  try {
    const response = await fetch('/api/settings/ai', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: baseUrl.value, model: model.value, api_key: apiKey.value, clear_api_key: clearApiKey.value }) })
    const payload = await response.json().catch(() => ({ detail: '保存失败，请重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    apiKeyConfigured.value = payload.api_key_configured; apiKey.value = ''; clearApiKey.value = false; message.value = 'AI 配置已安全保存。'
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
  <section class="settings-page" aria-labelledby="settings-title">
    <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回</button>
    <header><p>账户与服务</p><h1 id="settings-title">AI 设置</h1><span>配置后，只有你在 OCR 页面手动点击时才会调用 AI。</span></header>
    <div v-if="isLoading" class="loading" aria-live="polite"><LoaderCircle class="spin" :size="20" />正在读取设置…</div>
    <div v-else class="settings-grid">
      <form class="card ai-card" @submit.prevent="saveConfig">
        <div class="card-heading"><div class="icon purple"><Sparkles :size="20" /></div><div><h2>OpenAI 兼容接口</h2><p>可连接支持 Chat Completions 和图片输入的服务。</p></div></div>
        <label for="ai-base-url">接口地址</label><input id="ai-base-url" v-model.trim="baseUrl" type="url" required placeholder="https://.../v1" />
        <label for="ai-model">视觉模型名称</label><input id="ai-model" v-model.trim="model" required placeholder="填写服务商提供的模型 ID" />
        <label for="ai-key">API 密钥</label><div class="key-input"><KeyRound :size="18" /><input id="ai-key" v-model="apiKey" type="password" autocomplete="new-password" :placeholder="apiKeyConfigured ? '已配置；留空表示不修改' : '请输入 API 密钥'" /></div>
        <label v-if="apiKeyConfigured" class="checkbox"><input v-model="clearApiKey" type="checkbox" />清除当前密钥</label>
        <div class="privacy-note"><ShieldCheck :size="18" /><span>密钥会加密保存，页面不会回显。题图仅在你点击“AI 补全识别”后发送。</span></div>
        <p v-if="message" class="success" role="status"><CheckCircle2 :size="16" />{{ message }}</p><p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
        <div class="actions"><button class="secondary" type="button" :disabled="isTesting || isSaving" @click="testConnection"><LoaderCircle v-if="isTesting" class="spin" :size="17" />{{ isTesting ? '正在测试…' : '测试连接' }}</button><button class="primary" type="submit" :disabled="isSaving"><LoaderCircle v-if="isSaving" class="spin" :size="17" />{{ isSaving ? '保存中…' : '保存设置' }}</button></div>
      </form>
      <aside class="card account-card"><div class="card-heading"><div class="avatar">{{ props.user.display_name.slice(0, 1) }}</div><div><h2>{{ props.user.display_name }}</h2><p>@{{ props.user.username }}</p></div></div><p class="account-copy">退出后需要重新输入密码。错题和 AI 设置仍会安全保留。</p><button class="logout" type="button" @click="emit('logout')"><LogOut :size="17" />退出登录</button></aside>
    </div>
  </section>
</template>

<style scoped>
.settings-page{max-width:1050px;margin:0 auto;padding:32px 44px 60px;color:#263f5a}.back-button{display:flex;align-items:center;gap:7px;min-height:44px;padding:0;color:#315f9b;border:0;background:transparent;font-weight:700;cursor:pointer}header{margin:16px 0 25px}header p{margin:0 0 7px;color:#7189a3;font-size:12px;font-weight:800}header h1{margin:0;font-size:31px;letter-spacing:-.6px}header span{display:block;margin-top:9px;color:#687f97;font-size:13px}.settings-grid{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:20px;align-items:start}.card{padding:24px;border:1px solid #dce5ef;border-radius:14px;background:#fff}.card-heading{display:flex;align-items:center;gap:12px;margin-bottom:23px}.card-heading h2{margin:0;color:#29435f;font-size:18px}.card-heading p{margin:4px 0 0;color:#72869a;font-size:12px}.icon{display:grid;width:42px;height:42px;place-items:center;border-radius:11px}.icon.purple{color:#6d4fd0;background:#f0ebff}.ai-card{display:grid;gap:9px}.ai-card label{margin-top:6px;color:#3b5570;font-size:13px;font-weight:700}.ai-card>input,.key-input{min-height:46px;padding:0 12px;color:#2b435d;border:1px solid #ccd9e7;border-radius:8px;background:#fbfdff;font:inherit}.ai-card>input:focus,.key-input:focus-within{outline:0;border-color:#3975cf;box-shadow:0 0 0 3px rgba(57,117,207,.12)}.key-input{display:flex;align-items:center;gap:9px;color:#7890a8}.key-input input{min-width:0;flex:1;height:42px;border:0;outline:0;background:transparent;font:inherit}.checkbox{display:flex;align-items:center;gap:8px;min-height:36px!important;color:#93463a!important}.checkbox input{width:17px;height:17px}.privacy-note{display:flex;align-items:flex-start;gap:9px;margin-top:10px;padding:12px;color:#496c62;border-radius:9px;background:#eff9f5;font-size:12px;line-height:1.6}.privacy-note svg{flex:0 0 auto}.success{display:flex;align-items:center;gap:7px;margin:4px 0 0;color:#23775c;font-size:12px}.error{margin:4px 0 0;padding:10px 12px;color:#9e4033;border-radius:8px;background:#fff3f1;font-size:12px}.actions{display:flex;justify-content:flex-end;gap:9px;margin-top:12px}.actions button,.logout{display:flex;align-items:center;justify-content:center;gap:7px;min-height:44px;padding:0 15px;border-radius:8px;font-weight:800;cursor:pointer}.secondary{color:#315f9b;border:1px solid #adc5df;background:#fff}.primary{color:#fff;border:1px solid #2f6de1;background:#2f6de1}.actions button:disabled{cursor:wait;opacity:.65}.avatar{display:grid;width:42px;height:42px;place-items:center;color:#fff;border-radius:50%;background:#2f6de1;font-weight:800}.account-copy{color:#70849a;font-size:12px;line-height:1.7}.logout{width:100%;margin-top:18px;color:#a24437;border:1px solid #e1b7b0;background:#fff}.loading{display:flex;align-items:center;gap:9px;min-height:180px;color:#687f97}.spin{animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:800px){.settings-page{padding:22px 17px 44px}.settings-grid{grid-template-columns:1fr}.account-card{order:-1}.actions{flex-direction:column-reverse}.actions button{width:100%}}@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
