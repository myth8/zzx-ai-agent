<template>
  <div class="ai-avatar-fallback" :class="type">
    <svg v-if="type === 'love'" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 20S4.5 15.7 4.5 9.4A4.4 4.4 0 0 1 12 6.3a4.4 4.4 0 0 1 7.5 3.1C19.5 15.7 12 20 12 20Z"/>
    </svg>
    <span v-else>Z</span>
  </div>
</template>

<script setup>
defineProps({
  type: {
    type: String,
    default: 'default'
  }
})
</script>

<style scoped>
.ai-avatar-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #07101b;
  font: 800 15px 'Manrope', sans-serif;
  border-radius: 12px;
}

.ai-avatar-fallback svg { width: 17px; }

.love {
  background: linear-gradient(135deg, #fda4af, #fb7185);
}

.default, .super {
  background: linear-gradient(135deg, #a5f3fc, #67e8f9 55%, #a78bfa);
}
</style>
