<script setup lang="ts">
import { ref } from 'vue'
import { ArrowLeft, CheckCircle2, Eye, EyeOff, LoaderCircle, LockKeyhole, LogOut, UserRound } from '@lucide/vue'
import type { SignedInUser } from './AuthWorkspace.vue'

const props = defineProps<{ user: SignedInUser }>()
const emit = defineEmits<{ back: []; logout: []; 'profile-updated': [user: SignedInUser] }>()
const displayName = ref(props.user.display_name)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const isSavingProfile = ref(false)
const isChangingPassword = ref(false)
const message = ref('')
const errorMessage = ref('')

async function saveProfile() {
  isSavingProfile.value = true; message.value = ''; errorMessage.value = ''
  try {
    const response = await fetch('/api/auth/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: displayName.value }) })
    const payload = await response.json().catch(() => ({ detail: '保存账户资料失败。' }))
    if (!response.ok) throw new Error(payload.detail)
    emit('profile-updated', payload)
    message.value = '显示名称已更新。'
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '保存账户资料失败。' }
  finally { isSavingProfile.value = false }
}

async function changePassword() {
  message.value = ''; errorMessage.value = ''
  if (newPassword.value !== confirmPassword.value) { errorMessage.value = '两次输入的新密码不一致。'; return }
  isChangingPassword.value = true
  try {
    const response = await fetch('/api/auth/password', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: currentPassword.value, new_password: newPassword.value }) })
    const payload = await response.json().catch(() => ({ detail: '修改密码失败。' }))
    if (!response.ok) throw new Error(payload.detail)
    currentPassword.value = ''; newPassword.value = ''; confirmPassword.value = ''
    message.value = payload.message
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '修改密码失败。' }
  finally { isChangingPassword.value = false }
}
</script>

<template>
  <section class="settings-page" aria-labelledby="settings-title">
    <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回</button>
    <header class="page-heading"><p>账户与安全</p><h1 id="settings-title">账户设置</h1><span>管理个人显示名称、登录密码和当前会话。</span></header>

    <section class="card account-card" aria-labelledby="account-heading">
      <div class="card-heading"><div class="avatar">{{ displayName.slice(0, 1) || 'M' }}</div><div><h2 id="account-heading">{{ props.user.username }}</h2><span>个人资料与登录安全</span></div></div>
      <div class="account-grid">
        <form class="account-form" @submit.prevent="saveProfile">
          <h3>个人资料</h3>
          <label for="display-name">显示名称<div class="input-shell"><UserRound :size="17" /><input id="display-name" v-model.trim="displayName" autocomplete="name" required maxlength="64" /></div></label>
          <button class="secondary compact-button" type="submit" :disabled="isSavingProfile"><LoaderCircle v-if="isSavingProfile" class="spin" :size="16" />{{ isSavingProfile ? '保存中…' : '保存名称' }}</button>
        </form>
        <form class="password-form" @submit.prevent="changePassword">
          <h3><LockKeyhole :size="17" />修改登录密码</h3>
          <div class="password-fields">
            <label for="current-password">当前密码<div class="input-shell"><LockKeyhole :size="16" /><input id="current-password" v-model="currentPassword" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" required /></div></label>
            <label for="new-password">新密码<div class="input-shell"><LockKeyhole :size="16" /><input id="new-password" v-model="newPassword" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" required minlength="8" placeholder="至少 8 位" /></div></label>
            <label for="confirm-password">确认新密码<div class="input-shell"><LockKeyhole :size="16" /><input id="confirm-password" v-model="confirmPassword" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" required minlength="8" /><button class="form-submit" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword"><EyeOff v-if="showPassword" :size="17" /><Eye v-else :size="17" /></button></div></label>
          </div>
          <div class="password-actions"><label class="checkbox"><input v-model="showPassword" type="checkbox" />显示密码</label><button class="secondary compact-button" type="submit" :disabled="isChangingPassword"><LoaderCircle v-if="isChangingPassword" class="spin" :size="16" />{{ isChangingPassword ? '修改中…' : '修改密码' }}</button></div>
        </form>
      </div>
      <p v-if="message" class="success" role="status"><CheckCircle2 :size="16" />{{ message }}</p><p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
      <div class="account-footer"><p>退出后需要重新输入密码。你的错题和 AI 设置会安全保留。</p><button class="logout" type="button" @click="emit('logout')"><LogOut :size="17" />退出登录</button></div>
    </section>
  </section>
</template>

<style scoped>
.settings-page{max-width:920px;margin:0 auto;padding:32px 44px 64px;color:#263f5a}.back-button{display:flex;align-items:center;gap:7px;min-height:44px;padding:0;color:#315f9b;border:0;background:transparent;font-size:13px;font-weight:700;cursor:pointer}.page-heading{margin:15px 0 26px}.page-heading>p{margin:0 0 6px;color:#7189a3;font-size:12px;font-weight:800;letter-spacing:.3px}.page-heading h1{margin:0;color:#1e3553;font-size:32px;letter-spacing:-.8px}.page-heading>span{display:block;margin-top:9px;color:#687f97;font-size:13px;line-height:1.6}.card{padding:27px;border:1px solid #dce5ef;border-radius:15px;background:#fff;box-shadow:0 3px 12px rgba(33,72,113,.035)}.card-heading{display:flex;align-items:flex-start;gap:13px;margin-bottom:25px}.card-heading h2{margin:1px 0 0;color:#29435f;font-size:19px;letter-spacing:-.2px}.card-heading span{display:block;margin-top:4px;color:#72869a;font-size:12px}.avatar{display:grid;width:42px;height:42px;flex:0 0 auto;place-items:center;color:#fff;border-radius:50%;background:#2f6de1;font-weight:800}.account-grid{display:grid;grid-template-columns:minmax(230px,.75fr) minmax(0,1.65fr);gap:25px}.account-form,.password-form{display:grid;gap:13px}.account-form{padding-right:25px;border-right:1px solid #e8edf3}.account-form h3,.password-form h3{margin:0;color:#385571;font-size:15px}.password-form h3{display:flex;align-items:center;gap:7px}.account-form label,.password-form label{display:grid;gap:7px;color:#3b5570;font-size:13px;font-weight:700}.input-shell{display:flex;align-items:center;gap:9px;width:100%;min-height:46px;padding:0 12px;color:#7890a8;border:1px solid #ccd9e7;border-radius:9px;background:#fbfdff}.input-shell:focus-within{border-color:#3975cf;box-shadow:0 0 0 3px rgba(57,117,207,.12)}.input-shell input{width:0;min-width:0;flex:1;height:42px;padding:0;color:#2b435d;border:0;outline:0;background:transparent;font:inherit}.password-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}.form-submit{display:grid;width:38px;height:38px;flex:0 0 auto;place-items:center;color:#3975cf;border:0;border-radius:7px;background:transparent;cursor:pointer}.form-submit:hover{background:#eaf3ff}.password-actions,.account-footer{display:flex;align-items:center;justify-content:space-between;gap:14px}.checkbox{display:flex!important;align-items:center;gap:8px;min-height:36px;color:#526a81!important;font-size:12px!important;font-weight:600!important}.checkbox input{width:17px;height:17px;margin:0;accent-color:#2f6de1}.secondary,.logout{display:flex;align-items:center;justify-content:center;gap:7px;min-height:44px;padding:0 15px;border-radius:8px;font-size:13px;font-weight:800;cursor:pointer}.secondary{color:#315f9b;border:1px solid #adc5df;background:#fff}.secondary:hover{border-color:#78a1cf;background:#f8fbff}.compact-button{align-self:start;min-width:112px}.secondary:disabled{cursor:wait;opacity:.65}.success{display:flex;align-items:center;gap:7px;margin:15px 0 0;color:#23775c;font-size:12px;font-weight:600}.error{margin:15px 0 0;padding:10px 12px;color:#9e4033;border-radius:8px;background:#fff3f1;font-size:12px;line-height:1.5}.account-footer{margin-top:21px;padding-top:18px;border-top:1px solid #e8edf3}.account-footer p{margin:0;color:#70849a;font-size:12px;line-height:1.6}.logout{flex:0 0 auto;color:#a24437;border:1px solid #e1b7b0;background:#fff}.logout:hover{background:#fff7f5}.spin{animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:760px){.settings-page{padding:22px 17px 44px}.page-heading h1{font-size:28px}.card{padding:19px}.account-grid,.password-fields{grid-template-columns:1fr}.account-form{padding:0 0 19px;border-right:0;border-bottom:1px solid #e8edf3}.password-actions,.account-footer{align-items:stretch;flex-direction:column}.compact-button,.logout{width:100%}}@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
