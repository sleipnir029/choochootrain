// Typed API client (P6 revision). View-shaped endpoints: one call per screen.
// Relative URLs so the bundle works behind the dev proxy and served from FastAPI.
import axios from 'axios'

export const PRX_TEAM_ID = 624
const http = axios.create({ baseURL: '' })

// --- shared shapes ----------------------------------------------------------
export interface Insight { headline: string; points: string[]; tone: string }
export interface TeamBrief { id: number; name: string | null; logo: string | null }
export interface Factor { factor: string; weight: number; favors: 'team1' | 'team2' }
export interface MapPrediction {
  map_name: string; team1_win_prob: number; team1_win_prob_hdi: [number, number]; picked_by: number | null
}
export type Confidence = 'sharp' | 'lean' | 'coinflip'
export interface Prediction {
  team1_win_prob: number
  team1_win_prob_hdi: [number, number] | null
  series_win_prob: { team1: number; team2: number }
  confidence?: Confidence | null
  map_predictions: MapPrediction[]
  top_factors: Factor[]
}
export interface ExpectedRow {
  player_id: number; handle: string; team_id: number; n_history: number
  expected_acs: number; actual_acs?: number; delta_acs?: number
  expected_kills: number; expected_deaths: number; expected_assists: number
}

// --- home -------------------------------------------------------------------
export interface RecentResult {
  match_id: number; date: string; opponent: string | null; opponent_id: number
  prx_score: number; opp_score: number; prx_won: boolean
  predicted_prx_win_prob: number; model_correct: boolean
}
export interface RosterPlayer {
  player_id: number; handle: string; real_name: string | null; country: string | null; skill: number | null
}
export type Hero =
  | { kind: 'live'; match_id: number; current_map: string | null; subject: string; subject_win_prob: number | null; opponent: string | null; insight: Insight }
  | { kind: 'next'; schedule: Record<string, unknown>; prediction?: PreMatchLite; insight: Insight | null }
  | {
      kind: 'recent'; match_id: number; team1: TeamBrief; team2: TeamBrief
      team1_score: number; team2_score: number; winner_id: number | null
      prx_side: 'team1' | 'team2'; prediction: Prediction; insight: Insight | null
    }
export interface PreMatchLite extends Prediction { team1: TeamBrief; team2: TeamBrief; series_format: string }
export interface Home {
  prx: {
    team: { team_id: number; name: string; tag: string | null; region: string | null; logo_url: string | null }
    rank: { rank: number; of: number; rating: number } | null
    roster: RosterPlayer[]
  }
  hero: Hero | null
  recent: RecentResult[]
}

// --- match view -------------------------------------------------------------
export interface ReplayRound { round: number; team1_side: 'ct' | 't'; pre_round_prob_team1: number | null; winner: 'team1' | 'team2' }
export interface ReplayMap { map_index: number; map_name: string; rounds: ReplayRound[] }
export interface MatchView {
  match_id: number; completed: boolean; event: string | null; series_name: string | null; date: string; format: string
  team1: TeamBrief; team2: TeamBrief; team1_score: number; team2_score: number; winner_id: number | null
  prx_side: 'team1' | 'team2' | null
  prediction: Prediction
  prematch_insight: Insight | null
  expected_stats: ExpectedRow[]
  replay?: ReplayMap[]
  biggest_swing?: { map_name: string; round: number; delta: number } | null
  postmatch_insight?: Insight | null
}

// --- player view ------------------------------------------------------------
export interface Stint {
  team_id: number; team_name: string | null; team_tag: string | null; n_maps: number
  avg_rating: number | null; avg_acs: number | null; avg_kills: number | null
  avg_deaths: number | null; avg_assists: number | null; first_date: string; last_date: string
}
export interface FormRow { match_id: number; date: string; opponent: string | null; expected_acs: number; actual_acs: number; delta_acs: number }
export interface DuelMatchup { opponent: string; kills: number; deaths: number; net: number }
export interface PlayerView {
  player_id: number; handle: string; real_name: string | null; country: string | null
  current_team_id: number | null; current_team_name: string | null; current_team_tag: string | null
  skill: { rating: number; percentile: number; rated_players: number } | null
  stints: Stint[]
  recent_form: FormRow[]
  duels?: { best: DuelMatchup[]; worst: DuelMatchup[] }
}

// --- live (for the top-bar pill) --------------------------------------------
export type Live = { mode: 'live'; [k: string]: unknown } | { mode: 'no_live'; [k: string]: unknown }

// --- calls ------------------------------------------------------------------
// --- model trust / track record --------------------------------------------
export interface RegimeAgg {
  tier?: string; confidence?: Confidence; bucket?: string
  n: number; acc: number; brier: number; elo_sign_acc?: number; logloss?: number
}
export interface ReliabilityPoint { bin: number; predicted: number; actual: number; n: number }
export interface RecentCall {
  match_id: number; date_utc: string; tier: string
  team1_win_prob: number; team1_won: number; correct: number; confidence: Confidence
}
export interface TrackRecord {
  available: boolean; reason?: string
  overall?: { n: number; acc: number; elo_sign_acc: number; brier: number; logloss: number }
  by_tier?: RegimeAgg[]; by_confidence?: RegimeAgg[]; by_elo_bucket?: RegimeAgg[]
  reliability?: ReliabilityPoint[]; recent?: RecentCall[]
}
export const getTrackRecord = () => http.get<TrackRecord>('/api/model/track-record').then((r) => r.data)

// --- team scouting ----------------------------------------------------------
export interface MapPoolRow { map_name: string; n: number; win_rate: number | null; ct_win_rate: number | null; t_win_rate: number | null }
export interface CompRow { map_name: string; comp: string[]; n: number; win_rate: number | null }
export interface AgentPool { handle: string; agents: { agent: string; n: number }[] }
export interface DuelRow { handle: string; fk: number; fd: number; win_rate: number | null }
export interface VetoRow { map_name: string; n: number }
export interface ImpactRow {
  player_handle: string; clutches: number; big_clutches: number
  multikills: number; big_multikills: number; plants: number; defuses: number
}
export interface TeamScouting {
  team: { team_id: number; name: string; tag: string | null; region: string | null; logo_url: string | null }
  window_maps: number
  map_pool: MapPoolRow[]
  economy: { pistol: number; eco: number; semi_buy: number; full_buy: number } | null
  agents: { by_player: AgentPool[]; comps_by_map: CompRow[] }
  opening_duels: { team: { fk: number; fd: number; win_rate: number | null } | null; by_player: DuelRow[] }
  veto: { n_matches: number; bans: VetoRow[]; picks: VetoRow[] }
  impact: ImpactRow[]
}
export const getTeamScouting = (id: number) => http.get<TeamScouting>(`/api/teams/${id}/scouting`).then((r) => r.data)

export const getHome = () => http.get<Home>('/api/home').then((r) => r.data)
export const getMatch = (id: number) => http.get<MatchView>(`/api/matches/${id}`).then((r) => r.data)
export const getPlayer = (id: number) => http.get<PlayerView>(`/api/players/${id}`).then((r) => r.data)
export const getLive = () => http.get<Live>('/api/predict/live').then((r) => r.data)
