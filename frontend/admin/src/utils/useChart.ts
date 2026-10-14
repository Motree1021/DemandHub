import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onMounted, onUnmounted, ref } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'

// 按需注册，控制打包体积
echarts.use([LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent,
  CanvasRenderer])

/** echarts 容器绑定：返回 el 挂到 div ref，setOption 渲染；自动处理 resize 与销毁。 */
export function useChart() {
  const el = ref<HTMLElement>()
  let chart: echarts.ECharts | undefined

  function setOption(option: EChartsCoreOption) {
    if (!chart && el.value) chart = echarts.init(el.value)
    chart?.setOption(option)
  }

  const onResize = () => chart?.resize()
  onMounted(() => window.addEventListener('resize', onResize))
  onUnmounted(() => {
    window.removeEventListener('resize', onResize)
    chart?.dispose()
    chart = undefined
  })
  return { el, setOption }
}
