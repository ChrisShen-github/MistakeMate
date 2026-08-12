<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, CheckCircle2, Eye, EyeOff, KeyRound, LoaderCircle, LockKeyhole, LogOut, ShieldCheck, Sparkles, UserRound } from '@lucide/vue'
import type { SignedInUser } from './AuthWorkspace.vue'

const props = defineProps<{ user: SignedInUser }>()
const emit = defineEmits<{ back: []; logout: []; 'profile-updated': [user: SignedInUser] }>()
const displayName = ref(props.user.display_name)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const baseUrl = ref('https://api.openai.com/v1')
const model = ref('')
const apiKey = ref('')
const apiKeyConfigured = ref(false)
const clearApiKey = ref(false)
const isLoading = ref(true)
const isSaving = ref(false)
const isTesting = ref(false)
const isSavingProfile = ref(false)
const isChangingPassword = ref(false)
const message = ref('')
const errorMessage = ref('')
const accountMessage = ref('')
const accountError = ref('')

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

async function saveProfile() {
  isSavingProfile.value = true; accountMessage.value = ''; accountError.value = ''
  try {
    const response = await fetch('/api/auth/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: displayName.value }) })
    const payload = await response.json().catch(() => ({ detail: '保存账户资料失败。' }))
    if (!response.ok) throw new Error(payload.detail)
    emit('profile-updated', payload)
    accountMessage.value = '账户资料已更新。'
  } catch (error) { accountError.value = error instanceof Error ? error.message : '保存账户资料失败。' }
  finally { isSavingProfile.value = false }
}

async function changePassword() {
  accountMessage.value = ''; accountError.value = ''
  if (newPassword.value !== confirmPassword.value) { accountError.value = '两次输入的新密码不一致。'; return }
  isChangingPassword.value = true
  try {
    const response = await fetch('/api/auth/password', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: currentPassword.value, new_password: newPassword.value }) })
    const payload = await response.json().catch(() => ({ detail: '修改密码失败。' }))
    if (!response.ok) throw new Error(payload.detail)
    currentPassword.value = ''; newPassword.value = ''; confirmPassword.value = ''; accountMessage.value = payload.message
  } catch (error) { accountError.value = error instanceof Error ? error.message : '修改密码失败。' }
  finally { isChangingPassword.value = false }
}

onMounted(loadConfig)
</script>

<template>
  <section class="settings-page" aria-labelledby="settings-title">
    <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回</button>
    <header class="page-heading"><p>账户与服务</p><h1 id="settings-title">设置</h1><span>AI 只会在你确认后参与 OCR 复核，账号和密码也都在这里管理。</span></header>
    <div v-if="isLoading" class="loading" aria-live="polite"><LoaderCircle class="spin" :size="20" />正在读取设置…</div>
    <div v-else class="settings-stack">
      <form class="card ai-card" @submit.prevent="saveConfig">
        <div class="card-heading"><div class="icon purple"><Sparkles :size="20" /></div><div><p class="section-label">识别增强</p><h2>AI 复核配置</h2><span>支持 OpenAI Chat Completions 和图片输入的视觉模型。</span></div></div>
        <div class="ai-guide"><span>1. 保存接口与密钥</span><span>2. 测试连接</span><span>3. 在题目确认页点击“AI 补全识别”</span></div>
        <div class="form-grid ai-fields">
          <label for="ai-base-url">接口地址<input id="ai-base-url" v-model.trim="baseUrl" type="url" required placeholder="https://.../v1" /></label>
          <label for="ai-model">视觉模型名称<input id="ai-model" v-model.trim="model" required placeholder="填写服务商提供的模型 ID" /></label>
          <label class="field-wide" for="ai-key">API 密钥<div class="input-shell"><KeyRound :size="18" /><input id="ai-key" v-model="apiKey" type="password" autocomplete="new-password" :placeholder="apiKeyConfigured ? '已配置；留空表示不修改' : '请输入 API 密钥'" /></div></label>
        </div>
        <label v-if="apiKeyConfigured" class="checkbox clear-key"><input v-model="clearApiKey" type="checkbox" />清除当前密钥</label>
        <div class="privacy-note"><ShieldCheck :size="18" /><span>密钥加密保存在 MistakeMate 数据库中，网页不会回显。原图仅在你点“AI 补全识别”后才会发送给所选 AI 服务。</span></div>
        <p v-if="message" class="success" role="status"><CheckCircle2 :size="16" />{{ message }}</p><p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
        <div class="actions"><button class="secondary" type="button" :disabled="isTesting || isSaving" @click="testConnection"><LoaderCircle v-if="isTesting" class="spin" :size="17" />{{ isTesting ? '正在测试…' : '测试连接' }}</button><button class="primary" type="submit" :disabled="isSaving"><LoaderCircle v-if="isSaving" class="spin" :size="17" />{{ isSaving ? '保存中…' : '保存设置' }}</button></div>
      </form>
      <section class="card account-card" aria-labelledby="account-heading">
        <div class="card-heading"><div class="avatar">{{ displayName.slice(0, 1) || 'M' }}</div><div><p class="section-label">账户安全</p><h2 id="account-heading">账号与密码</h2><span>@{{ props.user.username }}</span></div></div>
        <div class="account-grid">
          <form class="account-form" @submit.prevent="saveProfile"><h3>账户资料</h3><label for="display-name">显示名称<div class="input-shell"><UserRound :size="17" /><input id="display-name" v-model.trim="displayName" autocomplete="name" required maxlength="64" /></div></label><button class="secondary compact-button" type="submit" :disabled="isSavingProfile"><LoaderCircle v-if="isSavingProfile" class="spin" :size="16" />{{ isSavingProfile ? '保存中…' : '保存名称' }}</button></form>
          <form class="password-form" @submit.prevent="changePassword"><h3><LockKeyhole :size="17" />修改登录密码</h3><div class="password-fields"><label for="current-password">当前密码<div class="input-shell"><LockKeyhole :size="16" /><input id="current-password" v-model="currentPassword" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" required /></div></label><label for="new-password">新密码<div class="input-shell"><LockKeyhole :size="16" /><input id="new-password" v-model="newPassword" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" required minlength="8" placeholder="至少 8 位" /></div></label><label for="confirm-password">确认新密码<div class="input-shell"><LockKeyhole :size="16" /><input id="confirm-password" v-model="confirmPassword" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" required minlength="8" /><button class="form-submit" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword"><EyeOff v-if="showPassword" :size="17" /><Eye v-else :size="17" /></button></div></label></div><div class="password-actions"><label class="checkbox"><input v-model="showPassword" type="checkbox" />显示密码</label><button class="secondary compact-button" type="submit" :disabled="isChangingPassword"><LoaderCircle v-if="isChangingPassword" class="spin" :size="16" />{{ isChangingPassword ? '修改中…' : '修改密码' }}</button></div></form>
        </div>
        <p v-if="accountMessage" class="success" role="status"><CheckCircle2 :size="16" />{{ accountMessage }}</p><p v-if="accountError" class="error" role="alert">{{ accountError }}</p>
        <div class="account-footer"><p class="account-copy">退出后需要重新输入密码。错题和 AI 设置会安全保留。</p><button class="logout" type="button" @click="emit('logout')"><LogOut :size="17" />退出登录</button></div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.settings-page{max-width:920px;margin:0 auto;padding:32px 44px 64px;color:#263f5a}.back-button{display:flex;align-items:center;gap:7px;min-height:44px;padding:0;color:#315f9b;border:0;background:transparent;font-size:13px;font-weight:700;cursor:pointer}.page-heading{margin:15px 0 26px}.page-heading>p,.section-label{margin:0 0 6px;color:#7189a3;font-size:12px;font-weight:800;letter-spacing:.3px}.page-heading h1{margin:0;color:#1e3553;font-size:32px;letter-spacing:-.8px}.page-heading>span{display:block;margin-top:9px;color:#687f97;font-size:13px;line-height:1.6}.settings-stack{display:grid;gap:20px}.card{padding:26px;border:1px solid #dce5ef;border-radius:15px;background:#fff;box-shadow:0 3px 12px rgba(33,72,113,.035)}.card-heading{display:flex;align-items:flex-start;gap:13px;margin-bottom:21px}.card-heading h2{margin:0;color:#29435f;font-size:19px;letter-spacing:-.2px}.card-heading span{display:block;margin-top:4px;color:#72869a;font-size:12px;line-height:1.55}.icon,.avatar{display:grid;width:42px;height:42px;flex:0 0 auto;place-items:center;border-radius:11px}.icon.purple{color:#6d4fd0;background:#f0ebff}.avatar{color:#fff;border-radius:50%;background:#2f6de1;font-weight:800}.ai-guide{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 19px}.ai-guide span{padding:6px 9px;color:#47667f;border-radius:7px;background:#f1f6fb;font-size:11px;font-weight:700}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.form-grid label,.account-form label,.password-form label{display:grid;gap:7px;color:#3b5570;font-size:13px;font-weight:700}.field-wide{grid-column:1/-1}.form-grid input,.input-shell{width:100%;min-height:46px;color:#2b435d;border:1px solid #ccd9e7;border-radius:9px;background:#fbfdff;font:inherit}.form-grid input{padding:0 12px}.form-grid input:focus,.input-shell:focus-within{outline:0;border-color:#3975cf;box-shadow:0 0 0 3px rgba(57,117,207,.12)}.input-shell{display:flex;align-items:center;gap:9px;padding:0 12px;color:#7890a8}.input-shell input{width:0;min-width:0;flex:1;height:42px;padding:0;color:#2b435d;border:0!important;outline:0;background:transparent;font:inherit;box-shadow:none!important}.form-submit{display:grid;width:38px;height:38px;flex:0 0 auto;place-items:center;color:#3975cf;border:0;border-radius:7px;background:transparent;cursor:pointer}.form-submit:hover{background:#eaf3ff}.checkbox{display:flex!important;align-items:center;gap:8px;min-height:36px;color:#526a81!important;font-size:12px!important;font-weight:600!important}.checkbox input{width:17px;height:17px;margin:0;accent-color:#2f6de1}.clear-key{margin-top:2px}.privacy-note{display:flex;align-items:flex-start;gap:9px;margin-top:17px;padding:12px 13px;color:#496c62;border-radius:9px;background:#eff9f5;font-size:12px;line-height:1.6}.privacy-note svg{flex:0 0 auto;margin-top:1px}.success{display:flex;align-items:center;gap:7px;margin:13px 0 0;color:#23775c;font-size:12px;font-weight:600}.error{margin:13px 0 0;padding:10px 12px;color:#9e4033;border-radius:8px;background:#fff3f1;font-size:12px;line-height:1.5}.actions{display:flex;justify-content:flex-end;gap:9px;margin-top:20px}.actions button,.logout,.compact-button{display:flex;align-items:center;justify-content:center;gap:7px;min-height:44px;padding:0 15px;border-radius:8px;font-size:13px;font-weight:800;cursor:pointer}.secondary{color:#315f9b;border:1px solid #adc5df;background:#fff}.secondary:hover{border-color:#78a1cf;background:#f8fbff}.primary{color:#fff;border:1px solid #2f6de1;background:#2f6de1}.primary:hover{background:#245cc3}.actions button:disabled,.compact-button:disabled,.form-submit:disabled{cursor:wait;opacity:.65}.account-card{padding-bottom:21px}.account-grid{display:grid;grid-template-columns:minmax(230px,.75fr) minmax(0,1.65fr);gap:25px;padding-top:2px}.account-form{display:grid;align-content:start;gap:13px;padding-right:25px;border-right:1px solid #e8edf3}.account-form h3,.password-form h3{margin:0;color:#385571;font-size:15px}.password-form{display:grid;gap:13px}.password-form h3{display:flex;align-items:center;gap:7px}.password-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}.password-actions{display:flex;align-items:center;justify-content:space-between;gap:14px}.compact-button{align-self:start;min-width:112px}.account-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:20px;padding-top:18px;border-top:1px solid #e8edf3}.account-copy{margin:0;color:#70849a;font-size:12px;line-height:1.6}.logout{flex:0 0 auto;color:#a24437;border:1px solid #e1b7b0;background:#fff}.logout:hover{background:#fff7f5}.loading{display:flex;align-items:center;gap:9px;min-height:180px;color:#687f97}.spin{animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:760px){.settings-page{padding:22px 17px 44px}.page-heading h1{font-size:28px}.card{padding:19px}.form-grid,.account-grid,.password-fields{grid-template-columns:1fr}.account-form{padding:0 0 19px;border-right:0;border-bottom:1px solid #e8edf3}.password-actions,.account-footer{align-items:stretch;flex-direction:column}.compact-button,.logout{width:100%}.actions{flex-direction:column-reverse}.actions button{width:100%}.ai-guide{display:grid;grid-template-columns:1fr}.ai-guide span{padding:8px 10px}.field-wide{grid-column:auto}}@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
