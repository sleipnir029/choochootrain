// Narrative block (P6 revision) — the "why/what" lead on every view.
import type { Insight as InsightT } from '../lib/api'

export function Insight({ insight }: { insight: InsightT | null | undefined }) {
  if (!insight) return null
  return (
    <div className={`insight tone-${insight.tone}`}>
      <div className="insight-headline">{insight.headline}</div>
      {insight.points.length > 0 && (
        <ul className="insight-points">
          {insight.points.map((p, i) => <li key={i}>{p}</li>)}
        </ul>
      )}
    </div>
  )
}
