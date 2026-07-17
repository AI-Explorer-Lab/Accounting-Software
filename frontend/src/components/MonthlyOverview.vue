<template>
  <section class="monthly-overview" aria-labelledby="monthly-overview-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">MONTHLY OVERVIEW</p>
        <h2 id="monthly-overview-title">月度概览</h2>
      </div>
      <label class="month-picker">
        月份
        <input v-model="selectedMonth" type="month" aria-label="选择统计月份" @change="loadStatistics" />
      </label>
    </div>

    <p v-if="loading" role="status">正在加载月度汇总…</p>
    <p v-else-if="error" class="form-error" role="alert">{{ error }}</p>
    <template v-else-if="statistics">
      <dl class="summary-grid">
        <div><dt>收入</dt><dd>¥{{ money(statistics.income_total) }}</dd></div>
        <div><dt>支出</dt><dd>¥{{ money(statistics.expense_total) }}</dd></div>
        <div><dt>结余</dt><dd>¥{{ money(statistics.balance) }}</dd></div>
        <div><dt>交易笔数</dt><dd>{{ statistics.transaction_count }}</dd></div>
      </dl>

      <p v-if="statistics.transaction_count === 0" class="list-state">
        本月暂无交易数据
      </p>
      <div v-else class="category-analysis" aria-labelledby="category-analysis-title">
        <h3 id="category-analysis-title">支出分类</h3>
        <p v-if="statistics.expense_by_category.length === 0" class="category-empty">
          本月没有支出记录
        </p>
        <ul v-else class="category-list">
          <li v-for="item in statistics.expense_by_category" :key="item.category">
            <div class="category-label">
              <span>{{ item.category }}</span>
              <span>¥{{ money(item.amount) }} · {{ percentage(item.percentage) }}%</span>
            </div>
            <div
              class="category-track"
              role="progressbar"
              :aria-label="`${item.category}支出占比`"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="Number(item.percentage)"
              :aria-valuetext="`${percentage(item.percentage)}%`"
            >
              <span class="category-bar" :style="{ width: `${item.percentage}%` }"></span>
            </div>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { getMonthlyStatistics, type MonthlyTransactionStatisticsData } from '../api/transactions'

const props = defineProps<{ refreshKey: number }>()
const now = new Date()
const selectedMonth = ref(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
const statistics = ref<MonthlyTransactionStatisticsData | null>(null)
const loading = ref(false)
const error = ref('')

function money(value: string) {
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function percentage(value: string) {
  return Number(value).toFixed(2)
}

async function loadStatistics() {
  loading.value = true
  error.value = ''
  try {
    const response = await getMonthlyStatistics(selectedMonth.value)
    if (!response.data) {
      throw new Error('月度汇总为空')
    }
    statistics.value = response.data
  } catch {
    statistics.value = null
    error.value = '月度汇总加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(loadStatistics)
watch(() => props.refreshKey, loadStatistics)
</script>
