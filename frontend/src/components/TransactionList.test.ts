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
      min_amount: undefined,
      max_amount: undefined,
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
    await wrapper.get('input[name="filter_min_amount"]').setValue('88.00')
    await wrapper.get('input[name="filter_max_amount"]').setValue('100.00')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mockedListTransactions).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 10,
      transaction_type: 'expense',
      category: '餐饮',
      start_date: '2026-07-01',
      end_date: '2026-07-31',
      min_amount: '88',
      max_amount: '100',
    })

    await wrapper.get('nav button:last-child').trigger('click')
    await flushPromises()
    expect(mockedListTransactions).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 2 }),
    )
  })

  it('blocks an invalid amount range without requesting', async () => {
    const wrapper = mount(TransactionList, { props: { refreshKey: 0 } })
    await flushPromises()

    await wrapper.get('input[name="filter_min_amount"]').setValue('100.00')
    await wrapper.get('input[name="filter_max_amount"]').setValue('50.00')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mockedListTransactions).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[role="alert"]').text()).toBe('最低金额不能大于最高金额')
  })

  it('reset clears amount filters and reloads without them', async () => {
    const wrapper = mount(TransactionList, { props: { refreshKey: 0 } })
    await flushPromises()

    await wrapper.get('input[name="filter_min_amount"]').setValue('10.00')
    await wrapper.get('input[name="filter_max_amount"]').setValue('20.00')
    await wrapper.get('button.secondary-button').trigger('click')
    await flushPromises()

    expect(wrapper.get<HTMLInputElement>('input[name="filter_min_amount"]').element.value).toBe('')
    expect(wrapper.get<HTMLInputElement>('input[name="filter_max_amount"]').element.value).toBe('')
    expect(mockedListTransactions).toHaveBeenLastCalledWith(
      expect.objectContaining({ min_amount: undefined, max_amount: undefined }),
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
    expect(wrapper.emitted('deleted')).toHaveLength(1)
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
