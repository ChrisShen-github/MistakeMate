<script setup lang="ts">
import { computed } from 'vue'
import { ListPlus, Plus, Trash2 } from '@lucide/vue'
import type { QuestionPart } from '../types/questions'

const props = defineProps<{ part: QuestionPart; child?: boolean }>()
const emit = defineEmits<{ remove: []; addChild: [] }>()

const isGroup = computed(() => props.part.part_type === '题组说明')
const hasAnswerContent = computed(() => props.part.answers.some((answer) => answer.trim()) || Boolean(props.part.solution.trim()))
const availableTypes = computed(() => props.child
  ? ['填空题', '计算题', '证明题', '简答题', '选择题', '判断题', '其他']
  : ['题组说明', '填空题', '计算题', '证明题', '简答题', '选择题', '判断题', '其他'])

function ensureAnswerShape() {
  if (isGroup.value) {
    props.part.answers = []
    props.part.answer_lines = 0
    return
  }
  if (!props.part.answers.length) props.part.answers.push('')
  if (props.part.answer_lines < 1) props.part.answer_lines = props.part.part_type === '填空题' ? 1 : 4
  if (props.part.part_type !== '填空题' && props.part.answers.length > 1) props.part.answers.splice(1)
}

function addAnswer() {
  if (props.part.answers.length < 12) props.part.answers.push('')
}

function removeAnswer(index: number) {
  if (props.part.answers.length > 1) props.part.answers.splice(index, 1)
}

function addKeyPoint() {
  if (props.part.key_points.length < 12) props.part.key_points.push('')
}
</script>

<template>
  <article class="part-card" :class="{ child, group: isGroup }">
    <header class="part-header">
      <label class="label-field">
        <span>编号</span>
        <input v-model="part.label" maxlength="32" :aria-label="`${part.label || '小问'}编号`" />
      </label>
      <label class="type-field">
        <span>类型</span>
        <select v-model="part.part_type" @change="ensureAnswerShape">
          <option v-for="type in availableTypes" :key="type">{{ type }}</option>
        </select>
      </label>
      <div class="part-actions">
        <button v-if="isGroup && !child" class="add-child" type="button" @click="emit('addChild')"><ListPlus :size="16" />添加子问</button>
        <button class="remove-part" type="button" :aria-label="`移除小问 ${part.label}`" @click="emit('remove')"><Trash2 :size="17" />移除</button>
      </div>
    </header>

    <label class="prompt-field">
      <span>{{ isGroup ? '共同条件' : '小问题干' }}</span>
      <textarea v-model="part.prompt" rows="3" :placeholder="isGroup ? '填写后续子问共同使用的条件' : '填写这一小问的内容'"></textarea>
    </label>

    <p v-if="isGroup" class="group-hint">分组只保存共同条件，答案填写在下面的子问中。</p>

    <template v-else>
      <details class="answer-details" :open="hasAnswerContent">
        <summary>答案与解析 <span>可选，不填写也能确认题目</span><small v-if="hasAnswerContent">已填写</small></summary>
        <div class="answer-content">
          <section v-if="part.part_type === '填空题'" class="answers-section" :aria-label="`${part.label}填空答案`">
            <div class="section-title"><div><strong>填空答案</strong><span>有答案时每个空单独填写</span></div><button type="button" @click="addAnswer"><Plus :size="16" />增加一空</button></div>
            <div class="answer-list">
              <div v-for="(_, answerIndex) in part.answers" :key="answerIndex" class="answer-row">
                <label :for="`part-${part.id}-answer-${answerIndex}`">第 {{ answerIndex + 1 }} 空</label>
                <input :id="`part-${part.id}-answer-${answerIndex}`" v-model="part.answers[answerIndex]" placeholder="可暂不填写" />
                <button type="button" :disabled="part.answers.length <= 1" :aria-label="`移除第 ${answerIndex + 1} 空`" @click="removeAnswer(answerIndex)"><Trash2 :size="16" /></button>
              </div>
            </div>
          </section>

          <label v-else class="answer-field">
            <span>最终答案 <small>可选</small></span>
            <input v-model="part.answers[0]" placeholder="有答案时再填写" />
          </label>

          <label class="solution-field">
            <span>标准解答 / 过程 <small>可选，用于答案版和以后按步骤批改</small></span>
            <textarea v-model="part.solution" rows="4" placeholder="有完整解答时再补充"></textarea>
          </label>
        </div>
      </details>

      <details class="part-details">
        <summary>关键得分点与复练设置</summary>
        <div class="details-content">
          <section class="key-points">
            <div class="section-title"><div><strong>关键得分点</strong><span>以后 AI 可按这些步骤判断哪里出错</span></div><button type="button" @click="addKeyPoint"><Plus :size="16" />添加</button></div>
            <div v-if="part.key_points.length" class="key-point-list">
              <div v-for="(_, pointIndex) in part.key_points" :key="pointIndex" class="key-point-row"><label :for="`part-${part.id}-point-${pointIndex}`">{{ pointIndex + 1 }}</label><input :id="`part-${part.id}-point-${pointIndex}`" v-model="part.key_points[pointIndex]" placeholder="例如：正确列出两数之差" /><button type="button" :aria-label="`移除关键点 ${pointIndex + 1}`" @click="part.key_points.splice(pointIndex, 1)"><Trash2 :size="16" /></button></div>
            </div>
          </section>
          <div class="part-settings">
            <label>答题空间<select v-model.number="part.answer_lines"><option v-for="lines in [1, 2, 4, 6, 8, 10, 12]" :key="lines" :value="lines">{{ lines }} 行</option></select></label>
            <label>难度<select v-model.number="part.difficulty"><option v-for="star in 5" :key="star" :value="star">{{ star }} 星</option></select></label>
            <label>错因<select v-model="part.error_type"><option value="">暂不填写</option><option>计算错误</option><option>审题不清</option><option>概念不牢</option><option>方法不会</option><option>粗心遗漏</option><option>其他</option></select></label>
            <label class="knowledge-field">知识点<input v-model="part.knowledge_points" maxlength="1000" placeholder="多个知识点用逗号分隔" /></label>
          </div>
        </div>
      </details>
    </template>
  </article>
</template>

<style scoped>
.part-card { padding: 18px; border: 1px solid #d8e4ef; border-left: 4px solid #4f83ce; border-radius: 10px; background: #fff; }
.part-card.child { margin-left: 28px; border-left-color: #f59e0b; background: #fffdfa; }
.part-card.group { background: #f7faff; }
.part-header { display: grid; grid-template-columns: 110px minmax(140px, 190px) 1fr; gap: 12px; align-items: end; }
.part-header label,.prompt-field,.answer-field,.solution-field,.part-settings label { display: grid; gap: 6px; color: #405a75; font-size: 12px; font-weight: 700; }
input,textarea,select { box-sizing: border-box; width: 100%; color: #2d4662; border: 1px solid #c9d8e6; border-radius: 8px; background: #fff; font: inherit; font-size: 14px; line-height: 1.55; }
input,select { min-height: 44px; padding: 0 11px; }
textarea { padding: 10px 11px; resize: vertical; }
input:focus,textarea:focus,select:focus,button:focus-visible,summary:focus-visible { border-color: #2563eb; outline: 3px solid rgba(37,99,235,.17); outline-offset: 1px; }
.part-actions { display: flex; justify-content: flex-end; gap: 8px; }
.part-actions button,.section-title button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 5px; padding: 8px 10px; border-radius: 8px; background: #fff; font-size: 12px; font-weight: 700; cursor: pointer; }
.add-child,.section-title button { color: #285fae; border: 1px solid #b9d1ef; }
.remove-part { color: #a84b3d; border: 1px solid #e5bbb4; }
.prompt-field,.part-details,.answer-details { margin-top: 16px; }
.answer-field,.solution-field,.answers-section { margin-top: 0; }
.solution-field { margin-top: 14px; }
.answer-field span,.solution-field span { display: flex; align-items: baseline; gap: 7px; }
small,.section-title span { color: #7b8fa3; font-size: 11px; font-weight: 500; }
.group-hint { margin: 10px 0 0; color: #667f99; font-size: 12px; }
.answer-details { overflow: hidden; border: 1px solid #d8e5f2; border-radius: 9px; background: #f8fbff; }
.answer-details summary { display: flex; min-height: 44px; box-sizing: border-box; align-items: center; gap: 7px; padding: 12px 14px; color: #355875; font-size: 13px; font-weight: 700; cursor: pointer; }
.answer-details summary span { color: #71879c; font-size: 11px; font-weight: 500; }
.answer-details summary small { margin-left: auto; padding: 3px 6px; color: #247358; border-radius: 5px; background: #e8f7f0; }
.answer-content { padding: 2px 14px 14px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-title > div { display: grid; gap: 3px; color: #3a5570; font-size: 13px; }
.answer-list,.key-point-list { display: grid; gap: 9px; margin-top: 10px; }
.answer-row,.key-point-row { display: grid; grid-template-columns: 68px minmax(0,1fr) 44px; gap: 8px; align-items: center; color: #657b91; font-size: 12px; font-weight: 700; }
.answer-list button,.key-point-list button { display: grid; width: 44px; height: 44px; place-items: center; color: #9f4b40; border: 0; border-radius: 8px; background: #fff3f0; cursor: pointer; }
.answer-list button:disabled { cursor: not-allowed; opacity: .35; }
.part-details { overflow: hidden; border: 1px solid #e0e8f0; border-radius: 9px; background: #fbfdff; }
.part-details summary { min-height: 44px; padding: 13px 14px; color: #46627f; font-size: 12px; font-weight: 700; cursor: pointer; }
.details-content { padding: 0 14px 14px; }
.key-point-row { grid-template-columns: 30px minmax(0,1fr) 44px; }
.key-point-row > label { display: grid; width: 26px; height: 26px; place-items: center; color: #2f69bb; border-radius: 50%; background: #eaf3ff; }
.part-settings { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; margin-top: 15px; }
.knowledge-field { grid-column: 1 / -1; }
@media (max-width: 760px) {
  .part-card { padding: 15px; }
  .part-card.child { margin-left: 12px; }
  .part-header { grid-template-columns: 82px minmax(0,1fr); }
  .part-actions { grid-column: 1 / -1; justify-content: flex-start; }
  .part-settings { grid-template-columns: 1fr; }
  .knowledge-field { grid-column: auto; }
  .answer-row { grid-template-columns: 58px minmax(0,1fr) 44px; }
}
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto; } }
</style>
