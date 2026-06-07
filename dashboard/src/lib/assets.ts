// Valorant visual assets (Phase B): resolve agent/map art + minimap transforms by NAME from
// the committed valorant-api manifest (scripts/fetch_assets.py). Image URLs are hotlinked to
// media.valorant-api.com; the manifest (not the binaries) is committed.
import manifest from '../assets/valorant-assets.json'

export interface AgentAsset { role: string | null; icon: string | null; roleIcon: string | null }
export interface MapAsset {
  splash: string | null; minimap: string | null; listView: string | null
  xMultiplier: number | null; yMultiplier: number | null; xScalarToAdd: number | null; yScalarToAdd: number | null
}

const agents = manifest.agents as Record<string, AgentAsset>
const maps = manifest.maps as Record<string, MapAsset>

// Warehouse agent names -> manifest keys (manifest keys are lowercased display names).
const AGENT_ALIAS: Record<string, string> = { kayo: 'kay/o' }

export function agentAsset(name: string): AgentAsset | null {
  const k = name.toLowerCase()
  return agents[AGENT_ALIAS[k] ?? k] ?? null
}
export function mapAsset(name: string): MapAsset | null {
  return maps[name.toLowerCase()] ?? null
}

// vlr.gg logos come back protocol-relative (//owcdn.net/...); normalize to https.
export function teamLogo(url: string | null | undefined): string | null {
  if (!url) return null
  return url.startsWith('//') ? `https:${url}` : url
}
