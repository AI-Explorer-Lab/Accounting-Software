import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import MonthlyOverview from './MonthlyOverview.vue'
import { getMonthlyStatistics } from '../api/transactions'

vi.mock('../api/transactions', () => ({ getMonthlyStatistics: vi.fn() }))

const mockedStatistics = vi.mocked(getMonthlyStatistics)

describe('MonthlyOverview', () => {
  beforeEach(() => mockedStatistics.mockReset())

  it('queries the current month and shows a loading state', async () => {
    const now = new Date()
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    mockedStatistics.mockImplementation(() => new Promise((resolve) => {
      setTimeout(() => resolve({
        success: true,
        data: {
          month: currentMonth, income_total: '1.00', expense_total: '0.00', balance: '1.00',
          transaction_count: 1, expense_by_category: [],
        },
        message: 'ok', request_id: null,
      }), 10)
    }))

    const wrapper = mount(MonthlyOverview, { props: { refreshKey: 0 } })
    await nextTick()

    expect(mockedStatistics).toHaveBeenCalledWith(currentMonth)
    expect(wrapper.get('[role="status"]').text()).toBe('正在加载月度汇总…')
    await new Promise((resolve) => setTimeout(resolve, 20))
  })

  it('shows sorted category bars and refreshes all data when month changes', async () => {
    mockedStatistics
      .mockResolvedValueOnce({
        success: true,
        data: {
          month: '2026-07', income_total: '1000.00', expense_total: '300.00',
          balance: '700.00', transaction_count: 4,
          expense_by_category: [
            { category: '餐饮', amount: '200.00', percentage: '66.67' },
            { category: '交通', amount: '100.00', percentage: '33.33' },
          ],
        },
        message: 'ok', request_id: null,
      })
      .mockResolvedValueOnce({
        success: true,
        data: {
          month: '2026-06', income_total: '500.00', expense_total: '50.00',
          balance: '450.00', transaction_count: 2,
          expense_by_category: [{ category: '交通', amount: '50.00', percentage: '100.00' }],
        },
        message: 'ok', request_id: null,
      })

    const wrapper = mount(MonthlyOverview, { props: { refreshKey: 0 } })
    await flushPromises()

    expect(wrapper.findAll('.category-list li').map((item) => item.text())).toEqual([
      '餐饮¥200.00 · 66.67%', '交通¥100.00 · 33.33%',
    ])
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('66.67')

    await wrapper.get('input[type="month"]').setValue('2026-06')
    await flushPromises()

    expect(mockedStatistics).toHaveBeenLastCalledWith('2026-06')
    expect(wrapper.text()).toContain('¥500.00')
    expect(wrapper.text()).toContain('交通¥50.00 · 100.00%')
    expect(wrapper.text()).not.toContain('餐饮')
  })

  it('shows a clear empty state when there are no transactions', async () => {
    mockedStatistics.mockResolvedValue({
      success: true,
      data: {
        month: '2026-07', income_total: '0', expense_total: '0', balance: '0',
        transaction_count: 0, expense_by_category: [],
      },
      message: 'ok', request_id: null,
    })
    const wrapper = mount(MonthlyOverview, { props: { refreshKey: 0 } })
    await flushPromises()

    expect(wrapper.text()).toContain('本月暂无交易数据')
    expect(wrapper.find('.summary-grid').exists()).toBe(true)
    expect(wrapper.text()).toContain('交易笔数0')
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
  })

  it('shows an error state and reloads the selected month when requested', async () => {
    mockedStatistics.mockRejectedValueOnce(new Error('network error')).mockResolvedValueOnce({
      success: true,
      data: {
        month: '2026-05', income_total: '10.00', expense_total: '0.00', balance: '10.00',
        transaction_count: 1, expense_by_category: [],
      },
      message: 'ok', request_id: null,
    })
    const wrapper = mount(MonthlyOverview, { props: { refreshKey: 0 } })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('月度汇总加载失败，请稍后重试')

    await wrapper.get('input[type="month"]').setValue('2026-05')
    await flushPromises()
    await wrapper.setProps({ refreshKey: 1 })
    await flushPromises()

    expect(mockedStatistics).toHaveBeenLastCalledWith('2026-05')
    expect(mockedStatistics).toHaveBeenCalledTimes(3)
  })
})
