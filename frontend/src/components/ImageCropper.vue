<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, Maximize2, X } from '@lucide/vue'

export type CropRegion = { x: number; y: number; width: number; height: number }

const props = defineProps<{ file: File; initialRegion: CropRegion | null }>()
const emit = defineEmits<{ cancel: []; confirm: [region: CropRegion | null] }>()
const canvas = ref<HTMLCanvasElement | null>(null)
const frame = ref<HTMLDivElement | null>(null)
const dialog = ref<HTMLElement | null>(null)
const isReady = ref(false)
const loadError = ref('')
const region = ref<CropRegion>(props.initialRegion ? { ...props.initialRegion } : { x: 0.05, y: 0.05, width: 0.9, height: 0.9 })

let image: HTMLImageElement | null = null
let objectUrl = ''
let displayWidth = 0
let displayHeight = 0
let activePointer: number | null = null
let dragMode = ''
let dragOrigin = { x: 0, y: 0 }
let dragStart: CropRegion = { ...region.value }
let previousBodyOverflow = ''

const cropSummary = computed(() => {
  const { x, y, width, height } = region.value
  return `左侧 ${Math.round(x * 100)}%，顶部 ${Math.round(y * 100)}%，宽 ${Math.round(width * 100)}%，高 ${Math.round(height * 100)}%`
})

function clamp(value: number, minimum: number, maximum: number) { return Math.min(maximum, Math.max(minimum, value)) }
function isWholeImage(value: CropRegion) { return value.x < 0.002 && value.y < 0.002 && value.width > 0.998 && value.height > 0.998 }

function draw() {
  const target = canvas.value
  if (!target || !image || !isReady.value || !displayWidth || !displayHeight) return
  const ratio = window.devicePixelRatio || 1
  const context = target.getContext('2d')
  if (!context) return
  context.setTransform(ratio, 0, 0, ratio, 0, 0)
  context.clearRect(0, 0, displayWidth, displayHeight)
  context.drawImage(image, 0, 0, displayWidth, displayHeight)

  const box = {
    x: region.value.x * displayWidth,
    y: region.value.y * displayHeight,
    width: region.value.width * displayWidth,
    height: region.value.height * displayHeight,
  }
  context.fillStyle = 'rgba(14, 28, 45, .62)'
  context.fillRect(0, 0, displayWidth, box.y)
  context.fillRect(0, box.y, box.x, box.height)
  context.fillRect(box.x + box.width, box.y, displayWidth - box.x - box.width, box.height)
  context.fillRect(0, box.y + box.height, displayWidth, displayHeight - box.y - box.height)

  context.save()
  context.strokeStyle = 'rgba(255, 255, 255, .58)'
  context.lineWidth = 1
  context.setLineDash([5, 5])
  for (const fraction of [1 / 3, 2 / 3]) {
    context.beginPath()
    context.moveTo(box.x + box.width * fraction, box.y)
    context.lineTo(box.x + box.width * fraction, box.y + box.height)
    context.stroke()
    context.beginPath()
    context.moveTo(box.x, box.y + box.height * fraction)
    context.lineTo(box.x + box.width, box.y + box.height * fraction)
    context.stroke()
  }
  context.restore()

  context.strokeStyle = '#f97316'
  context.lineWidth = 3
  context.strokeRect(box.x + 1.5, box.y + 1.5, Math.max(0, box.width - 3), Math.max(0, box.height - 3))
  const handleSize = 12
  context.fillStyle = '#ffffff'
  context.strokeStyle = '#f97316'
  context.lineWidth = 2
  for (const [handleX, handleY] of [
    [box.x, box.y], [box.x + box.width / 2, box.y], [box.x + box.width, box.y],
    [box.x, box.y + box.height / 2], [box.x + box.width, box.y + box.height / 2],
    [box.x, box.y + box.height], [box.x + box.width / 2, box.y + box.height], [box.x + box.width, box.y + box.height],
  ]) {
    context.beginPath()
    context.rect(handleX - handleSize / 2, handleY - handleSize / 2, handleSize, handleSize)
    context.fill()
    context.stroke()
  }
}

function resizeCanvas() {
  if (!frame.value || !canvas.value || !image) return
  const availableWidth = Math.max(260, frame.value.clientWidth - 24)
  const availableHeight = Math.max(260, window.innerHeight - (window.innerWidth <= 680 ? 260 : 310))
  const scale = Math.min(availableWidth / image.naturalWidth, availableHeight / image.naturalHeight, 1)
  displayWidth = Math.max(1, Math.round(image.naturalWidth * scale))
  displayHeight = Math.max(1, Math.round(image.naturalHeight * scale))
  const ratio = window.devicePixelRatio || 1
  canvas.value.style.width = `${displayWidth}px`
  canvas.value.style.height = `${displayHeight}px`
  canvas.value.width = Math.round(displayWidth * ratio)
  canvas.value.height = Math.round(displayHeight * ratio)
  draw()
}

function pointFromEvent(event: PointerEvent) {
  const bounds = canvas.value!.getBoundingClientRect()
  return {
    x: clamp((event.clientX - bounds.left) / bounds.width, 0, 1),
    y: clamp((event.clientY - bounds.top) / bounds.height, 0, 1),
  }
}

function hitTest(point: { x: number; y: number }) {
  const value = region.value
  const thresholdX = Math.min(0.06, 18 / Math.max(displayWidth, 1))
  const thresholdY = Math.min(0.06, 18 / Math.max(displayHeight, 1))
  const left = Math.abs(point.x - value.x) <= thresholdX
  const right = Math.abs(point.x - (value.x + value.width)) <= thresholdX
  const top = Math.abs(point.y - value.y) <= thresholdY
  const bottom = Math.abs(point.y - (value.y + value.height)) <= thresholdY
  const withinX = point.x >= value.x - thresholdX && point.x <= value.x + value.width + thresholdX
  const withinY = point.y >= value.y - thresholdY && point.y <= value.y + value.height + thresholdY
  if (left && top) return 'nw'
  if (right && top) return 'ne'
  if (left && bottom) return 'sw'
  if (right && bottom) return 'se'
  if (top && withinX) return 'n'
  if (bottom && withinX) return 's'
  if (left && withinY) return 'w'
  if (right && withinY) return 'e'
  if (point.x >= value.x && point.x <= value.x + value.width && point.y >= value.y && point.y <= value.y + value.height) return 'move'
  return 'new'
}

function cursorForMode(mode: string) {
  return ({ nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize', n: 'ns-resize', s: 'ns-resize', w: 'ew-resize', e: 'ew-resize', move: 'move', new: 'crosshair' } as Record<string, string>)[mode] ?? 'crosshair'
}

function onPointerDown(event: PointerEvent) {
  if (!canvas.value || !isReady.value) return
  const point = pointFromEvent(event)
  activePointer = event.pointerId
  dragMode = hitTest(point)
  dragOrigin = point
  dragStart = { ...region.value }
  if (dragMode === 'new') region.value = { x: point.x, y: point.y, width: 0.03, height: 0.03 }
  canvas.value.setPointerCapture(event.pointerId)
  canvas.value.style.cursor = cursorForMode(dragMode)
  draw()
}

function onPointerMove(event: PointerEvent) {
  if (!canvas.value || !isReady.value) return
  const point = pointFromEvent(event)
  if (activePointer !== event.pointerId) {
    canvas.value.style.cursor = cursorForMode(hitTest(point))
    return
  }
  const minimum = 0.03
  const deltaX = point.x - dragOrigin.x
  const deltaY = point.y - dragOrigin.y
  if (dragMode === 'new') {
    const x = Math.min(dragOrigin.x, point.x)
    const y = Math.min(dragOrigin.y, point.y)
    region.value = { x, y, width: Math.max(minimum, Math.abs(point.x - dragOrigin.x)), height: Math.max(minimum, Math.abs(point.y - dragOrigin.y)) }
  } else if (dragMode === 'move') {
    region.value = {
      ...dragStart,
      x: clamp(dragStart.x + deltaX, 0, 1 - dragStart.width),
      y: clamp(dragStart.y + deltaY, 0, 1 - dragStart.height),
    }
  } else {
    let left = dragStart.x
    let top = dragStart.y
    let right = dragStart.x + dragStart.width
    let bottom = dragStart.y + dragStart.height
    if (dragMode.includes('w')) left = clamp(dragStart.x + deltaX, 0, right - minimum)
    if (dragMode.includes('e')) right = clamp(right + deltaX, left + minimum, 1)
    if (dragMode.includes('n')) top = clamp(dragStart.y + deltaY, 0, bottom - minimum)
    if (dragMode.includes('s')) bottom = clamp(bottom + deltaY, top + minimum, 1)
    region.value = { x: left, y: top, width: right - left, height: bottom - top }
  }
  region.value.width = Math.min(region.value.width, 1 - region.value.x)
  region.value.height = Math.min(region.value.height, 1 - region.value.y)
  draw()
}

function onPointerUp(event: PointerEvent) {
  if (activePointer !== event.pointerId || !canvas.value) return
  activePointer = null
  dragMode = ''
  canvas.value.releasePointerCapture(event.pointerId)
  draw()
}

function onCanvasKeydown(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  const step = event.ctrlKey ? 0.02 : 0.005
  const value = { ...region.value }
  if (event.shiftKey) {
    if (event.key === 'ArrowLeft') value.width = Math.max(0.03, value.width - step)
    if (event.key === 'ArrowRight') value.width = Math.min(1 - value.x, value.width + step)
    if (event.key === 'ArrowUp') value.height = Math.max(0.03, value.height - step)
    if (event.key === 'ArrowDown') value.height = Math.min(1 - value.y, value.height + step)
  } else {
    if (event.key === 'ArrowLeft') value.x = Math.max(0, value.x - step)
    if (event.key === 'ArrowRight') value.x = Math.min(1 - value.width, value.x + step)
    if (event.key === 'ArrowUp') value.y = Math.max(0, value.y - step)
    if (event.key === 'ArrowDown') value.y = Math.min(1 - value.height, value.y + step)
  }
  region.value = value
  draw()
}

function useWholeImage() { region.value = { x: 0, y: 0, width: 1, height: 1 }; draw(); canvas.value?.focus() }
function confirmCrop() { emit('confirm', isWholeImage(region.value) ? null : { ...region.value }) }
function onWindowKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { emit('cancel'); return }
  if (event.key !== 'Tab' || !dialog.value) return
  const focusable = Array.from(dialog.value.querySelectorAll<HTMLElement>('button:not(:disabled), canvas[tabindex="0"]'))
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}

onMounted(() => {
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  objectUrl = URL.createObjectURL(props.file)
  image = new Image()
  image.onload = async () => { isReady.value = true; await nextTick(); resizeCanvas(); canvas.value?.focus() }
  image.onerror = () => { loadError.value = '无法预览这张图片，请改用 JPG、PNG 或 WebP。' }
  image.src = objectUrl
  window.addEventListener('resize', resizeCanvas)
  window.addEventListener('keydown', onWindowKeydown)
})

onBeforeUnmount(() => {
  document.body.style.overflow = previousBodyOverflow
  window.removeEventListener('resize', resizeCanvas)
  window.removeEventListener('keydown', onWindowKeydown)
  if (objectUrl) URL.revokeObjectURL(objectUrl)
})
</script>

<template>
  <Teleport to="body">
    <div class="crop-overlay" @click.self="emit('cancel')">
      <section ref="dialog" class="crop-dialog" role="dialog" aria-modal="true" aria-labelledby="crop-title" aria-describedby="crop-help">
        <header class="crop-header"><div><p>识别范围</p><h2 id="crop-title">截取题目区域</h2></div><button type="button" aria-label="关闭裁剪" @click="emit('cancel')"><X :size="21" /></button></header>
        <p id="crop-help" class="crop-help">拖动橙色框或八个控制点，只保留需要 OCR 的题目。键盘可用方向键移动，Shift + 方向键调整大小。</p>
        <div ref="frame" class="crop-frame">
          <canvas v-show="isReady" ref="canvas" class="crop-canvas" tabindex="0" role="application" :aria-label="`图片裁剪区域，${cropSummary}`" @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp" @keydown="onCanvasKeydown"></canvas>
          <p v-if="!isReady && !loadError" class="crop-loading">正在准备图片…</p>
          <p v-if="loadError" class="crop-error" role="alert">{{ loadError }}</p>
        </div>
        <div class="crop-meta"><strong>{{ props.file.name }}</strong><span aria-live="polite">{{ cropSummary }}</span></div>
        <footer class="crop-actions"><button class="whole-button" type="button" :disabled="!isReady" @click="useWholeImage"><Maximize2 :size="17" />使用整张图</button><div><button class="cancel-button" type="button" @click="emit('cancel')">取消</button><button class="confirm-button" type="button" :disabled="!isReady" @click="confirmCrop"><Check :size="17" />确认范围</button></div></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.crop-overlay { position: fixed; z-index: 1000; inset: 0; display: grid; place-items: center; padding: 24px; background: rgba(15,35,57,.58); }.crop-dialog { display: flex; flex-direction: column; width: min(960px,100%); max-height: calc(100dvh - 48px); padding: 22px; overflow: hidden; border-radius: 16px; background: #fff; box-shadow: 0 20px 45px rgba(15,35,57,.22); }.crop-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }.crop-header p { margin: 0 0 4px; color: #71879e; font-size: 12px; font-weight: 700; }.crop-header h2 { margin: 0; color: #203954; font-size: 21px; }.crop-header button { display: grid; width: 44px; height: 44px; flex: 0 0 auto; place-items: center; color: #60768e; border: 0; border-radius: 9px; background: #f1f5f9; cursor: pointer; }.crop-help { margin: 9px 52px 15px 0; color: #60758c; font-size: 13px; line-height: 1.55; }.crop-frame { display: grid; min-height: 260px; flex: 1; place-items: center; overflow: hidden; padding: 12px; border-radius: 12px; background: #172534; }.crop-canvas { display: block; max-width: 100%; max-height: 100%; border-radius: 4px; outline: 0; touch-action: none; user-select: none; }.crop-canvas:focus-visible { box-shadow: 0 0 0 4px rgba(96,165,250,.75); }.crop-loading,.crop-error { color: #dce8f3; font-size: 14px; }.crop-error { color: #fecaca; }.crop-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 11px; color: #71849a; font-size: 11px; }.crop-meta strong { overflow: hidden; color: #405a75; text-overflow: ellipsis; white-space: nowrap; }.crop-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 17px; }.crop-actions > div { display: flex; gap: 9px; }.crop-actions button { display: inline-flex; min-height: 44px; align-items: center; justify-content: center; gap: 6px; padding: 9px 14px; border-radius: 8px; font-size: 13px; font-weight: 700; cursor: pointer; transition: border-color .18s ease, background .18s ease, opacity .18s ease; }.crop-actions button:focus-visible,.crop-header button:focus-visible { outline: 3px solid rgba(37,99,235,.28); outline-offset: 2px; }.whole-button,.cancel-button { color: #315f9b; border: 1px solid #bed0e5; background: #fff; }.whole-button:hover,.cancel-button:hover { background: #f3f7fc; }.confirm-button { min-width: 126px; color: #fff; border: 1px solid #f97316; background: #f97316; }.confirm-button:hover { background: #dc5f0b; }.crop-actions button:disabled { cursor: not-allowed; opacity: .45; }@media (max-width: 680px) { .crop-overlay { align-items: end; padding: 0; }.crop-dialog { width: 100%; max-height: 100dvh; padding: 16px; border-radius: 16px 16px 0 0; }.crop-help { margin-right: 0; font-size: 12px; }.crop-frame { min-height: 250px; padding: 8px; }.crop-meta { align-items: flex-start; flex-direction: column; gap: 4px; }.crop-actions { align-items: stretch; flex-direction: column-reverse; }.crop-actions > div { display: grid; grid-template-columns: 1fr 1.35fr; }.whole-button { width: 100%; } }@media (prefers-reduced-motion: reduce) { .crop-actions button { transition: none; } }
</style>
