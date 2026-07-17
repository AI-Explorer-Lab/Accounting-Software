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
          MonthlyOverview: true,
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

  it('refreshes the monthly overview after creating or deleting a transaction', async () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          HealthCard: true,
          MonthlyOverview: {
            props: ['refreshKey'],
            template: '<div data-test="overview">{{ refreshKey }}</div>',
          },
          TransactionForm: {
            emits: ['created'],
            template: '<button data-test="create" @click="$emit(\'created\')">create</button>',
          },
          TransactionList: {
            props: ['refreshKey'],
            emits: ['deleted'],
            template: '<button data-test="delete" @click="$emit(\'deleted\')">{{ refreshKey }}</button>',
          },
        },
      },
    })

    expect(wrapper.get('[data-test="overview"]').text()).toBe('0')
    await wrapper.get('[data-test="create"]').trigger('click')
    expect(wrapper.get('[data-test="overview"]').text()).toBe('1')
    await wrapper.get('[data-test="delete"]').trigger('click')
    expect(wrapper.get('[data-test="overview"]').text()).toBe('2')
  })
})
