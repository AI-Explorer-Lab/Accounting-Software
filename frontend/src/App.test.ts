import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import App from './App.vue'

describe('App theme toggle', () => {
  afterEach(() => {
    delete document.documentElement.dataset.theme
  })

  it('switches to dark mode and back to light mode', async () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          HealthCard: true,
          TransactionForm: true,
          TransactionList: true,
        },
      },
    })
    const toggle = wrapper.get<HTMLButtonElement>('.theme-toggle')

    expect(toggle.text()).toContain('黑暗模式')
    expect(toggle.attributes('aria-pressed')).toBe('false')

    await toggle.trigger('click')

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(toggle.text()).toContain('浅色模式')
    expect(toggle.attributes('aria-pressed')).toBe('true')

    await toggle.trigger('click')

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(toggle.text()).toContain('黑暗模式')
    expect(toggle.attributes('aria-pressed')).toBe('false')
  })
})
