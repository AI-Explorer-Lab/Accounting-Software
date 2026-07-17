<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { ApiError } from '../api/http'
import {
  deleteTransaction,
  listTransactions,
  type TransactionData,
  type TransactionType,
} from '../api/transactions'

const props = defineProps<{
  refreshKey: number
}>()

const emit = defineEmits<{
  deleted: []
}>()

const pageSize = 10
const transactions = ref<TransactionData[]>([])
const total = ref(0)
const page = ref(1)
const transactionType = ref<TransactionType | ''>('')
const category = ref('')
const startDate = ref('')
const endDate = ref('')
const loading = ref(false)
const deletingId = ref<number | null>(null)
const errorMessage = ref('')
const feedbackMessage = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

async function loadTransactions() {
  loading.value = true
  errorMessage.value = ''

  try {
    const response = await listTransactions({
      page: page.value,
      page_size: pageSize,
      transaction_type: transactionType.value || undefined,
      category: category.value.trim() || undefined,
      start_date: startDate.value || undefined,
      end_date: endDate.value || undefined,
    })
    if (!response.data) {
      throw new Error('查询结果为空')
    }
    transactions.value = response.data.items
    total.value = response.data.total
  } catch (caught) {
    errorMessage.value = caught instanceof Error ? caught.message : '交易查询失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function applyFilters() {
  feedbackMessage.value = ''
  if (startDate.value && endDate.value && startDate.value > endDate.value) {
    errorMessage.value = '开始日期不能晚于结束日期'
    return
  }
  page.value = 1
  await loadTransactions()
}

async function resetFilters() {
  transactionType.value = ''
  category.value = ''
  startDate.value = ''
  endDate.value = ''
  page.value = 1
  feedbackMessage.value = ''
  await loadTransactions()
}

async function changePage(nextPage: number) {
  if (nextPage < 1 || nextPage > totalPages.value || loading.value) {
    return
  }
  page.value = nextPage
  await loadTransactions()
}

async function removeTransaction(transactionId: number) {
  if (deletingId.value !== null) {
    return
  }

  deletingId.value = transactionId
  errorMessage.value = ''
  feedbackMessage.value = ''
  try {
    await deleteTransaction(transactionId)
    feedbackMessage.value = '交易已删除'
    if (transactions.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await loadTransactions()
    emit('deleted')
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 404) {
      await loadTransactions()
      errorMessage.value = '记录不存在'
    } else {
      errorMessage.value = caught instanceof Error ? caught.message : '删除失败，请稍后重试'
    }
  } finally {
    deletingId.value = null
  }
}

onMounted(loadTransactions)
watch(() => props.refreshKey, loadTransactions)
</script>

<template>
  <section class="transaction-list-card" aria-labelledby="transaction-list-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">TRANSACTIONS</p>
        <h2 id="transaction-list-title">交易记录</h2>
      </div>
      <p>共 {{ total }} 条记录</p>
    </div>

    <form class="transaction-filters" aria-label="交易筛选" @submit.prevent="applyFilters">
      <label>
        <span>交易类型</span>
        <select v-model="transactionType" name="filter_transaction_type">
          <option value="">全部</option>
          <option value="expense">支出</option>
          <option value="income">收入</option>
        </select>
      </label>
      <label>
        <span>分类</span>
        <input v-model="category" name="filter_category" maxlength="100" placeholder="输入分类" />
      </label>
      <label>
        <span>开始日期</span>
        <input v-model="startDate" name="filter_start_date" type="date" />
      </label>
      <label>
        <span>结束日期</span>
        <input v-model="endDate" name="filter_end_date" type="date" />
      </label>
      <div class="filter-actions">
        <button type="submit" :disabled="loading">查询</button>
        <button class="secondary-button" type="button" :disabled="loading" @click="resetFilters">
          重置
        </button>
      </div>
    </form>

    <div class="list-feedback" aria-live="polite">
      <p v-if="feedbackMessage" class="success-message" role="status">{{ feedbackMessage }}</p>
      <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
    </div>

    <p v-if="loading" class="list-state">正在查询交易记录…</p>
    <p v-else-if="transactions.length === 0" class="list-state">暂无符合条件的交易记录</p>

    <div v-else class="transaction-table-wrap">
      <table class="transaction-table">
        <thead>
          <tr>
            <th>类型</th>
            <th>金额</th>
            <th>分类</th>
            <th>日期</th>
            <th>描述</th>
            <th><span class="visually-hidden">操作</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="transaction in transactions" :key="transaction.id">
            <td>
              <span :class="['transaction-type', transaction.transaction_type]">
                {{ transaction.transaction_type === 'income' ? '收入' : '支出' }}
              </span>
            </td>
            <td class="amount">¥{{ transaction.amount }}</td>
            <td>{{ transaction.category }}</td>
            <td>{{ transaction.transaction_date }}</td>
            <td class="description">{{ transaction.description || '—' }}</td>
            <td class="delete-cell">
              <button
                class="delete-button"
                type="button"
                :disabled="deletingId !== null"
                :aria-label="`删除 ${transaction.category} 交易`"
                @click="removeTransaction(transaction.id)"
              >
                {{ deletingId === transaction.id ? '删除中…' : '删除' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <nav v-if="total > pageSize" class="pagination" aria-label="交易记录分页">
      <button class="secondary-button" type="button" :disabled="page === 1 || loading" @click="changePage(page - 1)">
        上一页
      </button>
      <span>第 {{ page }} / {{ totalPages }} 页</span>
      <button class="secondary-button" type="button" :disabled="page === totalPages || loading" @click="changePage(page + 1)">
        下一页
      </button>
    </nav>
  </section>
</template>
