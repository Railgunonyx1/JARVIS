const CIRC = 2 * Math.PI * 42

export default function GaugeRing({ label, value, color = '#00d4ff', accentColor = 'rgba(0,212,255,0.08)' }) {
  const offset = CIRC - (CIRC * Math.min(value, 100) / 100)

  return (
    <div className="gauge-ring-wrapper">
      <svg viewBox="0 0 100 100" className="gauge-ring-svg">
        <circle cx="50" cy="50" r="42" fill="none" stroke={accentColor} strokeWidth="6" />
        <circle
          cx="50" cy="50" r="42" fill="none" stroke={color}
          strokeWidth="6" strokeLinecap="round"
          strokeDasharray={CIRC} strokeDashoffset={offset}
          className="gauge-ring-fill"
          transform="rotate(-90 50 50)"
        />
        <text x="50" y="48" textAnchor="middle" fill={color} fontSize="14" fontWeight="600" fontFamily="JetBrains Mono, monospace">
          {Math.round(value)}%
        </text>
        <text x="50" y="62" textAnchor="middle" fill="#666" fontSize="7" fontFamily="JetBrains Mono, monospace">
          {label}
        </text>
      </svg>
    </div>
  )
}
