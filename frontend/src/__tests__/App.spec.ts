import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'
import App from '../App.vue'

describe('App', () => {
  it('renders the local data workspace', async () => {
    const wrapper = mount(App)
    expect(wrapper.find('.hero').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('LOCAL DATA TOOLKIT')
    expect(wrapper.text()).not.toContain('在本机完成数据清洗、回归、相关性和空间分析，不上传数据。')
    expect(wrapper.text()).toContain('数据清洗')
    expect(wrapper.text()).toContain('回归分析方法')
    expect(wrapper.text()).toContain('空间分析')
    expect(wrapper.text()).toContain('GWRF + SHAP')
    expect(wrapper.find('input[type="file"]').attributes('accept')).toBe('.csv,.xlsx')

    const tabs = wrapper.findAll('.workspace-tabs button')
    const views = wrapper.findAll('.workspace-view')
    expect(views[0]?.attributes('style')).toContain('display: none')
    expect(views[1]?.attributes('style')).toContain('display: none')

    await tabs[1]?.trigger('click')
    expect(tabs[1]?.classes()).toContain('active')
    expect(views[0]?.attributes('style') ?? '').not.toContain('display: none')
    expect(views[1]?.attributes('style')).toContain('display: none')

    await tabs[2]?.trigger('click')
    expect(tabs[2]?.classes()).toContain('active')
    expect(views[0]?.attributes('style')).toContain('display: none')
    expect(views[1]?.attributes('style') ?? '').not.toContain('display: none')

    await tabs[3]?.trigger('click')
    expect(tabs[3]?.classes()).toContain('active')
    expect(views[2]?.attributes('style') ?? '').not.toContain('display: none')
  })
})
