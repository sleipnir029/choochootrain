// Two-segment win-probability bar (P6.T5). p1 = P(team1), 0..1.
export function WinProbBar({ p1, label1, label2 }: { p1: number; label1?: string; label2?: string }) {
  const pct1 = Math.round(p1 * 100)
  const pct2 = 100 - pct1
  return (
    <div className="probbar">
      <div className="seg1 seg-label" style={{ width: `${pct1}%` }}>
        {pct1 >= 12 ? `${label1 ?? 'Team 1'} ${pct1}%` : ''}
      </div>
      <div className="seg2 seg-label" style={{ width: `${pct2}%` }}>
        {pct2 >= 12 ? `${label2 ?? 'Team 2'} ${pct2}%` : ''}
      </div>
    </div>
  )
}
