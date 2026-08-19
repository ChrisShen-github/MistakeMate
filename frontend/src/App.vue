<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Bell,
  BookOpenCheck,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  FolderOpen,
  GraduationCap,
  LayoutDashboard,
  LoaderCircle,
  Menu,
  MoreHorizontal,
  ScanText,
  SlidersHorizontal,
  Sparkles,
  Upload,
  X,
} from '@lucide/vue'
import UploadWorkspace from './components/UploadWorkspace.vue'
import MistakeLibrary from './components/MistakeLibrary.vue'
import BatchReview from './components/BatchReview.vue'
import PrintWorkspace from './components/PrintWorkspace.vue'
import AuthWorkspace, { type SignedInUser } from './components/AuthWorkspace.vue'
import SettingsWorkspace from './components/SettingsWorkspace.vue'
import AiSettingsWorkspace from './components/AiSettingsWorkspace.vue'
import OcrModelSettingsWorkspace from './components/OcrModelSettingsWorkspace.vue'
import PreferencesWorkspace from './components/PreferencesWorkspace.vue'
import TodayTasksWorkspace from './components/TodayTasksWorkspace.vue'

type NavItem = {
  label: string
  icon: typeof LayoutDashboard
}

const navigation: NavItem[] = [
  { label: '今日任务', icon: LayoutDashboard },
  { label: '我的错题', icon: FolderOpen },
  { label: '错题集', icon: BookOpenCheck },
  { label: '学习报告', icon: ClipboardList },
]

const activeNav = ref('今日任务')
type AppView = 'dashboard' | 'upload' | 'library' | 'review' | 'print' | 'settings' | 'ai-settings' | 'ocr-models' | 'preferences'
const currentView = ref<AppView>('dashboard')
const settingsReturnView = ref<AppView>('dashboard')
const previousView = ref<'dashboard' | 'library'>('dashboard')
const previousPrintView = ref<'dashboard' | 'library'>('dashboard')
const activeBatchId = ref('')
const requestedPrintQuestionIds = ref<string[]>([])
const sidebarOpen = ref(false)
const notice = ref('')
const authLoading = ref(true)
const currentUser = ref<SignedInUser | null>(null)

const currentCrumb = computed(() => currentView.value === 'upload' ? '上传错题' : currentView.value === 'library' ? '我的错题' : currentView.value === 'review' ? '检查错题' : currentView.value === 'print' ? '错题集打印' : currentView.value === 'settings' ? '账户设置' : currentView.value === 'ai-settings' ? 'AI 设置' : currentView.value === 'ocr-models' ? 'OCR 模型' : currentView.value === 'preferences' ? '偏好设置' : activeNav.value)
const displayInitial = computed(() => currentUser.value?.display_name.slice(0, 1) || 'M')

function showNotice(message: string) {
  notice.value = message
  window.setTimeout(() => {
    notice.value = ''
  }, 2600)
}

function openUpload() {
  previousView.value = currentView.value === 'library' ? 'library' : 'dashboard'
  currentView.value = 'upload'
  sidebarOpen.value = false
}

function openLibrary() {
  activeNav.value = '我的错题'
  currentView.value = 'library'
  sidebarOpen.value = false
}

function closeUpload() {
  currentView.value = previousView.value
  activeNav.value = previousView.value === 'library' ? '我的错题' : '今日任务'
}

function openBatch(batchId: string) {
  activeBatchId.value = batchId
  currentView.value = 'review'
}

function openPrint(questionIds: string[] = []) {
  requestedPrintQuestionIds.value = questionIds
  previousPrintView.value = currentView.value === 'library' ? 'library' : 'dashboard'
  activeNav.value = '错题集'
  currentView.value = 'print'
  sidebarOpen.value = false
}

function closePrint() {
  requestedPrintQuestionIds.value = []
  if (previousPrintView.value === 'library') {
    openLibrary()
  } else {
    activeNav.value = '今日任务'
    currentView.value = 'dashboard'
  }
}

function selectNav(label: string) {
  if (label === '错题集') {
    openPrint()
    return
  }
  activeNav.value = label
  currentView.value = label === '我的错题' ? 'library' : 'dashboard'
  sidebarOpen.value = false
}

function onRecognitionQueued(count: number) {
  activeNav.value = '我的错题'
  currentView.value = 'library'
  showNotice(`已创建 ${count} 组待处理错题，正在按所选流程处理。`)
}

function onAuthenticated(user: SignedInUser) {
  currentUser.value = user
  const printIds = new URLSearchParams(window.location.search).get('print')?.split(',').filter(Boolean) || []
  if (printIds.length) {
    requestedPrintQuestionIds.value = printIds
    activeNav.value = '错题集'
    currentView.value = 'print'
  } else currentView.value = 'dashboard'
}

function onProfileUpdated(user: SignedInUser) {
  currentUser.value = user
  showNotice('账户资料已更新。')
}

function openSettings() {
  if (!['settings', 'ai-settings', 'ocr-models', 'preferences'].includes(currentView.value)) settingsReturnView.value = currentView.value
  currentView.value = 'settings'
  sidebarOpen.value = false
}

function openAiSettings() {
  if (!['settings', 'ai-settings', 'ocr-models', 'preferences'].includes(currentView.value)) settingsReturnView.value = currentView.value
  currentView.value = 'ai-settings'
  sidebarOpen.value = false
}

function openOcrModels() {
  if (!['settings', 'ai-settings', 'ocr-models', 'preferences'].includes(currentView.value)) settingsReturnView.value = currentView.value
  currentView.value = 'ocr-models'
  sidebarOpen.value = false
}

function openPreferences() {
  if (!['settings', 'ai-settings', 'ocr-models', 'preferences'].includes(currentView.value)) settingsReturnView.value = currentView.value
  currentView.value = 'preferences'
  sidebarOpen.value = false
}

function closeSettings() {
  currentView.value = ['settings', 'ai-settings', 'ocr-models', 'preferences'].includes(settingsReturnView.value) ? 'dashboard' : settingsReturnView.value
}

async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' }).catch(() => undefined)
  currentUser.value = null
  currentView.value = 'dashboard'
}

onMounted(async () => {
  try {
    const response = await fetch('/api/auth/me')
    if (response.ok) {
      currentUser.value = await response.json()
      const printIds = new URLSearchParams(window.location.search).get('print')?.split(',').filter(Boolean) || []
      if (printIds.length) {
        requestedPrintQuestionIds.value = printIds
        activeNav.value = '错题集'
        currentView.value = 'print'
      }
    }
  } finally {
    authLoading.value = false
  }
})
</script>

<template>
  <main v-if="authLoading" class="auth-check" aria-live="polite"><LoaderCircle :size="23" />正在打开 MistakeMate…</main>
  <AuthWorkspace v-else-if="!currentUser" @authenticated="onAuthenticated" />
  <div v-else class="app-shell">
    <a class="skip-link" href="#main-content">跳到主要内容</a>
    <aside class="sidebar" :class="{ 'is-open': sidebarOpen }" aria-label="主导航">
      <div class="brand-row">
        <div class="brand-mark" aria-hidden="true"><GraduationCap :size="22" /></div>
        <div class="brand-name">MistakeMate<span>让错题有价值</span></div>
        <button class="mobile-close icon-button" aria-label="关闭导航" @click="sidebarOpen = false"><X :size="19" /></button>
      </div>

      <button class="upload-button" @click="openUpload">
        <Upload :size="18" />
        上传错题
      </button>

      <nav class="nav-list">
        <button
          v-for="item in navigation"
          :key="item.label"
          class="nav-item"
          :class="{ active: activeNav === item.label }"
          :aria-current="activeNav === item.label ? 'page' : undefined"
          @click="selectNav(item.label)"
        >
          <component :is="item.icon" :size="19" />
          {{ item.label }}
        </button>
      </nav>

      <div class="sidebar-bottom">
        <button class="nav-item muted" :class="{ active: currentView === 'ocr-models' }" @click="openOcrModels"><ScanText :size="19" />OCR 模型</button>
        <button class="nav-item muted" :class="{ active: currentView === 'ai-settings' }" @click="openAiSettings"><Sparkles :size="19" />AI 设置</button>
        <button class="nav-item muted" :class="{ active: currentView === 'preferences' }" @click="openPreferences"><SlidersHorizontal :size="19" />偏好设置</button>
        <button class="nav-item muted" @click="showNotice('帮助中心将在正式版开放。')"><CircleHelp :size="19" />使用帮助</button>
        <div class="child-switcher">
          <div class="avatar">{{ displayInitial }}</div>
          <div><strong>{{ currentUser.display_name }}</strong><span>@{{ currentUser.username }}</span></div>
          <MoreHorizontal :size="18" />
        </div>
      </div>
    </aside>

    <div v-if="sidebarOpen" class="sidebar-mask" @click="sidebarOpen = false"></div>

    <main id="main-content" class="main-content" tabindex="-1">
      <header class="topbar">
        <button class="mobile-menu icon-button" aria-label="打开导航" @click="sidebarOpen = true"><Menu :size="21" /></button>
        <div class="crumb"><span>{{ currentUser.display_name }}的错题本</span><ChevronRight :size="15" /><strong>{{ currentCrumb }}</strong></div>
        <div class="top-actions">
          <button class="bell icon-button" aria-label="查看提醒" @click="showNotice('今天有 8 道题等待复练。')"><Bell :size="20" /><i></i></button>
          <button class="profile" aria-label="打开账户设置" @click="openSettings"><div class="avatar">{{ displayInitial }}</div><span>{{ currentUser.display_name }}</span></button>
        </div>
      </header>

      <UploadWorkspace v-if="currentView === 'upload'" :notebook-name="`${currentUser.display_name}的错题本`" @back="closeUpload" @queued="onRecognitionQueued" @configure-ai="openAiSettings" />
      <MistakeLibrary v-else-if="currentView === 'library'" @upload="openUpload" @print="openPrint" @open="openBatch($event.id)" />
      <BatchReview v-else-if="currentView === 'review'" :batch-id="activeBatchId" @back="openLibrary" @configure-ai="openAiSettings" />
      <PrintWorkspace v-else-if="currentView === 'print'" :initial-question-ids="requestedPrintQuestionIds" @back="closePrint" />
      <SettingsWorkspace v-else-if="currentView === 'settings'" :user="currentUser" @back="closeSettings" @logout="logout" @profile-updated="onProfileUpdated" />
      <AiSettingsWorkspace v-else-if="currentView === 'ai-settings'" @back="closeSettings" />
      <OcrModelSettingsWorkspace v-else-if="currentView === 'ocr-models'" @back="closeSettings" />
      <PreferencesWorkspace v-else-if="currentView === 'preferences'" @back="closeSettings" />

      <TodayTasksWorkspace v-else @open-batch="openBatch" />
    </main>

    <Transition name="toast"><div v-if="notice" class="toast" role="status" aria-live="polite">{{ notice }}</div></Transition>
  </div>
</template>
