// PRX home (P6 revision): hero (live/next/last-match) + recent results + roster.
// Everything is click-through — no ID typing.
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getHome, type Hero, type Home } from '../lib/api'
import { Insight } from '../components/Insight'
import { WinProbBar } from '../components/WinProbBar'

function HeroCard({ hero }: { hero: Hero }) {
  if (hero.kind === 'recent') {
    const prxP = hero.prx_side === 'team1' ? hero.prediction.team1_win_prob : 1 - hero.prediction.team1_win_prob
    const t1 = hero.team1.name ?? 'Team 1'
    const t2 = hero.team2.name ?? 'Team 2'
    return (
      <Link to={`/match/${hero.match_id}`} className="hero-card">
        <div className="hero-tag">Last match</div>
        <div className="teams-row">
          <span className="team-name t1">{t1}</span>
          <span className="scoreline"><span className="t1">{hero.team1_score}</span>–<span className="t2">{hero.team2_score}</span></span>
          <span className="team-name t2">{t2}</span>
        </div>
        <Insight insight={hero.insight} />
        <WinProbBar p1={prxP} label1="PRX" label2={(hero.prx_side === 'team1' ? t2 : t1)} />
        <div className="hero-cta">View full breakdown →</div>
      </Link>
    )
  }
  if (hero.kind === 'next') {
    const p = hero.prediction
    return (
      <div className="hero-card static">
        <div className="hero-tag">Next match</div>
        {p ? (
          <>
            <div className="teams-row">
              <span className="team-name t1">{p.team1.name}</span>
              <span className="muted">{p.series_format}</span>
              <span className="team-name t2">{p.team2.name}</span>
            </div>
            <Insight insight={hero.insight} />
            <WinProbBar p1={p.team1_win_prob} label1={p.team1.name ?? 'PRX'} label2={p.team2.name ?? 'Opp'} />
          </>
        ) : (
          <div className="muted">Upcoming PRX match scheduled — prediction available once the opponent is in the warehouse.</div>
        )}
      </div>
    )
  }
  // live
  return (
    <Link to={`/match/${hero.match_id}`} className="hero-card">
      <div className="hero-tag live">● Live{hero.current_map ? ` · ${hero.current_map}` : ''}</div>
      <Insight insight={hero.insight} />
      {hero.prx_win_prob != null && <WinProbBar p1={hero.prx_win_prob} label1="PRX" label2={hero.opponent ?? 'Opponent'} />}
      <div className="hero-cta">Follow live →</div>
    </Link>
  )
}

export function HomePage() {
  const q = useQuery<Home>({ queryKey: ['home'], queryFn: getHome })
  if (q.isLoading) return <div className="panel loading">Loading PRX dashboard…</div>
  if (q.isError) return <div className="panel error">{(q.error as Error).message}</div>
  const { prx, hero, recent } = q.data!

  return (
    <>
      <div className="prx-head">
        <h2>{prx.team.name}</h2>
        {prx.rank && <span className="rank-chip">#{prx.rank.rank} of {prx.rank.of} · Elo {prx.rank.rating}</span>}
      </div>

      {hero && <HeroCard hero={hero} />}

      <div className="panel">
        <div className="sub">Recent matches — model's call vs the result</div>
        <div className="recent-list">
          {recent.map((r) => (
            <Link key={r.match_id} to={`/match/${r.match_id}`} className="recent-row">
              <span className={`res ${r.prx_won ? 'win' : 'loss'}`}>{r.prx_won ? 'W' : 'L'}</span>
              <span className="opp">vs {r.opponent}</span>
              <span className="score">{r.prx_score}–{r.opp_score}</span>
              <span className="muted date">{r.date}</span>
              <span className="pred">predicted {(r.predicted_prx_win_prob * 100).toFixed(0)}%</span>
              <span className={`mark ${r.model_correct ? 'ok' : 'miss'}`}>{r.model_correct ? '✓' : '✗'}</span>
            </Link>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="sub">Roster — conservative skill rating (click a player)</div>
        <div className="roster-grid">
          {prx.roster.map((p) => (
            <Link key={p.player_id} to={`/player/${p.player_id}`} className="roster-card">
              <div className="rc-handle">{p.handle}</div>
              <div className="rc-name muted">{p.real_name ?? ''}</div>
              <div className="rc-skill">{p.skill != null ? p.skill.toFixed(1) : '—'}</div>
            </Link>
          ))}
        </div>
      </div>
    </>
  )
}
