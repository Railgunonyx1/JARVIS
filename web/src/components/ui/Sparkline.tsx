interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  stroke?: string
  strokeWidth?: number
  className?: string
}

/** SVG polyline sparkline, scaled to the series min/max (prototype `.graph`). */
export function Sparkline({
  data,
  width = 300,
  height = 42,
  stroke = '#18cfe8',
  strokeWidth = 1.5,
  className,
}: SparklineProps) {
  let points = ''
  if (data.length > 0) {
    const max = Math.max(...data)
    const min = Math.min(...data)
    const range = max - min || 1
    const step = Math.max(1, data.length - 1)
    points = data
      .map((value, i) => {
        const x = (i / step) * width
        const y = height - ((value - min) / range) * (height - 2) - 1
        return `${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')
  }
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      aria-hidden="true"
    >
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth={strokeWidth}
        points={points}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
