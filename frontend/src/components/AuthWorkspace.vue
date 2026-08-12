<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { GraduationCap, LoaderCircle, LockKeyhole, UserRound } from '@lucide/vue'

export type SignedInUser = { id: string; username: string; display_name: string }

const emit = defineEmits<{ authenticated: [user: SignedInUser] }>()
const mode = ref<'login' | 'register'>('login')
const isLoading = ref(true)
const isSubmitting = ref(false)
const username = ref('')
const displayName = ref('')
const password = ref('')
const errorMessage = ref('')

onMounted(async () => {
  try {
    const response = await fetch('/api/auth/bootstrap')
    const payload = await response.json()
    mode.value = payload.has_users ? 'login' : 'register'
  } catch {
    errorMessage.value = '暂时无法连接 MistakeMate 服务。'
  } finally {
    isLoading.value = false
  }
})

async function submit() {
  if (isSubmitting.value) return
  isSubmitting.value = true
  errorMessage.value = ''
  try {
    const body = mode.value === 'register'
      ? { username: username.value, display_name: displayName.value, password: password.value }
      : { username: username.value, password: password.value }
    const response = await fetch(`/api/auth/${mode.value}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => ({ detail: '登录请求未完成，请重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    emit('authenticated', payload)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登录请求未完成，请重试。'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card" aria-labelledby="auth-title">
      <div class="brand-mark" aria-hidden="true"><GraduationCap :size="25" /></div>
      <p class="brand-name">MistakeMate</p>
      <h1 id="auth-title">{{ mode === 'register' ? '创建第一个账号' : '欢迎回来' }}</h1>
      <p class="intro">{{ mode === 'register' ? '账号用于保护错题、打印模板和 AI 密钥。已有错题会自动归入这个账号。' : '登录后继续整理、复练和打印错题。' }}</p>

      <div v-if="isLoading" class="loading" aria-live="polite"><LoaderCircle class="spin" :size="20" />正在检查账号状态…</div>
      <form v-else @submit.prevent="submit">
        <label for="auth-username">用户名</label>
        <div class="input-wrap"><UserRound :size="18" /><input id="auth-username" v-model.trim="username" autocomplete="username" required minlength="3" placeholder="字母、数字或下划线" /></div>

        <template v-if="mode === 'register'">
          <label for="auth-display-name">显示名称</label>
          <div class="input-wrap"><UserRound :size="18" /><input id="auth-display-name" v-model.trim="displayName" autocomplete="name" required maxlength="64" placeholder="例如：陈晨家长" /></div>
        </template>

        <label for="auth-password">密码</label>
        <div class="input-wrap"><LockKeyhole :size="18" /><input id="auth-password" v-model="password" type="password" :autocomplete="mode === 'register' ? 'new-password' : 'current-password'" required :minlength="mode === 'register' ? 8 : 1" placeholder="至少 8 位" /></div>

        <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
        <button class="submit-button" type="submit" :disabled="isSubmitting">
          <LoaderCircle v-if="isSubmitting" class="spin" :size="18" />
          {{ isSubmitting ? '请稍候…' : mode === 'register' ? '创建并进入' : '登录' }}
        </button>
      </form>
      <button v-if="!isLoading" class="mode-button" type="button" @click="mode = mode === 'login' ? 'register' : 'login'; errorMessage = ''">
        {{ mode === 'login' ? '没有账号？创建账号' : '已有账号？返回登录' }}
      </button>
    </section>
  </main>
</template>

<style scoped>
.auth-page{min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 20% 10%,#eaf3ff 0,transparent 36%),#f5f8fc;color:#203a57}.auth-card{width:min(100%,430px);padding:40px;border:1px solid #dce6f1;border-radius:20px;background:#fff;box-shadow:0 18px 50px rgba(39,73,112,.12)}.brand-mark{display:grid;width:48px;height:48px;place-items:center;color:#fff;border-radius:13px;background:#2f6de1;box-shadow:0 8px 18px rgba(47,109,225,.25)}.brand-name{margin:16px 0 7px;color:#315f9b;font-size:13px;font-weight:800;letter-spacing:.3px}.auth-card h1{margin:0;font-size:29px;letter-spacing:-.6px}.intro{margin:10px 0 28px;color:#647c95;font-size:13px;line-height:1.7}.auth-card form{display:grid;gap:9px}.auth-card label{margin-top:6px;color:#3b5570;font-size:13px;font-weight:700}.input-wrap{display:flex;align-items:center;gap:9px;min-height:48px;padding:0 13px;color:#7590aa;border:1px solid #cfdce9;border-radius:9px;background:#fbfdff}.input-wrap:focus-within{border-color:#3975cf;box-shadow:0 0 0 3px rgba(57,117,207,.13)}.input-wrap input{min-width:0;flex:1;height:44px;color:#213c59;border:0;outline:0;background:transparent;font:inherit}.error{margin:6px 0 0;padding:10px 12px;color:#9e4033;border-radius:8px;background:#fff3f1;font-size:12px;line-height:1.5}.submit-button{display:flex;align-items:center;justify-content:center;gap:8px;min-height:48px;margin-top:11px;color:#fff;border:0;border-radius:9px;background:#2f6de1;font-weight:800;cursor:pointer}.submit-button:hover{background:#245cc5}.submit-button:disabled{cursor:wait;opacity:.68}.mode-button{display:block;min-height:44px;margin:14px auto 0;padding:0 8px;color:#315f9b;border:0;background:transparent;font-size:13px;font-weight:700;cursor:pointer}.loading{display:flex;align-items:center;gap:9px;min-height:90px;color:#647c95;font-size:13px}.spin{animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:520px){.auth-page{padding:14px}.auth-card{padding:28px 21px;border-radius:15px}}@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
