// Broadcast-style matchup hero: pick-map splash background, big team logos + form, and the
// answer-first win probability. Used by the Matchup page (the flagship of the bold redesign).
import type { ReactNode } from 'react'
import { TeamLogo } from './Visual'
import { FormDots } from './Viz'
import { mapAsset } from '../lib/assets'

export function MatchupHero({ t1Name, t2Name, t1Logo, t2Logo, p1, confidence, pickMap, takeaway, form1, form2 }: {
  t1Name: string; t2Name: string; t1Logo?: string | null; t2Logo?: string | null
  p1: number; confidence?: string | null; pickMap?: string | null
  takeaway?: ReactNode; form1: ('W' | 'L')[]; form2: ('W' | 'L')[]
}) {
  const favT1 = p1 >= 0.5
  const favPct = Math.round((favT1 ? p1 : 1 - p1) * 100)
  const pc1 = Math.round(p1 * 100), pc2 = 100 - pc1
  const splash = pickMap ? mapAsset(pickMap)?.splash : null
  return (
    <div className="bhero">
      {splash && <div className="bhero-bg" style={{ backgroundImage: `url(${splash})` }} />}
      <div className="bhero-veil" />
      <div className="bhero-inner">
        {pickMap && <div className="bhero-map">likely decider · {pickMap}</div>}
        <div className="bhero-teams">
          <div className="bhero-team t1">
            <TeamLogo url={t1Logo} name={t1Name} size={68} />
            <div className="tcol"><span className="tn">{t1Name}</span>{form1.length > 0 && <FormDots results={form1} />}</div>
          </div>
          <div className="bhero-mid">
            <div className={`bhero-prob ${favT1 ? 't1' : 't2'}`}>
              <span className="who">{favT1 ? t1Name : t2Name} favoured — map</span>
              <span className="pct">{favPct}%</span>
            </div>
            {confidence && <div className="bhero-conf"><span className={`conf-chip conf-${confidence}`}>{confidence}</span></div>}
          </div>
          <div className="bhero-team t2 right">
            <TeamLogo url={t2Logo} name={t2Name} size={68} />
            <div className="tcol"><span className="tn">{t2Name}</span>{form2.length > 0 && <FormDots results={form2} />}</div>
          </div>
        </div>
        <div className="bhero-bar">
          <div className="s1" style={{ width: `${pc1}%` }}>{pc1 >= 14 ? `${t1Name} ${pc1}%` : ''}</div>
          <div className="s2" style={{ width: `${pc2}%` }}>{pc2 >= 14 ? `${t2Name} ${pc2}%` : ''}</div>
        </div>
        {takeaway && <div className="bhero-take">{takeaway}</div>}
      </div>
    </div>
  )
}
