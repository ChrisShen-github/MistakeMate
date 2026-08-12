<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Bell,
  BookOpenCheck,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  FilePlus2,
  FolderOpen,
  GraduationCap,
  LayoutDashboard,
  Menu,
  MoreHorizontal,
  Printer,
  Sparkles,
  Star,
  Target,
  Upload,
  X,
} from '@lucide/vue'
import UploadWorkspace from './components/UploadWorkspace.vue'
import MistakeLibrary from './components/MistakeLibrary.vue'
import BatchReview from './components/BatchReview.vue'
import PrintWorkspace from './components/PrintWorkspace.vue'

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
const currentView = ref<'dashboard' | 'upload' | 'library' | 'review' | 'print'>('dashboard')
const previousView = ref<'dashboard' | 'library'>('dashboard')
const previousPrintView = ref<'dashboard' | 'library'>('dashboard')
const activeBatchId = ref('')
const sidebarOpen = ref(false)
const notice = ref('')
const isStartingReview = ref(false)

const questions = [
  { subject: '数学', tag: '分数加减法', title: '计算：3/4 − 2/9 + 5/12', level: '高价值', stars: 2, due: '今天', color: 'blue' },
  { subject: '数学', tag: '长方形面积', title: '一块长方形菜地的面积是多少？', level: '需巩固', stars: 3, due: '今天', color: 'orange' },
  { subject: '英语', tag: '一般现在时', title: '选择正确的动词形式填空', level: '高价值', stars: 2, due: '明天', color: 'purple' },
]

const subjects = [
  { name: '数学', count: 42, progress: 68, tone: 'blue' },
  { name: '英语', count: 18, progress: 74, tone: 'purple' },
  { name: '语文', count: 12, progress: 81, tone: 'orange' },
]

const activeTitle = computed(() => activeNav.value === '今日任务' ? '今天，先攻克最值得重做的题。' : activeNav.value)
const currentCrumb = computed(() => currentView.value === 'upload' ? '上传错题' : currentView.value === 'library' ? '我的错题' : currentView.value === 'review' ? '检查错题' : currentView.value === 'print' ? '错题集打印' : activeNav.value)

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

function openPrint() {
  previousPrintView.value = currentView.value === 'library' ? 'library' : 'dashboard'
  activeNav.value = '错题集'
  currentView.value = 'print'
  sidebarOpen.value = false
}

function closePrint() {
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

function startReview() {
  if (isStartingReview.value) return
  isStartingReview.value = true
  window.setTimeout(() => {
    isStartingReview.value = false
    showNotice('今日复练已开始，第一题将从分数加减法开始。')
  }, 500)
}

function onRecognitionQueued(count: number) {
  activeNav.value = '我的错题'
  currentView.value = 'library'
  showNotice(`已上传 ${count} 个文件，下一步将进入题目检查。`)
}
</script>

<template>
  <div class="app-shell">
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
        <button class="nav-item muted" @click="showNotice('帮助中心将在正式版开放。')"><CircleHelp :size="19" />使用帮助</button>
        <div class="child-switcher">
          <div class="avatar">晨</div>
          <div><strong>陈晨</strong><span>小学五年级</span></div>
          <MoreHorizontal :size="18" />
        </div>
      </div>
    </aside>

    <div v-if="sidebarOpen" class="sidebar-mask" @click="sidebarOpen = false"></div>

    <main id="main-content" class="main-content" tabindex="-1">
      <header class="topbar">
        <button class="mobile-menu icon-button" aria-label="打开导航" @click="sidebarOpen = true"><Menu :size="21" /></button>
        <div class="crumb"><span>陈晨的错题本</span><ChevronRight :size="15" /><strong>{{ currentCrumb }}</strong></div>
        <div class="top-actions">
          <button class="bell icon-button" aria-label="查看提醒" @click="showNotice('今天有 8 道题等待复练。')"><Bell :size="20" /><i></i></button>
          <button class="profile" @click="showNotice('孩子档案设置将在后续开放。')"><div class="avatar">晨</div><span>陈晨</span></button>
        </div>
      </header>

      <UploadWorkspace v-if="currentView === 'upload'" @back="closeUpload" @queued="onRecognitionQueued" />
      <MistakeLibrary v-else-if="currentView === 'library'" @upload="openUpload" @print="openPrint" @open="openBatch($event.id)" />
      <BatchReview v-else-if="currentView === 'review'" :batch-id="activeBatchId" @back="openLibrary" />
      <PrintWorkspace v-else-if="currentView === 'print'" @back="closePrint" />

      <section v-else class="dashboard">
        <div class="welcome-row">
          <div>
            <p class="eyebrow">星期二 · 8 月 11 日</p>
            <h1>{{ activeTitle }}</h1>
            <p class="welcome-copy">把时间用在真正没掌握的地方，而不是重复抄写。</p>
          </div>
          <button class="secondary-button" @click="showNotice('正在准备本周学习报告。')"><ClipboardList :size="18" />查看报告</button>
        </div>

        <section class="hero-card">
          <div class="hero-content">
            <div class="hero-icon"><Target :size="24" /></div>
            <div>
              <p class="hero-kicker">今日复练</p>
              <h2>8 道题，预计 <strong>18 分钟</strong></h2>
              <p>其中 5 道来自“分数加减法”，是最近最需要巩固的知识点。</p>
            </div>
          </div>
          <button class="primary-button" :disabled="isStartingReview" @click="startReview">
            {{ isStartingReview ? '正在开始…' : '开始复练' }} <ChevronRight v-if="!isStartingReview" :size="18" />
          </button>
          <div class="hero-decoration decoration-one"></div>
          <div class="hero-decoration decoration-two"></div>
        </section>

        <section class="summary-grid" aria-label="学习概览">
          <article class="summary-card">
            <div class="summary-icon blue"><FilePlus2 :size="20" /></div>
            <div><span>本周新增错题</span><strong>16 <small>道</small></strong></div>
            <p class="trend positive">较上周 -4 道</p>
          </article>
          <article class="summary-card">
            <div class="summary-icon gold"><Sparkles :size="20" /></div>
            <div><span>值得反复练习</span><strong>23 <small>道</small></strong></div>
            <p class="trend neutral">AI 已为你筛选</p>
          </article>
          <article class="summary-card">
            <div class="summary-icon green"><BookOpenCheck :size="20" /></div>
            <div><span>已掌握错题</span><strong>57 <small>道</small></strong></div>
            <p class="trend positive">本月 +12 道</p>
          </article>
        </section>

        <section class="content-grid">
          <article class="panel question-panel">
            <div class="panel-heading">
              <div><p class="section-kicker">优先完成</p><h2>待复练的错题</h2></div>
              <button class="text-button" @click="openLibrary">查看全部 <ChevronRight :size="16" /></button>
            </div>
            <div class="question-list">
              <button v-for="question in questions" :key="question.title" class="question-row" @click="showNotice(`已打开：${question.title}`)">
                <span class="subject-dot" :class="question.color"></span>
                <div class="question-info"><span class="question-meta">{{ question.subject }} · {{ question.tag }}</span><strong>{{ question.title }}</strong></div>
                <div class="question-rating"><span class="value-tag" :class="question.level === '高价值' ? 'high' : 'mid'">{{ question.level }}</span><span class="stars"><Star v-for="star in question.stars" :key="star" :size="14" fill="currentColor" /></span></div>
                <span class="due-date">{{ question.due }}</span>
                <ChevronRight class="row-chevron" :size="17" />
              </button>
            </div>
          </article>

          <aside class="right-column">
            <article class="panel focus-panel">
              <div class="panel-heading compact"><div><p class="section-kicker">本周薄弱点</p><h2>知识点掌握</h2></div><button class="icon-button mini" aria-label="更多知识点"><MoreHorizontal :size="19" /></button></div>
              <div class="subject-progress" v-for="subject in subjects" :key="subject.name">
                <div class="progress-label"><span><i :class="subject.tone"></i>{{ subject.name }}</span><strong>{{ subject.progress }}%</strong></div>
                <div class="progress-track"><span :class="subject.tone" :style="{ width: `${subject.progress}%` }"></span></div>
                <small>待巩固 {{ subject.count }} 道</small>
              </div>
              <button class="focus-link" @click="showNotice('已筛选出分数加减法专项练习。')">先练分数加减法 <ChevronRight :size="16" /></button>
            </article>

            <article class="print-card">
              <div class="print-icon"><Printer :size="21" /></div>
              <div><p>错题集打印</p><strong>选择已确认题目</strong><span>练习版与答案版均可打印</span></div>
              <button class="white-button" @click="openPrint">去打印</button>
            </article>
          </aside>
        </section>
      </section>
    </main>

    <Transition name="toast"><div v-if="notice" class="toast" role="status" aria-live="polite">{{ notice }}</div></Transition>
  </div>
</template>
