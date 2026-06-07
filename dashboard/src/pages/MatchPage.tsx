// Match view (P6 revision): prediction + narrative ("what might happen"), and for
// completed matches the replay trace, biggest swing, and expected-vs-actual
// ("what actually happened"). Everything is framed from PRX's perspective.
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { getMatch, type MatchView } from '../lib/api'
import { Insight } from '../components/Insight'
import { WinProbBar } from '../components/WinProbBar'

function ConfChip({ c }: { c: string }) {
  const tip = c === 'sharp' ? 'big skill gap — the model is reliable here (~74% out-of-sample)'
    : c === 'coinflip' ? 'evenly matched / elite — treat as a coin-flip'
    : 'some edge, but modest'
  return <span className={`conf-chip conf-${c}`} title={tip}>{c}</span>
}

function ExpectedTable({ d }: { d: MatchView }) {
  const rows = [...d.expected_stats].sort((a, b) => (b.delta_acs ?? 0) - (a.delta_acs ?? 0))
  return (
    <div className="panel">
      <div className="sub">Expected vs actual — who showed up</div>
      <table className="stints">
        <thead><tr><th>Player</th><th>Expected ACS</th><th>Actual ACS</th><th>Δ</th></tr></thead>
        <tbody>
          {rows.map((r) => {
            const d2 = r.delta_acs
            const cls = d2 == null ? '' : d2 >= 25 ? 'over' : d2 <= -25 ? 'under' : ''
            return (
              <tr key={r.player_id}>
                <td><Link to={`/player/${r.player_id}`}>{r.handle}</Link></td><td>{r.expected_acs}</td><td>{r.actual_acs ?? '—'}</td>
                <td className={cls}>{d2 == null ? '—' : `${d2 > 0 ? '+' : ''}${d2}`}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function MatchPage() {
  const { id } = useParams()
  const matchId = Number(id)
  const q = useQuery<MatchView>({ queryKey: ['match', matchId], queryFn: () => getMatch(matchId), enabled: Number.isFinite(matchId) })

  if (q.isLoading) return <div className="panel loading">Loading match…</div>
  if (q.isError) return <div className="panel error">{(q.error as Error).message}</div>
  const d = q.data!
  const t1 = d.team1.name ?? 'Team 1'
  const t2 = d.team2.name ?? 'Team 2'
  const prxSide = d.prx_side ?? 'team1'
  const prxName = prxSide === 'team1' ? t1 : t2
  const oppName = prxSide === 'team1' ? t2 : t1
  const toPrx = (p: number) => (prxSide === 'team1' ? p : 1 - p)

  // Factors framed for PRX (drop the near-zero/noisy recent-form term).
  const factors = d.prediction.top_factors
    .filter((f) => !f.factor.startsWith('Recent form'))
    .map((f) => ({ ...f, favoursPrx: (f.favors === 'team1') === (prxSide === 'team1') }))

  return (
    <>
      <div className="panel">
        <div className="teams-row">
          <Link to={`/team/${d.team1.id}`} className="team-name t1">{t1}</Link>
          <span className="scoreline">
            {d.completed ? <><span className="t1">{d.team1_score}</span>–<span className="t2">{d.team2_score}</span></> : <span className="muted">{d.format}</span>}
          </span>
          <Link to={`/team/${d.team2.id}`} className="team-name t2">{t2}</Link>
        </div>
        <div className="muted" style={{ textAlign: 'center', marginBottom: 6 }}>
          {[d.event, d.series_name, d.date].filter(Boolean).join(' · ')}
        </div>
        <div style={{ textAlign: 'center', marginBottom: 12 }}>
          <Link to={`/matchup/${d.team1.id}/${d.team2.id}`}>Scout this matchup →</Link>
        </div>

        {d.completed && <Insight insight={d.postmatch_insight} />}
        <Insight insight={d.prematch_insight} />

        <div style={{ marginTop: 12 }}>
          <div className="sub">
            Pre-match win probability
            {d.prediction.confidence && <ConfChip c={d.prediction.confidence} />}
          </div>
          <WinProbBar p1={toPrx(d.prediction.team1_win_prob)} label1={prxName} label2={oppName} />
        </div>

        {d.prediction.map_predictions.length > 0 && (
          <div className="maps-grid">
            <div className="sub" style={{ marginTop: 12 }}>Per map — {prxName} win probability</div>
            {d.prediction.map_predictions.map((m) => (
              <div className="map-row" key={m.map_name}>
                <span className="mname">{m.map_name}</span>
                <div className="mini-bar"><div style={{ width: `${Math.round(toPrx(m.team1_win_prob) * 100)}%` }} /></div>
                <span className="mpct">{(toPrx(m.team1_win_prob) * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}

        <div className="factors">
          <div className="sub">What's driving the prediction</div>
          {factors.map((f) => (
            <div className="factor" key={f.factor}>
              <span>{f.factor}</span>
              <div className={`fbar ${f.favoursPrx ? 'favors-team1' : 'favors-team2'}`}>
                <div style={{ width: `${Math.round(f.weight * 100)}%` }} />
              </div>
              <span className="fav">favours {f.favoursPrx ? prxName : oppName}</span>
            </div>
          ))}
        </div>
      </div>

      {d.completed && d.expected_stats.some((e) => e.actual_acs != null) && <ExpectedTable d={d} />}

      {d.completed && d.replay && d.replay.length > 0 && (
        <div className="panel">
          <div className="sub">Round-by-round — win probability for {prxName}</div>
          {d.replay.map((m) => (
            <div key={m.map_index} style={{ marginBottom: 18 }}>
              <div className="sub" style={{ marginBottom: 4 }}>Map {m.map_index + 1} — {m.map_name}</div>
              <ResponsiveContainer width="100%" height={170}>
                <LineChart data={m.rounds.map((r) => ({ round: r.round, prob: r.pre_round_prob_team1 == null ? null : toPrx(r.pre_round_prob_team1) }))}
                  margin={{ top: 6, right: 10, bottom: 0, left: -20 }}>
                  <CartesianGrid stroke="#2a3340" vertical={false} />
                  <XAxis dataKey="round" stroke="#8b949e" fontSize={11} />
                  <YAxis domain={[0, 1]} stroke="#8b949e" fontSize={11} tickFormatter={(v) => `${Math.round(v * 100)}`} />
                  <ReferenceLine y={0.5} stroke="#3a4452" strokeDasharray="3 3" />
                  <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #2a3340', fontSize: 12 }}
                    formatter={(v) => `${(Number(v) * 100).toFixed(0)}%`} labelFormatter={(l) => `Round ${l}`} />
                  <Line type="monotone" dataKey="prob" stroke="#4ea1ff" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
