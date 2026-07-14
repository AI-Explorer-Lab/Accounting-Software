import { post } from './http'

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

export function createTransaction(transaction: TransactionInput) {
  return post<TransactionData, TransactionInput>('/api/transactions', transaction)
}
