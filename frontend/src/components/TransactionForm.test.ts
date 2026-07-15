import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createTransaction } from '../api/transactions'
import TransactionForm from './TransactionForm.vue'

vi.mock('../api/transactions', () => ({
  createTransaction: vi.fn(),
}))

const mockedCreateTransaction = vi.mocked(createTransaction)

describe('TransactionForm', () => {
  beforeEach(() => {
    mockedCreateTransaction.mockReset()
  })

  it('disables submit when amount is empty or not positive', async () => {
    const wrapper = mount(TransactionForm)
    const category = wrapper.get<HTMLSelectElement>('select[name="category"]')
    const amount = wrapper.get<HTMLInputElement>('input[name="amount"]')
    const submit = wrapper.get<HTMLButtonElement>('button[type="submit"]')

    await category.setValue('餐饮')
    expect(submit.element.disabled).toBe(true)

    await amount.setValue('0')
    expect(submit.element.disabled).toBe(true)

    await amount.setValue('-1')
    expect(submit.element.disabled).toBe(true)

    await amount.setValue('12.50')
    expect(submit.element.disabled).toBe(false)
  })

  it('uses a category dropdown with at least five selectable categories', () => {
    const wrapper = mount(TransactionForm)
    const category = wrapper.get<HTMLSelectElement>('select[name="category"]')
    const options = category.findAll('option:not([disabled])')

    expect(wrapper.find('input[name="category"]').exists()).toBe(false)
    expect(options.length).toBeGreaterThanOrEqual(5)
    expect(options.map((option) => option.attributes('value'))).toContain('餐饮')
  })

  it.each(['expense', 'income'] as const)(
    'submits an %s transaction and shows success',
    async (type) => {
      mockedCreateTransaction.mockResolvedValue({
        success: true,
        data: {
          id: 1,
          amount: '125.50',
          category: '餐饮',
          description: '团队午餐',
          transaction_date: '2026-07-14',
          transaction_type: type,
        },
        message: 'transaction created',
        request_id: 'request-id',
      })
      const wrapper = mount(TransactionForm)

      await wrapper.get('select[name="transaction_type"]').setValue(type)
      await wrapper.get('input[name="amount"]').setValue('125.50')
      await wrapper.get('select[name="category"]').setValue('餐饮')
      await wrapper.get('textarea[name="description"]').setValue('团队午餐')
      await wrapper.get('input[name="transaction_date"]').setValue('2026-07-14')
      await wrapper.get('form').trigger('submit')
      await flushPromises()

      expect(mockedCreateTransaction).toHaveBeenCalledWith({
        amount: '125.5',
        category: '餐饮',
        description: '团队午餐',
        transaction_date: '2026-07-14',
        transaction_type: type,
      })
      expect(wrapper.get('[role="status"]').text()).toBe('交易已成功保存')
      expect(wrapper.emitted('created')).toHaveLength(1)
    },
  )
})
