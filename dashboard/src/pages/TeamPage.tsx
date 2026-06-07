// Team scouting (Wave B — analyst): map pool + side tendencies + economy + agent
// comps + opening duels, over the team's recent maps. Derived from existing data.
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { getTeamScouting, type TeamScouting } from '../lib/api'
import { AgentIcon, TeamLogo, MapThumb, Comp } from '../components/Visual'
import { FormDots, Bar } from '../components/Viz'

const pc = (x: number | null) => (x == null ? '—' : `${Math.round(x * 100)}%`)
const ibar = (x: number | null, cls: string) => (
  <><span className={`ibar ${cls}`}><span style={{ width: `${Math.round((x ?? 0) * 100)}%` }} /></span>{pc(x)}</>
)

export function TeamPage() {
  const { id } = useParams()
  const teamId = Number(id)
  const q = useQuery<TeamScouting>({
    queryKey: ['scouting', teamId], queryFn: () => getTeamScouting(teamId), enabled: Number.isFinite(teamId),
  })
  if (q.isLoading) return <div className="panel loading">Loading scouting report…</div>
  if (q.isError) return <div className="panel error">{(q.error as Error).message}</div>
  const s = q.data!
  const econ = s.economy
  const wins = s.recent_form.filter((f) => f === 'W').length
  const losses = s.recent_form.length - wins
  const bestMap = [...s.map_pool].sort((a, b) => (b.win_rate_adj ?? 0) - (a.win_rate_adj ?? 0))[0]
  const riser = s.meta_shift.movers.find((mv) => mv.delta > 0)

  return (
    <>
      <div className="prx-head team-head-logo">
        <TeamLogo url={s.team.logo_url} name={s.team.name} size={38} />
        <h2>{s.team.name}</h2>
        <span className="rank-chip">scouting · last {s.window_maps} maps</span>
        {s.recent_form.length > 0 && <FormDots results={s.recent_form} />}
      </div>

      {(wins + losses > 0 || bestMap) && (
        <div className="takeaway">
          <strong>{s.team.name}</strong>
          {wins + losses > 0 && <> are {wins}–{losses} in their last {wins + losses}</>}
          {bestMap && <> · strongest on <strong>{bestMap.map_name}</strong> ({pc(bestMap.win_rate)} over {bestMap.n})</>}
          {riser && <> · rising on <strong>{riser.map_name}</strong> (+{Math.round(riser.delta * 100)})</>}.
        </div>
      )}

      <div className="panel">
        <div className="sub">Map pool & side tendencies</div>
        <table className="stints">
          <thead><tr><th>Map</th><th>Played</th><th>Win%</th><th>CT win%</th><th>T win%</th></tr></thead>
          <tbody>
            {s.map_pool.map((m) => (
              <tr key={m.map_name}>
                <td><span className="map-cell"><MapThumb map={m.map_name} h={28} />{m.map_name}</span></td><td>{m.n}</td>
                <td className={(m.win_rate_adj ?? 0) >= 0.6 ? 'over' : (m.win_rate_adj ?? 1) <= 0.4 ? 'under' : ''}>{pc(m.win_rate)}</td>
                <td className="muted">{ibar(m.ct_win_rate, 'ct')}</td>
                <td className="muted">{ibar(m.t_win_rate, 't')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {s.meta_shift.movers.length > 0 && (
        <div className="panel">
          <div className="sub">
            Meta shift — maps this team has changed on
            {s.meta_shift.recent?.patches && s.meta_shift.prior?.patches && (
              <span className="muted"> · recent (patch {s.meta_shift.recent.patches.from}–{s.meta_shift.recent.patches.to}) vs prior (patch {s.meta_shift.prior.patches.from}–{s.meta_shift.prior.patches.to})</span>
            )}
          </div>
          <table className="stints">
            <thead><tr><th>Map</th><th>Prior</th><th>Recent</th><th>Shift</th></tr></thead>
            <tbody>
              {s.meta_shift.movers.map((mv) => (
                <tr key={mv.map_name}>
                  <td><span className="map-cell"><MapThumb map={mv.map_name} h={28} />{mv.map_name}</span></td>
                  <td className="muted">{pc(mv.prior_win_rate)} <span className="muted">({mv.prior_n})</span></td>
                  <td>{pc(mv.recent_win_rate)} <span className="muted">({mv.recent_n})</span></td>
                  <td className={mv.delta > 0 ? 'over' : 'under'}>{mv.delta > 0 ? '+' : ''}{Math.round(mv.delta * 100)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {econ && (
        <div className="panel">
          <div className="sub">Economy — round win% by buy type</div>
          {([['Pistol', econ.pistol], ['Eco', econ.eco], ['Semi-buy', econ.semi_buy], ['Full-buy', econ.full_buy]] as [string, number][]).map(([k, v]) => (
            <Bar key={k} label={k} frac={v / 100} value={`${v}%`} />
          ))}
        </div>
      )}

      <div className="panel">
        <div className="sub">Most-run comp per map</div>
        <table className="stints">
          <thead><tr><th>Map</th><th>Comp</th><th>Roles</th><th>n</th><th>Win%</th></tr></thead>
          <tbody>
            {s.agents.comps_by_map.map((c) => (
              <tr key={c.map_name}>
                <td><span className="map-cell"><MapThumb map={c.map_name} h={28} />{c.map_name}</span></td>
                <td><Comp comp={c.comp} size={28} /></td>
                <td className="muted">{c.roles.map((r) => `${r.n} ${r.role}`).join(' / ')}</td>
                <td>{c.n}</td>
                <td className={(c.win_rate_adj ?? 0) >= 0.6 ? 'over' : (c.win_rate_adj ?? 1) <= 0.4 ? 'under' : ''}>{pc(c.win_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <div className="sub">Opening duels — entry win rate (first kills vs first deaths)</div>
        {s.opening_duels.team && (
          <div className="muted" style={{ marginBottom: 8 }}>
            Team: {s.opening_duels.team.fk} FK / {s.opening_duels.team.fd} FD ·{' '}
            <strong>{pc(s.opening_duels.team.win_rate)}</strong> entry win rate
          </div>
        )}
        <table className="stints">
          <thead><tr><th>Player</th><th>FK</th><th>FD</th><th>Entry win%</th></tr></thead>
          <tbody>
            {s.opening_duels.by_player.map((d) => (
              <tr key={d.handle}>
                <td>{d.handle}</td><td>{d.fk}</td><td>{d.fd}</td>
                <td className={(d.win_rate ?? 0) >= 0.55 ? 'over' : (d.win_rate ?? 1) <= 0.45 ? 'under' : ''}>{pc(d.win_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(s.veto.bans.length > 0 || s.veto.picks.length > 0) && (
        <div className="panel">
          <div className="sub">Veto tendencies (last {s.veto.n_matches} matches)</div>
          <div className="veto-cols">
            <div>
              <div className="muted" style={{ marginBottom: 4 }}>Most banned</div>
              {s.veto.bans.map((b) => <span key={b.map_name} className="veto-chip ban">{b.map_name} ×{b.n}</span>)}
            </div>
            <div>
              <div className="muted" style={{ marginBottom: 4 }}>Most picked</div>
              {s.veto.picks.map((p) => <span key={p.map_name} className="veto-chip pick">{p.map_name} ×{p.n}</span>)}
            </div>
          </div>
        </div>
      )}

      {s.impact.length > 0 && (
        <div className="panel">
          <div className="sub">Round impact — clutches & multikills (recent matches)</div>
          <table className="stints">
            <thead><tr><th>Player</th><th>Clutches won</th><th>1v3+</th><th>Multikills</th><th>4K/5K</th></tr></thead>
            <tbody>
              {s.impact.map((p) => (
                <tr key={p.player_handle}>
                  <td>{p.player_handle}</td>
                  <td className={p.clutches >= 15 ? 'over' : ''}>{p.clutches}</td>
                  <td className="muted">{p.big_clutches}</td>
                  <td>{p.multikills}</td><td className="muted">{p.big_multikills}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="panel">
        <div className="sub">Agent pools & role profile</div>
        <table className="stints">
          <thead><tr><th>Player</th><th>Profile</th><th>Agents (most played)</th></tr></thead>
          <tbody>
            {s.agents.by_player.map((p) => (
              <tr key={p.handle}>
                <td>{p.handle}</td>
                <td>{p.profile
                  ? <span className={`role-tag ${p.profile.label}`}>{p.profile.label} · {p.profile.main_role} · {p.profile.distinct_agents} agents</span>
                  : <span className="muted">—</span>}</td>
                <td>
                  <span className="agent-pool">
                    {p.agents.slice(0, 6).map((a) => (
                      <span className="ap" key={a.agent}><AgentIcon agent={a.agent} size={28} /><small>{a.n}</small></span>
                    ))}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
