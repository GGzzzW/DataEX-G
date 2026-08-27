import { afterEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import GwrfWorkspace from '../components/GwrfWorkspace.vue'

const previewResponse = {
  filename: 'gwrf.csv',
  row_count: 12,
  column_count: 5,
  columns: ['lon', 'lat', 'x1', 'x2', 'target'],
  preview: [],
  quality: {
    missing_cell_count: 0,
    whitespace_cell_count: 0,
    line_break_cell_count: 0,
    duplicate_row_count: 0,
    duplicate_row_numbers: [],
    columns: ['lon', 'lat', 'x1', 'x2', 'target'].map((name) => ({
      name,
      pandas_dtype: 'float64',
      missing_count: 0,
      missing_ratio: 0,
      detected_types: [{ type: 'number', count: 12, examples: ['1'] }],
      mixed_types: false,
      whitespace_count: 0,
      whitespace_row_numbers: [],
      line_break_count: 0,
      line_break_row_numbers: [],
    })),
  },
}

function chooseFile(wrapper: ReturnType<typeof mount>, file: File) {
  const input = wrapper.find<HTMLInputElement>('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
  return input.trigger('change')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('GwrfWorkspace', () => {
  it('shows the selected file and variable controls after preview succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(previewResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    const wrapper = mount(GwrfWorkspace)

    await chooseFile(wrapper, new File(['lon,lat\n116,40'], 'my-gwrf.csv', { type: 'text/csv' }))
    await flushPromises()

    expect(wrapper.text()).toContain('my-gwrf.csv')
    expect(wrapper.text()).toContain('12 行')
    expect(wrapper.text()).toContain('自变量（框选一个或多个）')
    const selects = wrapper.findAll<HTMLSelectElement>('select')
    expect(selects[0]?.element.value).toBe('lon')
    expect(selects[1]?.element.value).toBe('lat')
  })

  it('keeps the selected filename visible when preview fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: '文件无法解析。' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    const wrapper = mount(GwrfWorkspace)

    await chooseFile(wrapper, new File(['bad'], 'broken.csv', { type: 'text/csv' }))
    await flushPromises()

    expect(wrapper.text()).toContain('broken.csv')
    expect(wrapper.text()).toContain('文件无法解析。')
  })

  it('runs parameter optimization as a separate step and fills the best parameters', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(previewResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            observations: 12,
            dropped_rows: 0,
            dependent_column: 'target',
            independent_columns: ['x1', 'x2'],
            best_parameters: {
              n_estimators: 200,
              max_depth: 10,
              min_samples_split: 5,
            },
            search_results: [
              {
                n_estimators: 200,
                max_depth: 10,
                min_samples_split: 5,
                cv_rmse: 0.25,
                rank: 1,
              },
            ],
            cv_folds: 3,
            scoring: 'negative_mean_squared_error',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(GwrfWorkspace)
    await chooseFile(wrapper, new File(['data'], 'model.csv', { type: 'text/csv' }))
    await flushPromises()

    const selects = wrapper.findAll<HTMLSelectElement>('select')
    await selects[2]?.setValue('target')
    for (const label of wrapper.findAll('.gwrf-independent-selector label')) {
      if (['x1', 'x2'].some((name) => label.text().includes(name))) {
        await label.find<HTMLInputElement>('input').setValue(true)
      }
    }
    await wrapper.find<HTMLButtonElement>('.parameter-action').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('参数寻优完成，可以继续运行最终模型')
    expect(wrapper.text()).toContain('决策树 200')
    expect(wrapper.find<HTMLButtonElement>('.primary-action').element.disabled).toBe(false)

    const shapSwitches = wrapper.findAll<HTMLInputElement>('.shap-switches input')
    await shapSwitches[0]?.setValue(true)
    await shapSwitches[1]?.setValue(true)
    expect(wrapper.find('.shap-interaction-selector').classes()).toContain('active')
    const interactionVariables = wrapper.findAll<HTMLInputElement>(
      '.shap-interaction-selector input',
    )
    expect(interactionVariables).toHaveLength(2)
    await interactionVariables[0]?.setValue(true)
    expect(wrapper.find<HTMLButtonElement>('.primary-action').element.disabled).toBe(true)
    await interactionVariables[1]?.setValue(true)
    expect(wrapper.find<HTMLButtonElement>('.primary-action').element.disabled).toBe(false)
  })
})
