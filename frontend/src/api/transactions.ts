import { del, get, post } from './http'

export type TransactionType = 'income' | 'expense'

export interface TransactionInput {
  amount: string
  category: string
  description: string | null
  transaction_date: string
  transaction_type: TransactionType
}

export interface TransactionData extends TransactionInput {
  id: number
}

export interface TransactionQuery {
  page?: number
  page_size?: number
  transaction_type?: TransactionType
  category?: string
  start_date?: string
  end_date?: string
}

export interface TransactionPageData {
  items: TransactionData[]
  total: number
  page: number
  page_size: number
}

export interface TransactionDeleteData {
  id: number
}

export function createTransaction(transaction: TransactionInput) {
  return post<TransactionData, TransactionInput>('/api/transactions', transaction)
}

export function listTransactions(query: TransactionQuery = {}) {
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      params.set(key, String(value))
    }
  })
  const queryString = params.toString()
  return get<TransactionPageData>(`/api/transactions${queryString ? `?${queryString}` : ''}`)
}

export function deleteTransaction(transactionId: number) {
  return del<TransactionDeleteData>(`/api/transactions/${transactionId}`)
}
