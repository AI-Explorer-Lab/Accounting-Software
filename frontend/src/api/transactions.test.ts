import { afterEach, describe, expect, it, vi } from 'vitest'

import { listTransactions } from './transactions'

describe('listTransactions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('serializes amount filters with existing filters and pagination', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: null, message: '', request_id: null }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await listTransactions({
      page: 2,
      page_size: 10,
      transaction_type: 'expense',
      category: '餐饮',
      start_date: '2026-07-01',
      end_date: '2026-07-31',
      min_amount: '10.00',
      max_amount: '20.00',
    })

    const url = new URL(fetchMock.mock.calls[0][0], 'http://test')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      page: '2',
      page_size: '10',
      transaction_type: 'expense',
      category: '餐饮',
      start_date: '2026-07-01',
      end_date: '2026-07-31',
      min_amount: '10.00',
      max_amount: '20.00',
    })
  })
})
