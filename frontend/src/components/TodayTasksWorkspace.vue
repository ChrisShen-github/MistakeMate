<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { Check, ChevronRight, CircleAlert, ClipboardCheck, LoaderCircle, RotateCcw, Target, X } from '@lucide/vue'
import QuestionText from './QuestionText.vue'
import type { TodayTask, TodayTasks } from '../types/questions'

const emit = defineEmits<{ openBatch: [batchId: string] }>()

const data = ref<TodayTasks | null>(null)
const loading = ref(true)
const error = ref('')
const savingQuestionId = ref('')
const selectedQuestionId = ref('')
const detailRef = ref<HTMLElement | null>(null)

const selectedTask = computed(() => data.value?.tasks.find((task) => task.question.id === selectedQuestionId.value) ?? data.value?.tasks[0] ?? null)
const pendingCount = computed(() => Math.max(0, (data.value?.planned_count ?? 0) - (data.value?.completed_count ?? 0)))
const dateLabel = computed(() => {
  if (!data.value?.date) return '今天'
  const [, month, day] = data.value.date.split('-')
  return `${Number(month)} 月 ${Number(day)} 日`
})

function titleOf(task: TodayTask) {
  const text = task.question.stem.trim().replace(/\s+/g, ' ')
  if (text) return text.slice(0, 56) + (text.length > 56 ? '…' : '')
  return task.question.is_image_only ? '清洁原题图片' : '这道错题'
}

function cleanImageUrl(task: TodayTask) {
  const fileId = task.question.clean_source_file_id
  return fileId ? `/api/mistakes/${task.batch_id}/files/${fileId}/clean-image` : ''
}

function figureUrl(task: TodayTask, figureId: string) {
  return `/api/mistakes/${task.batch_id}/questions/${task.question.id}/figures/${figureId}`
}

function formatAttempts(task: TodayTask) {
  if (!task.total_attempts) return '还没有练习记录'
  return `已练 ${task.total_attempts} 次 · 正确 ${task.correct_attempts} · 错误 ${task.incorrect_attempts}`
}

async function loadTasks(keepSelection = true) {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/tasks/today')
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || '今日任务暂时无法加载。')
    data.value = payload as TodayTasks
    const hasSelected = keepSelection && data.value.tasks.some((task) => task.question.id === selectedQuestionId.value)
    if (!hasSelected) selectedQuestionId.value = data.value.tasks.find((task) => !task.completed_today)?.question.id ?? data.value.tasks[0]?.question.id ?? ''
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '今日任务暂时无法加载。'
  } finally {
    loading.value = false
  }
}

async function markAttempt(result: 'correct' | 'incorrect') {
  const task = selectedTask.value
  if (!task || savingQuestionId.value) return
  savingQuestionId.value = task.question.id
  error.value = ''
  try {
    const response = await fetch(`/api/tasks/today/questions/${task.question.id}/attempts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || '标记没有保存成功，请再试一次。')
    await loadTasks(true)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '标记没有保存成功，请再试一次。'
  } finally {
    savingQuestionId.value = ''
  }
}

async function startReview() {
  const nextTask = data.value?.tasks.find((task) => !task.completed_today)
  if (!nextTask) return
  selectedQuestionId.value = nextTask.question.id
  await nextTick()
  detailRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(() => { void loadTasks(false) })
</script>

<template>
  <section class="today-workspace" aria-labelledby="today-heading">
    <header class="today-welcome">
      <div>
        <p class="eyebrow">{{ dateLabel }} · 今日任务</p>
        <h1 id="today-heading">今天，先攻克最值得重做的题。</h1>
        <p>每做完一道就标记结果；再次做错的题会自动排到之后复习的前面。</p>
      </div>
    </header>

    <section v-if="loading" class="today-loading" aria-live="polite"><LoaderCircle :size="21" />正在整理今天该练的题…</section>
    <section v-else-if="error && !data" class="today-empty error-state"><CircleAlert :size="23" /><strong>今日任务没有加载成功</strong><span>{{ error }}</span><button type="button" class="retry-button" @click="loadTasks(false)"><RotateCcw :size="17" />重新加载</button></section>

    <template v-else-if="data">
      <section class="today-hero">
        <div class="hero-copy">
          <div class="hero-icon"><Target :size="24" /></div>
          <div>
            <p>今日复练</p>
            <h2 v-if="data.target_count">{{ data.completed_count }}/{{ data.target_count }} 道已完成</h2>
            <h2 v-else>还没有可复习的题目</h2>
            <span v-if="data.completed_count && data.accuracy_rate !== null">今天正确率 {{ data.accuracy_rate }}% · 做错 {{ data.incorrect_count }} 道会优先安排下次复习</span>
            <span v-else-if="data.target_count">先完成 {{ data.target_count }} 道，系统会从明天开始按记忆节奏安排复习。</span>
            <span v-else>先在“上传错题”中确认题目，确认后的题会自动进入这里。</span>
          </div>
        </div>
        <button v-if="pendingCount" type="button" class="start-button" @click="startReview">{{ data.completed_count ? '继续复练' : '开始复练' }} <ChevronRight :size="18" /></button>
        <div v-else-if="data.target_count" class="complete-badge"><Check :size="17" />今日已完成</div>
      </section>

      <section class="today-stats" aria-label="今日练习统计">
        <article><span>待完成</span><strong>{{ pendingCount }} <small>道</small></strong></article>
        <article><span>今天正确</span><strong>{{ data.correct_count }} <small>道</small></strong></article>
        <article><span>仍然做错</span><strong>{{ data.incorrect_count }} <small>道</small></strong></article>
      </section>

      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <section v-if="data.tasks.length" class="today-layout">
        <article class="task-list-panel">
          <div class="panel-title"><div><p>优先完成</p><h2>待复练的错题</h2></div><span>{{ data.planned_count }} 道</span></div>
          <div class="task-list">
            <button
              v-for="task in data.tasks"
              :key="task.question.id"
              type="button"
              class="task-row"
              :class="{ selected: selectedTask?.question.id === task.question.id, completed: task.completed_today, incorrect: task.today_result === 'incorrect' }"
              @click="selectedQuestionId = task.question.id"
            >
              <span class="task-state"><Check v-if="task.today_result === 'correct'" :size="15" /><X v-else-if="task.today_result === 'incorrect'" :size="15" /><span v-else></span></span>
              <span class="task-content"><small>{{ task.subject }} · {{ task.question.knowledge_points || task.question.question_type }}</small><strong>{{ titleOf(task) }}</strong><em>{{ task.priority_reason }}</em></span>
              <ChevronRight :size="17" />
            </button>
          </div>
        </article>

        <article ref="detailRef" class="task-detail-panel">
          <template v-if="selectedTask">
            <div class="detail-heading"><div><p>{{ selectedTask.subject }} · {{ selectedTask.source }}</p><h2>第 {{ selectedTask.question.position }} 题</h2></div><button type="button" class="source-button" @click="emit('openBatch', selectedTask.batch_id)">查看原错题 <ChevronRight :size="15" /></button></div>
            <div class="priority-note"><CircleAlert :size="17" />{{ selectedTask.priority_reason }}</div>
            <img v-if="selectedTask.question.is_image_only && cleanImageUrl(selectedTask)" class="clean-question-image" :src="cleanImageUrl(selectedTask)" alt="清洁后的原题" />
            <template v-else>
              <QuestionText :text="selectedTask.question.stem" />
              <div v-if="selectedTask.question.figures.length" class="question-figures">
                <img v-for="figure in selectedTask.question.figures" :key="figure.id" :src="figureUrl(selectedTask, figure.id)" alt="题目图形" />
              </div>
            </template>
            <ul v-if="!selectedTask.question.is_image_only && selectedTask.question.options.length" class="task-options"><li v-for="option in selectedTask.question.options" :key="option.label"><b>{{ option.label }}</b>{{ option.text }}</li></ul>
            <p class="attempt-history">{{ formatAttempts(selectedTask) }}</p>
            <div class="result-actions">
              <p>这次做得怎么样？</p>
              <div><button type="button" class="wrong-button" :disabled="Boolean(savingQuestionId)" @click="markAttempt('incorrect')"><LoaderCircle v-if="savingQuestionId === selectedTask.question.id" :size="18" /><X v-else :size="18" />还是做错了</button><button type="button" class="correct-button" :disabled="Boolean(savingQuestionId)" @click="markAttempt('correct')"><LoaderCircle v-if="savingQuestionId === selectedTask.question.id" :size="18" /><Check v-else :size="18" />这次做对了</button></div>
              <small v-if="selectedTask.completed_today">想修正刚才的标记？直接再次选择结果即可，今天的正确率会按最新标记计算。</small>
            </div>
          </template>
        </article>
      </section>
      <section v-else class="today-empty"><ClipboardCheck :size="26" /><strong>先确认一两道错题，再开始今日复练</strong><span>已确认的题目会自动进入今日任务；你不需要手动排计划。</span></section>
    </template>
  </section>
</template>

<style scoped>
.today-workspace { max-width: 1370px; margin: 0 auto; padding: 38px 44px 56px; }
.today-welcome { display: flex; align-items: end; justify-content: space-between; gap: 20px; }.today-welcome p { margin: 9px 0 0; color: #738499; font-size: 14px; }.today-welcome .eyebrow { margin: 0 0 8px; color: #8797a9; font-size: 12px; font-weight: 700; letter-spacing: .45px; }.today-welcome h1 { margin: 0; color: #162f50; font-size: clamp(25px,3vw,34px); letter-spacing: -.8px; }
.today-loading,.today-empty { display: grid; justify-items: center; gap: 9px; min-height: 225px; margin-top: 27px; padding: 28px; color: #6c7f94; text-align: center; background: #fff; border: 1px solid #e1e8ef; border-radius: 16px; }.today-loading { display: flex; align-items: center; justify-content: center; min-height: 154px; }.today-loading svg { animation: spin .8s linear infinite; }.today-empty strong { color: #284563; }.today-empty span { max-width: 440px; font-size: 13px; line-height: 1.7; }.error-state { color: #a45345; }.retry-button,.source-button { display: inline-flex; align-items: center; gap: 4px; min-height: 40px; padding: 8px 11px; color: #2864be; border: 1px solid #bdd0e8; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; }
.today-hero { position: relative; display: flex; align-items: center; justify-content: space-between; gap: 20px; min-height: 153px; margin-top: 29px; padding: 26px 31px; overflow: hidden; color: #fff; background: linear-gradient(115deg,#2b65cc,#3877df); border-radius: 17px; box-shadow: 0 15px 30px rgba(46,100,192,.18); }.hero-copy { display: flex; align-items: center; gap: 17px; }.hero-icon { display: grid; width: 47px; height: 47px; place-items: center; background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.2); border-radius: 14px; }.hero-copy p { margin: 0 0 3px; color: #caddff; font-size: 12px; font-weight: 700; letter-spacing: .5px; }.hero-copy h2 { margin: 0; font-size: 22px; letter-spacing: -.4px; }.hero-copy span { display: block; margin-top: 7px; color: #dce9ff; font-size: 13px; }.start-button,.complete-badge { display: inline-flex; align-items: center; gap: 4px; flex: 0 0 auto; min-height: 44px; padding: 11px 16px; border: 0; border-radius: 9px; font-size: 13px; font-weight: 800; }.start-button { color: #265bb9; background: #fff; }.complete-badge { color: #e4fff3; background: rgba(19,105,70,.23); border: 1px solid rgba(255,255,255,.25); }
.today-stats { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; margin: 19px 0; }.today-stats article { display: grid; gap: 4px; padding: 18px; background: #fff; border: 1px solid #e8edf1; border-radius: 13px; }.today-stats span { color: #8191a4; font-size: 12px; font-weight: 600; }.today-stats strong { color: #213a58; font-size: 24px; }.today-stats small { color: #8090a1; font-size: 12px; font-weight: 600; }.inline-error { margin: 0 0 14px; padding: 10px 12px; color: #a1473b; background: #fff1ef; border-radius: 8px; font-size: 13px; }
.today-layout { display: grid; grid-template-columns: minmax(290px,.82fr) minmax(0,1.5fr); gap: 19px; align-items: start; }.task-list-panel,.task-detail-panel { background: #fff; border: 1px solid #e1e8ef; border-radius: 14px; }.panel-title,.detail-heading { display: flex; align-items: center; justify-content: space-between; gap: 13px; padding: 20px 21px 16px; border-bottom: 1px solid #edf0f3; }.panel-title p,.detail-heading p { margin: 0 0 5px; color: #8b9aab; font-size: 11px; font-weight: 700; }.panel-title h2,.detail-heading h2 { margin: 0; color: #203954; font-size: 18px; }.panel-title > span { padding: 4px 7px; color: #336bbb; background: #eef5ff; border-radius: 6px; font-size: 11px; font-weight: 800; }.task-list { display: grid; }.task-row { display: grid; grid-template-columns: auto minmax(0,1fr) auto; align-items: center; gap: 10px; width: 100%; padding: 15px 16px; color: #29435f; text-align: left; border: 0; border-bottom: 1px solid #edf0f3; background: #fff; }.task-row:last-child { border-bottom: 0; }.task-row:hover,.task-row.selected { background: #f3f7fe; }.task-row.selected { box-shadow: inset 3px 0 #2b6bda; }.task-state { display: grid; width: 23px; height: 23px; place-items: center; color: #fff; border: 1px solid #c7d3e0; border-radius: 50%; }.task-row.completed .task-state { color: #fff; background: #45a579; border-color: #45a579; }.task-row.incorrect .task-state { background: #df7664; border-color: #df7664; }.task-content { display: grid; min-width: 0; gap: 4px; }.task-content small { color: #8495a7; font-size: 11px; }.task-content strong { overflow: hidden; color: #324a67; font-size: 13px; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }.task-content em { overflow: hidden; color: #a36a35; font-size: 11px; font-style: normal; text-overflow: ellipsis; white-space: nowrap; }.task-row svg { color: #9dadbc; }
.task-detail-panel { padding-bottom: 22px; }.detail-heading { align-items: center; }.source-button { flex: 0 0 auto; }.priority-note { display: flex; align-items: center; gap: 7px; margin: 18px 22px; padding: 10px 12px; color: #8a5b24; background: #fff7e5; border-radius: 8px; font-size: 12px; font-weight: 700; }.task-detail-panel :deep(.question-text) { margin: 0 22px; color: #263f5d; font-size: 15px; line-height: 1.8; }.question-figures { display: grid; gap: 10px; margin: 16px 22px 0; }.question-figures img { display: block; max-width: min(100%, 680px); max-height: 420px; object-fit: contain; object-position: left top; border: 1px solid #d6e0ea; border-radius: 8px; }.clean-question-image { display: block; width: min(100% - 44px, 680px); max-height: 560px; margin: 0 22px; object-fit: contain; object-position: left top; border: 1px solid #d6e0ea; border-radius: 9px; background: #f7f8f9; }.task-options { display: grid; gap: 7px; margin: 17px 22px; padding: 0; list-style: none; }.task-options li { display: flex; gap: 8px; padding: 8px 10px; color: #465f7b; background: #f7fafc; border-radius: 7px; font-size: 13px; line-height: 1.5; }.task-options b { color: #2765c4; }.attempt-history { margin: 20px 22px 0; color: #8392a2; font-size: 12px; }.result-actions { margin: 15px 22px 0; padding: 16px; background: #f5f8fc; border: 1px solid #e1e9f1; border-radius: 10px; }.result-actions > p { margin: 0 0 11px; color: #35506c; font-size: 13px; font-weight: 800; }.result-actions > div { display: flex; gap: 10px; }.wrong-button,.correct-button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; flex: 1; min-height: 45px; border-radius: 8px; font-size: 13px; font-weight: 800; }.wrong-button { color: #c05445; border: 1px solid #edc2bb; background: #fff; }.correct-button { color: #fff; border: 1px solid #3c9770; background: #42a279; }.result-actions small { display: block; margin-top: 10px; color: #8796a6; font-size: 11px; line-height: 1.55; }.wrong-button:disabled,.correct-button:disabled { cursor: wait; opacity: .7; }.result-actions svg { animation: none; }.result-actions button svg { flex: 0 0 auto; }.result-actions button:disabled svg { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1000px) { .today-workspace { padding: 30px 28px 48px; }.today-layout { grid-template-columns: 1fr; }.task-list-panel { max-height: 380px; overflow: auto; } }
@media (max-width: 720px) { .today-workspace { padding: 26px 17px 42px; }.today-welcome h1 { max-width: 320px; font-size: 26px; line-height: 1.25; }.today-welcome p:not(.eyebrow) { line-height: 1.6; }.today-hero { align-items: flex-start; flex-direction: column; min-height: 218px; margin-top: 24px; padding: 23px; }.hero-copy { align-items: flex-start; }.hero-copy h2 { font-size: 20px; }.hero-copy span { max-width: 260px; line-height: 1.6; }.start-button,.complete-badge { margin-left: 63px; }.today-stats { gap: 10px; }.today-stats article { padding: 14px; }.today-stats strong { font-size: 20px; }.today-layout { gap: 12px; }.panel-title,.detail-heading { padding: 17px; }.task-row { min-height: 68px; padding: 13px; }.task-detail-panel :deep(.question-text) { margin: 0 17px; font-size: 14px; }.priority-note { margin: 15px 17px; }.clean-question-image { width: calc(100% - 34px); margin: 0 17px; }.task-options,.attempt-history { margin-left: 17px; margin-right: 17px; }.result-actions { margin: 15px 17px 0; padding: 14px; }.result-actions > div { flex-direction: column; }.wrong-button,.correct-button { min-height: 46px; }.source-button { min-height: 40px; padding: 8px; font-size: 11px; }.task-content strong { white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }.task-content em { display: none; } }
</style>
