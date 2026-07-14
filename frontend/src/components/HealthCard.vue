<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchHealth, type HealthData } from '../api/health'

const health = ref<HealthData | null>(null)
const error = ref('')
const loading = ref(true)

async function loadHealth() {
  loading.value = true
  error.value = ''

  try {
    const response = await fetchHealth()
    health.value = response.data
  } catch (caught) {
    health.value = null
    error.value = caught instanceof Error ? caught.message : '无法连接后端服务'
  } finally {
    loading.value = false
  }
}

onMounted(loadHealth)
</script>

<template>
  <section class="health-card" aria-live="polite">
    <div>
      <p class="eyebrow">系统状态</p>
      <h2>后端连接</h2>
    </div>

    <p v-if="loading" class="status pending">检查中…</p>
    <p v-else-if="health" class="status online">
      <span class="status-dot" aria-hidden="true"></span>
      正常 · {{ health.environment }} · v{{ health.version }}
    </p>
    <div v-else class="error-block">
      <p class="status offline">未连接 · {{ error }}</p>
      <button type="button" @click="loadHealth">重新检查</button>
    </div>
  </section>
</template>
