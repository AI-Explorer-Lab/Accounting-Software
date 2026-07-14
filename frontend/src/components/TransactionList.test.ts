import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/http'
import { deleteTransaction, listTransactions } from '../api/transactions'
import TransactionList from './TransactionList.vue'

vi.mock('../api/transactions', () => ({
  deleteTransaction: vi.fn(),
  listTransactions: vi.fn(),
}))

const mockedDeleteTransaction = vi.mocked(deleteTransaction)
const mockedListTransactions = vi.mocked(listTransactions)

const pageResponse = (total = 1) => ({
  success: true,
  data: {
    items: [
      {
        id: 7,
        amount: '88.00',
        category: '餐饮',
        description: '团队晚餐',
        transaction_date: '2026-07-14',
        transaction_type: 'expense' as const,
      },
    ],
    total,
    page: 1,
    page_size: 10,
  },
  message: 'transactions retrieved',
  request_id: null,
})

describe('TransactionList', () => {
  beforeEach(() => {
    mockedListTransactions.mockReset()
    mockedDeleteTransaction.mockReset()
    mockedListTransactions.mockResolvedValue(pageResponse())
  })

  it('loads and displays transactions', async () => {
    const wrapper = mount(TransactionList, { props: { refreshKey: 0 } })
    await flushPromises()

    expect(mockedListTransactions).toHaveBeenCalledWith({
      page: 1,
      page_size: 10,
      transaction_type: undefined,
      category: undefined,
      start_date: undefined,
      end_date: undefined,
    })
    expect(wrapper.text()).toContain('餐饮')
    expect(wrapper.text()).toContain('¥88.00')
    expect(wrapper.text()).toContain('团队晚餐')
  })

  it('reloads when a transaction is created', async () => {
    const wrapper = mount(TransactionList, { props: { refreshKey: 0 } })
    await flushPromises()

    await wrapper.setProps({ refreshKey: 1 })
    await flushPromises()

    expect(mockedListTransactions).toHaveBeenCalledTimes(2)
  })

  it('queries with filters and supports pagination', async () => {
    mockedListTransactions.mockResolvedValue(pageResponse(11))
    const wrapper = mount(TransactionList, { props: { refreshKey: 0 } })
    await flushPromises()

    await wrapper.get('select[name="filter_transaction_type"]').setValue('expense')
    await wrapper.get('input[name="filter_category"]').setValue('餐饮')
    await wrapper.get('input[name="filter_start_date"]').setValue('2026-07-01')
    await wrapper.get('input[name="filter_end_date"]').setValue('2026-07-31')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mockedListTransactions).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 10,
      transaction_type: 'expense',
      category: '餐饮',
      start_date: '2026-07-01',
      end_date: '2026-07-31',
    })

    await wrapper.get('nav button:last-child').trigger('click')
    await flushPromises()
    expect(mockedListTransactions).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 }),
    )
  })

  it('deletes a transaction and reloads the list', async () => {
    mockedDeleteTransaction.mockResolvedValue({
      success: true,
      data: { id: 7 },
      message: 'transaction deleted',
      request_id: null,
    })
    const wrapper = mount(TransactionList, { props: { refreshKey: 0 } })
    await flushPromises()

    await wrapper.get('button[aria-label="删除 餐饮 交易"]').trigger('click')
    await flushPromises()

    expect(mockedDeleteTransaction).toHaveBeenCalledWith(7)
    expect(mockedListTransactions).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[role="status"]').text()).toBe('交易已删除')
  })

  it('shows a friendly message and reloads when deletion returns 404', async () => {
    mockedDeleteTransaction.mockRejectedValue(new ApiError('transaction not found', 404))
    const wrapper = mount(TransactionList, { props: { refreshKey: 0 } })
    await flushPromises()

    await wrapper.get('button[aria-label="删除 餐饮 交易"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('记录不存在')
    expect(mockedListTransactions).toHaveBeenCalledTimes(2)
  })
})
