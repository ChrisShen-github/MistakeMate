<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, CheckCircle2, FileText, LoaderCircle, ScanText, Sparkles } from '@lucide/vue'

const emit = defineEmits<{ back: [] }>()
type Workflow = 'ask' | 'text' | 'clean'

const workflow = ref<Workflow>('ask')
const isLoading = ref(true)
const isSaving = ref(false)
const message = ref('')
const errorMessage = ref('')

const choices: Array<{ value: Workflow; title: string; description: string }> = [
  { value: 'ask', title: '每次上传时选择', description: '推荐。上传页会显示两种流程，由你按这次题目的情况决定。' },
  { value: 'text', title: '可编辑文字版', description: '默认使用 AI 识别题目；适合编辑、分类、组卷和针对性练习。' },
  { value: 'clean', title: '清洁原图版', description: '默认去除孩子笔迹并保留原排版；适合图表、公式、表格较多的题。' },
]

async function loadPreferences() {
  try {
    const response = await fetch('/api/settings/preferences')
    const payload = await response.json().catch(() => ({ detail: '无法读取偏好设置。' }))
    if (!response.ok) throw new Error(payload.detail)
    workflow.value = payload.default_upload_workflow
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '无法读取偏好设置。'
  } finally {
    isLoading.value = false
  }
}

async function savePreferences() {
  if (isSaving.value) return
  isSaving.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    const response = await fetch('/api/settings/preferences', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ default_upload_workflow: workflow.value }),
    })
    const payload = await response.json().catch(() => ({ detail: '保存失败，请稍后重试。' }))
    if (!response.ok) throw new Error(payload.detail)
    message.value = '上传默认流程已保存。下次上传时会自动带入，仍可临时切换。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存失败，请稍后重试。'
  } finally {
    isSaving.value = false
  }
}

function choiceIcon(value: Workflow) { return value === 'text' ? FileText : value === 'clean' ? Sparkles : ScanText }

onMounted(loadPreferences)
</script>

<template>
  <section class="preferences-page" aria-labelledby="preferences-title">
    <button class="back-button" type="button" @click="emit('back')"><ArrowLeft :size="18" />返回</button>
    <header class="page-heading"><p>上传与打印</p><h1 id="preferences-title">偏好设置</h1><span>设置新上传错题时的默认处理方式；每次上传仍可临时更改。</span></header>
    <div v-if="isLoading" class="loading" aria-live="polite"><LoaderCircle class="spin" :size="20" />正在读取偏好设置…</div>
    <form v-else class="preferences-card" @submit.prevent="savePreferences">
      <div class="card-heading"><div class="icon"><Sparkles :size="20" /></div><div><h2>默认上传流程</h2><span>选择默认值不会删除任何原图，也不会阻止你在上传时改选。</span></div></div>
      <fieldset class="workflow-list"><legend>新错题默认怎么处理？</legend><label v-for="choice in choices" :key="choice.value" class="workflow-choice" :class="{ active: workflow === choice.value }"><input v-model="workflow" type="radio" name="workflow" :value="choice.value" /><component :is="choiceIcon(choice.value)" :size="20" /><span><strong>{{ choice.title }}</strong><small>{{ choice.description }}</small></span><CheckCircle2 v-if="workflow === choice.value" :size="19" /></label></fieldset>
      <p class="notice"><strong>使用建议：</strong>文字、公式和知识点需要后续编辑时选“可编辑文字版”；题面有复杂图表、原排版更重要时选“清洁原图版”。</p>
      <p v-if="message" class="success" role="status"><CheckCircle2 :size="16" />{{ message }}</p><p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
      <button class="save-button" type="submit" :disabled="isSaving"><LoaderCircle v-if="isSaving" class="spin" :size="17" />{{ isSaving ? '正在保存…' : '保存偏好' }}</button>
    </form>
  </section>
</template>

<style scoped>
.preferences-page{max-width:920px;margin:0 auto;padding:32px 44px 64px;color:#263f5a}.back-button{display:flex;align-items:center;gap:7px;min-height:44px;padding:0;color:#315f9b;border:0;background:transparent;font-size:13px;font-weight:700;cursor:pointer}.page-heading{margin:15px 0 26px}.page-heading>p{margin:0 0 6px;color:#7189a3;font-size:12px;font-weight:800;letter-spacing:.3px}.page-heading h1{margin:0;color:#1e3553;font-size:32px;letter-spacing:-.8px}.page-heading>span{display:block;margin-top:9px;color:#687f97;font-size:13px;line-height:1.6}.preferences-card{padding:27px;border:1px solid #dce5ef;border-radius:15px;background:#fff;box-shadow:0 3px 12px rgba(33,72,113,.035)}.card-heading{display:flex;align-items:flex-start;gap:13px;margin-bottom:22px}.icon{display:grid;width:42px;height:42px;place-items:center;color:#6d4fd0;border-radius:11px;background:#f0ebff}.card-heading h2{margin:1px 0 0;color:#29435f;font-size:19px}.card-heading span{display:block;margin-top:4px;color:#72869a;font-size:12px;line-height:1.55}.workflow-list{display:grid;gap:10px;margin:0;padding:0;border:0}.workflow-list legend{margin-bottom:9px;color:#3b5570;font-size:13px;font-weight:800}.workflow-choice{display:grid;grid-template-columns:20px 22px minmax(0,1fr) 20px;align-items:center;gap:11px;min-height:76px;padding:12px;color:#5d7288;border:1px solid #d9e3ed;border-radius:10px;background:#fff;cursor:pointer}.workflow-choice:hover{border-color:#9dbde1;background:#fbfdff}.workflow-choice.active{color:#295eac;border-color:#78a8df;background:#f4f8ff;box-shadow:0 0 0 3px rgba(65,123,209,.1)}.workflow-choice input{width:18px;height:18px;margin:0;accent-color:#2868cc}.workflow-choice>span{display:grid;gap:3px}.workflow-choice strong{font-size:13px}.workflow-choice small{color:#74879b;font-size:11px;line-height:1.5}.workflow-choice.active>svg:last-child{color:#2b8a67}.notice{margin:17px 0 0;padding:11px 12px;color:#526f8a;border-radius:8px;background:#f5f8fb;font-size:12px;line-height:1.65}.save-button{display:flex;min-height:44px;align-items:center;justify-content:center;gap:7px;margin:20px 0 0 auto;padding:0 17px;color:#fff;border:0;border-radius:8px;background:#2f6de1;font-size:13px;font-weight:800;cursor:pointer}.save-button:disabled{cursor:wait;opacity:.65}.success{display:flex;align-items:center;gap:7px;margin:15px 0 0;color:#23775c;font-size:12px;font-weight:600}.error{margin:15px 0 0;padding:10px 12px;color:#9e4033;border-radius:8px;background:#fff3f1;font-size:12px;line-height:1.5}.loading{display:flex;align-items:center;gap:9px;min-height:180px;color:#687f97}.spin{animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:760px){.preferences-page{padding:22px 17px 44px}.page-heading h1{font-size:28px}.preferences-card{padding:19px}.workflow-choice{grid-template-columns:20px 21px minmax(0,1fr) 18px;gap:9px;min-height:82px}.save-button{width:100%}}@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
