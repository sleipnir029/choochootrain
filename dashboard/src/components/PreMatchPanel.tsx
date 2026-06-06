// Pre-match panel (P6.T5): team win prob, per-map probs, top-factor breakdown.
// Works for both contract modes — an ingested match_id, or an upcoming team1/team2.
import { useQuery } from '@tanstack/react-query'
import { getPreMatch, type Factor, type PreMatch } from '../lib/api'
import { WinProbBar } from './WinProbBar'

interface Props {
  matchId?: number
  team1Id?: number
  team2Id?: number
}

function FactorBar({ f }: { f: Factor }) {
  return (
    <div className="factor">
      <span>{f.factor}</span>
      <div className={`fbar favors-${f.favors}`}>
        <div style={{ width: `${Math.round(f.weight * 100)}%` }} />
      </div>
      <span className="fav">favors {f.favors === 'team1' ? 't1' : 't2'}</span>
    </div>
  )
}

export function PreMatchPanel({ matchId, team1Id, team2Id }: Props) {
  const enabled = matchId != null || (team1Id != null && team2Id != null)
  const q = useQuery<PreMatch>({
    queryKey: ['preMatch', matchId, team1Id, team2Id],
    queryFn: () => getPreMatch({ matchId, team1Id, team2Id }),
    enabled,
  })

  if (!enabled) return <div className="panel muted">Pick a match to see a pre-match prediction.</div>
  if (q.isLoading) return <div className="panel loading">Loading pre-match prediction…</div>
  if (q.isError) return <div className="panel error">Could not load prediction: {(q.error as Error).message}</div>

  const d = q.data!
  const t1 = d.team1.name ?? 'Team 1'
  const t2 = d.team2.name ?? 'Team 2'
  const series = d.series_win_prob

  return (
    <div className="panel">
      <div className="teams-row">
        <span className="team-name t1">{t1}</span>
        <span className="muted">
          {d.mode === 'upcoming' ? 'upcoming · ' : ''}{d.series_format}
        </span>
        <span className="team-name t2">{t2}</span>
      </div>

      <div className="sub">Series win probability</div>
      <WinProbBar p1={series.team1} label1={t1} label2={t2} />
      <div className="hdi">
        Map win prob {(d.team1_win_prob * 100).toFixed(0)}%
        {d.team1_win_prob_hdi
          ? ` (94% HDI ${(d.team1_win_prob_hdi[0] * 100).toFixed(0)}–${(d.team1_win_prob_hdi[1] * 100).toFixed(0)}%)`
          : ''}
      </div>

      {d.map_predictions.length > 0 && (
        <div className="maps-grid">
          <div className="sub" style={{ marginTop: 8 }}>Per-map ({t1})</div>
          {d.map_predictions.map((m) => (
            <div className="map-row" key={m.map_name}>
              <span className="mname">{m.map_name}</span>
              <div className="mini-bar"><div style={{ width: `${Math.round(m.team1_win_prob * 100)}%` }} /></div>
              <span className="mpct">{(m.team1_win_prob * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}

      <div className="factors">
        <div className="sub">Top factors</div>
        {d.top_factors.map((f) => <FactorBar key={f.factor} f={f} />)}
        <div className="hdi" style={{ marginTop: 8 }}>
          Attribution from model coefficients × features (interpretive, not exact).
        </div>
      </div>
    </div>
  )
}
