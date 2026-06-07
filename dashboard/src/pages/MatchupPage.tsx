// Head-to-head matchup — the analyst pre-match prep view. Overlays both teams'
// prediction, map edge (where to steer the veto), veto tendencies, and the marquee
// cross-roster player duels.
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { getMatchup, type Matchup } from '../lib/api'
import { Insight } from '../components/Insight'
import { WinProbBar } from '../components/WinProbBar'
import { TeamLogo, MapThumb, Comp } from '../components/Visual'
import { Dumbbell, Spectrum, Ban } from '../components/Viz'

const pc = (x: number | null) => (x == null ? '—' : `${Math.round(x * 100)}%`)

export function MatchupPage() {
  const { t1, t2 } = useParams()
  const a = Number(t1), b = Number(t2)
  const q = useQuery<Matchup>({
    queryKey: ['matchup', a, b], queryFn: () => getMatchup(a, b),
    enabled: Number.isFinite(a) && Number.isFinite(b),
  })
  if (q.isLoading) return <div className="panel loading">Building matchup report…</div>
  if (q.isError) return <div className="panel error">{(q.error as Error).message}</div>
  const m = q.data!
  const n1 = m.team1.name ?? 'Team 1'
  const n2 = m.team2.name ?? 'Team 2'
  const p1 = m.prediction.team1_win_prob
  const favT1 = p1 >= 0.5
  const favName = favT1 ? n1 : n2
  const favPct = Math.round((favT1 ? p1 : 1 - p1) * 100)
  const sFav = Math.round((favT1 ? m.prediction.series_win_prob.team1 : m.prediction.series_win_prob.team2) * 100)
  const edges = m.map_edge
    .filter((e) => e.t1_win_rate_adj != null && e.t2_win_rate_adj != null)
    .map((e) => ({ map: e.map_name, edge: (e.t1_win_rate_adj as number) - (e.t2_win_rate_adj as number) }))
  const best = edges.length ? edges.reduce((a, b) => (b.edge > a.edge ? b : a)) : null   // best for team1
  const worst = edges.length ? edges.reduce((a, b) => (b.edge < a.edge ? b : a)) : null  // worst for team1

  return (
    <>
      <div className="panel">
        <div className="teams-row">
          <Link to={`/team/${m.team1.id}`} className="team-name t1"><TeamLogo url={m.team1.logo} name={n1} size={26} />{n1}</Link>
          <span className="muted">matchup prep</span>
          <Link to={`/team/${m.team2.id}`} className="team-name t2">{n2}<TeamLogo url={m.team2.logo} name={n2} size={26} /></Link>
        </div>
        <div className="ban-grid" style={{ margin: '12px 0' }}>
          <Ban label="Model pick — map" value={`${favName} ${favPct}%`} sub={m.prediction.confidence ? `${m.prediction.confidence} confidence` : 'map win probability'} />
          <Ban label="Series (Bo3)" value={`${sFav}%`} sub={`${favName} to take the series`} />
          {best && <Ban label={`${n1}: pick`} value={best.map} sub={best.edge > 0 ? `+${Math.round(best.edge * 100)} edge` : 'least-bad map'} />}
          {worst && <Ban label={`${n1}: avoid`} value={worst.map} sub={worst.edge < 0 ? `${n2} +${Math.round(-worst.edge * 100)}` : 'still favoured'} />}
        </div>
        <Insight insight={m.prematch_insight} />
        <div style={{ marginTop: 10 }}>
          <div className="sub">
            Model prediction
            {m.prediction.confidence && <span className={`conf-chip conf-${m.prediction.confidence}`}>{m.prediction.confidence}</span>}
          </div>
          <WinProbBar p1={m.prediction.team1_win_prob} label1={n1} label2={n2} />
        </div>
      </div>

      {m.dumbbell.length > 0 && (
        <div className="panel">
          <div className="sub">Head-to-head — {n1} vs {n2} across key form metrics</div>
          <Dumbbell aName={n1} bName={n2}
            rows={m.dumbbell.map((d) => ({ label: d.label, a: d.t1, b: d.t2, aText: pc(d.t1), bText: pc(d.t2) }))} />
        </div>
      )}

      <div className="panel">
        <div className="sub">Map confidence — green favours {n1}, red favours {n2} (sample-adjusted)</div>
        <Spectrum rows={m.map_edge
          .filter((e) => e.t1_win_rate_adj != null && e.t2_win_rate_adj != null)
          .map((e) => {
            const edge = (e.t1_win_rate_adj as number) - (e.t2_win_rate_adj as number)
            const note = Math.abs(edge) < 0.06 ? 'even' : edge > 0 ? `${n1} +${Math.round(edge * 100)}` : `${n2} +${Math.round(-edge * 100)}`
            return { label: <span className="map-cell"><MapThumb map={e.map_name} h={22} />{e.map_name}</span>, edge: edge * 2.4, note }
          })} />
      </div>

      <div className="panel">
        <div className="sub">Map edge — steer the veto toward {n1}'s strong, {n2}'s weak maps</div>
        <table className="stints">
          <thead><tr><th>Map</th><th>{n1} win%</th><th>{n2} win%</th><th>Edge</th></tr></thead>
          <tbody>
            {m.map_edge.map((e) => {
              // Edge from sample-size-adjusted rates so a thin map pool doesn't show a fake +50.
              const a1 = e.t1_win_rate_adj ?? 0.5, a2 = e.t2_win_rate_adj ?? 0.5
              const diff = a1 - a2
              const edge = Math.abs(diff) < 0.12 ? '' : diff > 0 ? `${n1} +${Math.round(diff * 100)}` : `${n2} +${Math.round(-diff * 100)}`
              return (
                <tr key={e.map_name}>
                  <td><span className="map-cell"><MapThumb map={e.map_name} h={28} />{e.map_name}</span></td>
                  <td className={a1 >= 0.6 ? 'over' : a1 <= 0.4 ? 'under' : ''}>{pc(e.t1_win_rate)} <span className="muted">({e.t1_n})</span></td>
                  <td className={a2 >= 0.6 ? 'over' : a2 <= 0.4 ? 'under' : ''}>{pc(e.t2_win_rate)} <span className="muted">({e.t2_n})</span></td>
                  <td className={diff > 0.12 ? 'over' : diff < -0.12 ? 'under' : 'muted'}>{edge || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {(m.comps1.length > 0 || m.comps2.length > 0) && (
        <div className="panel">
          <div className="sub">Likely comps — each team's most-run lineup per map</div>
          <div className="veto-cols">
            {[{ n: n1, comps: m.comps1 }, { n: n2, comps: m.comps2 }].map(({ n, comps }) => (
              <div key={n}>
                <div className="team-name" style={{ fontSize: 15, marginBottom: 6 }}>{n}</div>
                {comps.slice(0, 6).map((c) => (
                  <div key={c.map_name} style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '5px 0' }}>
                    <MapThumb map={c.map_name} h={24} />
                    <span className="muted" style={{ minWidth: 70, fontSize: 13 }}>{c.map_name}</span>
                    <Comp comp={c.comp} size={24} />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="panel">
        <div className="sub">Key player duels — head-to-head history between the rosters</div>
        <div className="recent-list">
          {m.key_duels.length === 0 && <div className="muted">No prior cross-roster duels on record.</div>}
          {m.key_duels.map((d, i) => (
            <div key={i} className="recent-row" style={{ gridTemplateColumns: '1fr 70px 1fr 70px' }}>
              <span className="t1" style={{ textAlign: 'right' }}>{d.t1_player}</span>
              <span style={{ textAlign: 'center', fontVariantNumeric: 'tabular-nums' }}>{d.kills}–{d.deaths}</span>
              <span className="t2">{d.t2_player}</span>
              <span className={d.net > 0 ? 'over' : 'under'} style={{ textAlign: 'right' }}>{d.net > 0 ? '+' : ''}{d.net}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="sub">Veto tendencies</div>
        <div className="veto-cols">
          {[{ n: n1, v: m.veto1 }, { n: n2, v: m.veto2 }].map(({ n, v }) => (
            <div key={n}>
              <div className="team-name" style={{ fontSize: 15, marginBottom: 6 }}>{n}</div>
              <div className="muted" style={{ fontSize: 12 }}>Bans</div>
              <div style={{ marginBottom: 8 }}>{v.bans.slice(0, 5).map((x) => <span key={x.map_name} className="veto-chip ban">{x.map_name} ×{x.n}</span>)}</div>
              <div className="muted" style={{ fontSize: 12 }}>Picks</div>
              <div>{v.picks.slice(0, 5).map((x) => <span key={x.map_name} className="veto-chip pick">{x.map_name} ×{x.n}</span>)}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
