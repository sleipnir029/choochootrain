// Team scouting (Wave B — analyst): map pool + side tendencies + economy + agent
// comps + opening duels, over the team's recent maps. Derived from existing data.
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { getTeamScouting, type TeamScouting } from '../lib/api'

const pc = (x: number | null) => (x == null ? '—' : `${Math.round(x * 100)}%`)

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

  return (
    <>
      <div className="prx-head">
        <h2>{s.team.name}</h2>
        <span className="rank-chip">scouting · last {s.window_maps} maps</span>
      </div>

      <div className="panel">
        <div className="sub">Map pool & side tendencies</div>
        <table className="stints">
          <thead><tr><th>Map</th><th>Played</th><th>Win%</th><th>CT win%</th><th>T win%</th></tr></thead>
          <tbody>
            {s.map_pool.map((m) => (
              <tr key={m.map_name}>
                <td>{m.map_name}</td><td>{m.n}</td>
                <td className={(m.win_rate_adj ?? 0) >= 0.6 ? 'over' : (m.win_rate_adj ?? 1) <= 0.4 ? 'under' : ''}>{pc(m.win_rate)}</td>
                <td className="muted">{pc(m.ct_win_rate)}</td>
                <td className="muted">{pc(m.t_win_rate)}</td>
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
                  <td>{mv.map_name}</td>
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
          <div className="sub">Economy efficiency (win% by buy type)</div>
          <div className="roster-grid">
            {[['Pistol', econ.pistol], ['Eco', econ.eco], ['Semi-buy', econ.semi_buy], ['Full-buy', econ.full_buy]].map(([k, v]) => (
              <div className="roster-card" key={k as string}>
                <div className="rc-name muted">{k}</div>
                <div className="rc-skill">{v}%</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="panel">
        <div className="sub">Most-run comp per map</div>
        <table className="stints">
          <thead><tr><th>Map</th><th>Comp</th><th>Roles</th><th>n</th><th>Win%</th></tr></thead>
          <tbody>
            {s.agents.comps_by_map.map((c) => (
              <tr key={c.map_name}>
                <td>{c.map_name}</td>
                <td>{c.comp.join(' · ')}</td>
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
                  ? <><span className="rank-chip">{p.profile.label}</span>{' '}
                      <span className="muted">{p.profile.main_role} · {p.profile.distinct_agents} agents</span></>
                  : <span className="muted">—</span>}</td>
                <td className="muted">{p.agents.slice(0, 6).map((a) => `${a.agent} (${a.n})`).join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
