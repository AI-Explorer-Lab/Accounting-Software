<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  createTransaction,
  type TransactionType,
} from '../api/transactions'

const initialDate = () => new Date().toISOString().slice(0, 10)

const transactionType = ref<TransactionType>('expense')
const amount = ref<string | number>('')
const category = ref('')
const description = ref('')
const transactionDate = ref(initialDate())
const submitting = ref(false)
const successMessage = ref('')
const errorMessage = ref('')
const normalizedAmount = computed(() => String(amount.value).trim())

const amountIsValid = computed(() => {
  if (!normalizedAmount.value) {
    return false
  }

  const numericAmount = Number(normalizedAmount.value)
  return Number.isFinite(numericAmount) && numericAmount > 0
})

const formIsValid = computed(
  () =>
    amountIsValid.value &&
    Boolean(category.value.trim()) &&
    Boolean(transactionDate.value),
)

async function submitTransaction() {
  if (!formIsValid.value || submitting.value) {
    return
  }

  submitting.value = true
  successMessage.value = ''
  errorMessage.value = ''

  try {
    await createTransaction({
      amount: normalizedAmount.value,
      category: category.value.trim(),
      description: description.value.trim() || null,
      transaction_date: transactionDate.value,
      transaction_type: transactionType.value,
    })
    amount.value = ''
    category.value = ''
    description.value = ''
    transactionDate.value = initialDate()
    successMessage.value = '交易已成功保存'
  } catch (caught) {
    errorMessage.value = caught instanceof Error ? caught.message : '交易保存失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="transaction-card" aria-labelledby="transaction-form-title">
    <div class="section-heading">
      <div>
        <p class="eyebrow">NEW TRANSACTION</p>
        <h2 id="transaction-form-title">新增交易</h2>
      </div>
      <p>记录一笔收入或支出</p>
    </div>

    <form class="transaction-form" @submit.prevent="submitTransaction">
      <label>
        <span>交易类型</span>
        <select v-model="transactionType" name="transaction_type">
          <option value="expense">支出</option>
          <option value="income">收入</option>
        </select>
      </label>

      <label>
        <span>金额</span>
        <input
          v-model="amount"
          name="amount"
          type="number"
          min="0.01"
          step="0.01"
          inputmode="decimal"
          placeholder="0.00"
          required
        />
      </label>

      <label>
        <span>分类</span>
        <input
          v-model="category"
          name="category"
          type="text"
          maxlength="100"
          placeholder="例如：餐饮、工资"
          required
        />
      </label>

      <label>
        <span>交易日期</span>
        <input v-model="transactionDate" name="transaction_date" type="date" required />
      </label>

      <label class="full-width">
        <span>描述 <small>选填</small></span>
        <textarea
          v-model="description"
          name="description"
          maxlength="500"
          rows="3"
          placeholder="补充这笔交易的说明"
        ></textarea>
      </label>

      <div class="form-actions full-width">
        <div class="form-feedback" aria-live="polite">
          <p v-if="successMessage" class="success-message" role="status">
            {{ successMessage }}
          </p>
          <p v-if="errorMessage" class="form-error" role="alert">
            {{ errorMessage }}
          </p>
        </div>
        <button type="submit" :disabled="!formIsValid || submitting">
          {{ submitting ? '保存中…' : '保存交易' }}
        </button>
      </div>
    </form>
  </section>
</template>
