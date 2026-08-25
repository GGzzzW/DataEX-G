import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'
import App from '../App.vue'

describe('App', () => {
  it('renders the local data workspace', () => {
    const wrapper = mount(App)
    expect(wrapper.text()).toContain('数据质量工作台')
    expect(wrapper.text()).toContain('本地处理')
    expect(wrapper.find('input[type="file"]').attributes('accept')).toBe('.csv,.xlsx')
  })
})
