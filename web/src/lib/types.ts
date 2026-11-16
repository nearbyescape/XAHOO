export type Horizon = '1m' | '5m' | '15m' | '1h' | '4h' | '1d';

export interface Fc {
  p: number; band68: number; band95: number; lo68: number; hi68: number; lo95: number; hi95: number;
  move_bp: number; tradable: boolean; layers: Record<string, number>; show: boolean; tier: number;
}
export interface Level {
  price: number; dist: number; dist_sig: number; score: number; strength: number; reactions: number;
  sources: string[]; reach: Record<string, number>;
}
export interface Levels { tol?: number; resistance: Level[]; support: Level[]; }
export interface Forecast { ts: number; ref: number; h: Record<string, Fc>; levels?: Levels; }
export interface Meta { sym: string; name: string; short: string; kind: 'coin' | 'metal'; digits: number; }
export interface Liq { ts: number; side: 'long' | 'short'; usd: number; price: number; }
export interface Market extends Meta {
  price: number | null; mark: number | null; dayAgo: number | null; forecast: Forecast | null;
  ribbon: [number, Record<string, number>][]; spark: number[];
  b5: number; s5: number; b60: number; s60: number;
  funding: number | null; oiChg1h: number | null; lsRatio: number | null; liqs: Liq[]; age: number | null;
  changed: Record<string, number>;       // horizon -> time of the last notable probability change (for the flash)
  liqPulse: number;
}
export interface Resolved { sym: string; h: string; p: number; outcome: number; ret: number; due: number; }
export interface Skill { tier: number; show: boolean; auc?: number; accuracy?: number; conf55_hit?: number | null; conf55_share?: number; n?: number; basis?: string; }
export interface ScoreH {
  n: number; hits: number; hit_rate: number | null; brier: number | null; conf_n: number; conf_hit_rate: number | null;
  bins: { label: string; n: number; predicted: number | null; actual: number | null }[];
}
