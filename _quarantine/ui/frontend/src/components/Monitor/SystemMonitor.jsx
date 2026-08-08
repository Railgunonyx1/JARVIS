import { useRef, useEffect } from 'react'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useTelemetryStore } from '../../stores/telemetryStore'
import GaugeRing from './GaugeRing'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const MAX_POINTS = 60

export default function SystemMonitor() {
  const cpu = useTelemetryStore((s) => s.cpu)
  const ram = useTelemetryStore((s) => s.ram)
  const gpu = useTelemetryStore((s) => s.gpu)
  const disk = useTelemetryStore((s) => s.disk)
  const chartRef = useRef(null)
  const instanceRef = useRef(null)
  const cpuHistRef = useRef([])
  const ramHistRef = useRef([])
  const labelsRef = useRef([])

  useEffect(() => {
    const el = chartRef.current
    if (!el) return
    const instance = echarts.init(el, null, { renderer: 'canvas' })
    instanceRef.current = instance
    const option = {
      grid: { top: 20, right: 8, bottom: 20, left: 36 },
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        show: true,
        axisLine: { lineStyle: { color: 'rgba(0,212,255,0.1)' } },
        axisLabel: { color: '#555', fontSize: 8, show: false },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        min: 0, max: 100,
        splitLine: { lineStyle: { color: 'rgba(0,212,255,0.05)' } },
        axisLabel: { color: '#555', fontSize: 8 },
      },
      series: [
        {
          name: 'CPU',
          type: 'line',
          smooth: true,
          showSymbol: false,
          lineStyle: { color: '#00d4ff', width: 1.5 },
          areaStyle: { color: 'rgba(0,212,255,0.08)' },
          data: [],
        },
        {
          name: 'RAM',
          type: 'line',
          smooth: true,
          showSymbol: false,
          lineStyle: { color: '#7b2ff7', width: 1.5 },
          areaStyle: { color: 'rgba(123,47,247,0.08)' },
          data: [],
        },
      ],
    }
    instance.setOption(option)

    const handleResize = () => instance.resize()
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      instance.dispose()
      instanceRef.current = null
    }
  }, [])

  useEffect(() => {
    const now = Date.now()
    labelsRef.current.push(now)
    cpuHistRef.current.push(cpu)
    ramHistRef.current.push(ram)

    if (labelsRef.current.length > MAX_POINTS) {
      labelsRef.current.shift()
      cpuHistRef.current.shift()
      ramHistRef.current.shift()
    }

    if (instanceRef.current) {
      instanceRef.current.setOption({
        xAxis: { data: labelsRef.current.map(() => '') },
        series: [
          { data: cpuHistRef.current },
          { data: ramHistRef.current },
        ],
      })
    }
  }, [cpu, ram])

  return (
    <div className="system-monitor">
      <div className="panel-title">SYSTEM MONITOR</div>
      <div className="gauge-grid">
        <GaugeRing label="CPU" value={cpu} color="#00d4ff" />
        <GaugeRing label="RAM" value={ram} color="#00d4ff" />
        <GaugeRing label="GPU" value={gpu} color="#ff6b35" accentColor="rgba(255,107,53,0.08)" />
        <GaugeRing label="DISK" value={disk} color="#00d4ff" />
      </div>
      <div ref={chartRef} style={{ width: '100%', height: 100, marginTop: 8 }} />
    </div>
  )
}
