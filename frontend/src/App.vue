<template>
  <main class="shell">
    <button
      class="theme-toggle"
      type="button"
      :aria-pressed="isDarkMode"
      :aria-label="isDarkMode ? '切换到浅色模式' : '切换到黑暗模式'"
      @click="toggleDarkMode"
    >
      <span aria-hidden="true">{{ isDarkMode ? '☀' : '☾' }}</span>
      {{ isDarkMode ? '浅色模式' : '黑暗模式' }}
    </button>

    <header class="hero">
      <p class="eyebrow">ACCOUNTING SOFTWARE</p>
      <h1>清楚记录每一笔收支</h1>
      <p class="intro">
        在一个简洁的表单里记录收入与支出，让日常账目保持清晰。
      </p>
    </header>

    <TransactionForm @created="refreshTransactions" />
    <TransactionList :refresh-key="transactionRefreshKey" />
    <HealthCard />

    <section class="architecture" aria-labelledby="architecture-title">
      <div>
        <p class="eyebrow">ARCHITECTURE</p>
        <h2 id="architecture-title">当前组成</h2>
      </div>
      <ul>
        <li><strong>Frontend</strong><span>Vue 3 · Vite · TypeScript</span></li>
        <li><strong>Backend</strong><span>FastAPI · SQLAlchemy Async</span></li>
        <li><strong>Database</strong><span>PostgreSQL · Docker</span></li>
      </ul>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import HealthCard from './components/HealthCard.vue'
import TransactionForm from './components/TransactionForm.vue'
import TransactionList from './components/TransactionList.vue'

const transactionRefreshKey = ref(0)
const isDarkMode = ref(document.documentElement.dataset.theme === 'dark')

function refreshTransactions() {
  transactionRefreshKey.value += 1
}

function toggleDarkMode() {
  isDarkMode.value = !isDarkMode.value
  document.documentElement.dataset.theme = isDarkMode.value ? 'dark' : 'light'
}
</script>
