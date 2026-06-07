// Head-to-head matchup — the analyst pre-match prep view, redesigned broadcast-style:
// a splash-art hero with the answer-first call, then a two-column body (form dumbbell +
// key duels | map confidence + likely comps), with the raw map/veto tables as detail.
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { getMatchup, type Matchup } from '../lib/api'
import { Insight } from '../components/Insight'
import { MatchupHero } from '../components/MatchupHero'
import { MapThumb, Comp } from '../components/Visual'
import { Dumbbell, Spectrum } from '../components/Viz'

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
  const edges = m.map_edge
    .filter((e) => e.t1_win_rate_adj != null && e.t2_win_rate_adj != null)
    .map((e) => ({ map: e.map_name, edge: (e.t1_win_rate_adj as number) - (e.t2_win_rate_adj as number) }))
  const best = edges.length ? edges.reduce((x, y) => (y.edge > x.edge ? y : x)) : null   // best for team1
  const worst = edges.length ? edges.reduce((x, y) => (y.edge < x.edge ? y : x)) : null  // worst for team1
  const takeaway = best && worst
    ? <><strong>{n1}</strong> should steer to <strong>{best.map}</strong> and ban <strong>{worst.map}</strong>.</>
    : null

  return (
    <>
      <MatchupHero
        t1Name={n1} t2Name={n2} t1Logo={m.team1.logo} t2Logo={m.team2.logo}
        p1={p1} confidence={m.prediction.confidence} pickMap={best?.map ?? null}
        takeaway={takeaway} form1={m.form1} form2={m.form2}
      />
      <div className="muted" style={{ textAlign: 'center', margin: '-6px 0 16px', fontSize: 13 }}>
        Scout <Link to={`/team/${m.team1.id}`}>{n1}</Link> · <Link to={`/team/${m.team2.id}`}>{n2}</Link>
      </div>

      <div className="panel"><Insight insight={m.prematch_insight} /></div>

      <div className="grid-2">
        <div>
          {m.dumbbell.length > 0 && (
            <div className="panel">
              <div className="sub">Form head-to-head — {n1} vs {n2}</div>
              <Dumbbell aName={n1} bName={n2}
                rows={m.dumbbell.map((d) => ({ label: d.label, a: d.t1, b: d.t2, aText: pc(d.t1), bText: pc(d.t2) }))} />
            </div>
          )}

          <div className="panel">
            <div className="sub">Key player duels — cross-roster history</div>
            <div className="recent-list">
              {m.key_duels.length === 0 && <div className="muted">No prior cross-roster duels on record.</div>}
              {m.key_duels.slice(0, 8).map((d, i) => (
                <div key={i} className="recent-row" style={{ gridTemplateColumns: '1fr 70px 1fr 56px' }}>
                  <span className="t1" style={{ textAlign: 'right' }}>{d.t1_player}</span>
                  <span style={{ textAlign: 'center', fontVariantNumeric: 'tabular-nums' }}>{d.kills}–{d.deaths}</span>
                  <span className="t2">{d.t2_player}</span>
                  <span className={d.net > 0 ? 'over' : 'under'} style={{ textAlign: 'right' }}>{d.net > 0 ? '+' : ''}{d.net}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div>
          <div className="panel">
            <div className="sub">Map confidence — green favours {n1}, red favours {n2}</div>
            <Spectrum rows={m.map_edge
              .filter((e) => e.t1_win_rate_adj != null && e.t2_win_rate_adj != null)
              .map((e) => {
                const edge = (e.t1_win_rate_adj as number) - (e.t2_win_rate_adj as number)
                const note = Math.abs(edge) < 0.06 ? 'even' : edge > 0 ? `${n1} +${Math.round(edge * 100)}` : `${n2} +${Math.round(-edge * 100)}`
                return { label: <span className="map-cell"><MapThumb map={e.map_name} h={24} />{e.map_name}</span>, edge: edge * 2.4, note }
              })} />
          </div>

          {(m.comps1.length > 0 || m.comps2.length > 0) && (
            <div className="panel">
              <div className="sub">Likely comps — most-run lineup per map</div>
              {[{ n: n1, comps: m.comps1 }, { n: n2, comps: m.comps2 }].map(({ n, comps }) => (
                <div key={n} style={{ marginBottom: 12 }}>
                  <div className="team-name" style={{ fontSize: 14, marginBottom: 6 }}>{n}</div>
                  {comps.slice(0, 5).map((c) => (
                    <div key={c.map_name} style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '5px 0' }}>
                      <MapThumb map={c.map_name} h={22} />
                      <span className="muted" style={{ minWidth: 66, fontSize: 12 }}>{c.map_name}</span>
                      <Comp comp={c.comp} size={24} />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <details className="panel detail">
        <summary>Map-by-map detail & veto tendencies</summary>
        <table className="stints" style={{ marginTop: 12 }}>
          <thead><tr><th>Map</th><th>{n1} win%</th><th>{n2} win%</th><th>Edge</th></tr></thead>
          <tbody>
            {m.map_edge.map((e) => {
              const a1 = e.t1_win_rate_adj ?? 0.5, a2 = e.t2_win_rate_adj ?? 0.5
              const diff = a1 - a2
              const edge = Math.abs(diff) < 0.12 ? '' : diff > 0 ? `${n1} +${Math.round(diff * 100)}` : `${n2} +${Math.round(-diff * 100)}`
              return (
                <tr key={e.map_name}>
                  <td><span className="map-cell"><MapThumb map={e.map_name} h={26} />{e.map_name}</span></td>
                  <td className={a1 >= 0.6 ? 'over' : a1 <= 0.4 ? 'under' : ''}>{pc(e.t1_win_rate)} <span className="muted">({e.t1_n})</span></td>
                  <td className={a2 >= 0.6 ? 'over' : a2 <= 0.4 ? 'under' : ''}>{pc(e.t2_win_rate)} <span className="muted">({e.t2_n})</span></td>
                  <td className={diff > 0.12 ? 'over' : diff < -0.12 ? 'under' : 'muted'}>{edge || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="veto-cols" style={{ marginTop: 16 }}>
          {[{ n: n1, v: m.veto1 }, { n: n2, v: m.veto2 }].map(({ n, v }) => (
            <div key={n}>
              <div className="team-name" style={{ fontSize: 14, marginBottom: 6 }}>{n}</div>
              <div className="muted" style={{ fontSize: 12 }}>Bans</div>
              <div style={{ marginBottom: 8 }}>{v.bans.slice(0, 5).map((x) => <span key={x.map_name} className="veto-chip ban">{x.map_name} ×{x.n}</span>)}</div>
              <div className="muted" style={{ fontSize: 12 }}>Picks</div>
              <div>{v.picks.slice(0, 5).map((x) => <span key={x.map_name} className="veto-chip pick">{x.map_name} ×{x.n}</span>)}</div>
            </div>
          ))}
        </div>
      </details>
    </>
  )
}
