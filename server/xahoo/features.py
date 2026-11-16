"""Feature pipeline shared by research and the live engine.

Input: 1-minute bars (index = bar open time, UTC). Row t describes the market at the CLOSE of bar t, using only
data up to that moment, so the same function serves backtests (all rows) and live use (last row).
All features are scale-free (returns in volatility units, ratios, z-scores) so one model can serve every market.

Layers (prefix):
  a_  trend / regime        price vs its own history, volatility state, time of day
  b_  order flow            taker buy vs sell volume, activity, candle shape
  c_  positioning           open interest, long/short ratios, funding
  d_  leader                the leading market (BTC for coins, ETH for BTC, gold<->silver)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
LEADER = {"BTCUSDT": "ETHUSDT", "XAUUSDT": "XAGUSDT", "XAGUSDT": "XAUUSDT"}   # everything else follows BTC
EPS = 1e-12


def leader_of(sym: str) -> str:
    return LEADER.get(sym, "BTCUSDT")


def _roll_sum(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(1, n // 2)).sum()


def _z(s: pd.Series, n: int) -> pd.Series:
    m = s.rolling(n, min_periods=n // 4).mean()
    sd = s.rolling(n, min_periods=n // 4).std()
    return (s - m) / (sd + EPS)


def build(k: pd.DataFrame, metrics: pd.DataFrame | None = None, funding: pd.DataFrame | None = None,
          leader: pd.DataFrame | None = None) -> pd.DataFrame:
    """k / leader: columns open, high, low, close, volume, count, taker_buy_volume.
    metrics: oi, top_ls_acct, top_ls_pos, ls_acct, taker_ratio (5-minute snapshots, index = snapshot time).
    funding: column funding (index = settlement time)."""
    idx = k.index
    c, h, l, v = k["close"], k["high"], k["low"], k["volume"]
    lc = np.log(c)
    r1 = lc.diff()
    sig60 = r1.rolling(60, min_periods=30).std()
    sig1d = r1.rolling(1440, min_periods=360).std()
    sig7d = r1.rolling(10080, min_periods=1440).std()
    f = {}

    # ---------------------------------------------------------------- a_: trend / regime
    for n in (5, 15, 60, 240, 1440, 4320, 10080):
        f[f"a_ret{n}"] = (lc - lc.shift(n)) / (sig1d * np.sqrt(n) + EPS)
    for n in (60, 240, 1440, 10080):
        f[f"a_sma{n}"] = (c / c.rolling(n, min_periods=n // 2).mean() - 1) / (sig1d * np.sqrt(n) + EPS)
    for n in (240, 1440, 10080):
        hi, lo = h.rolling(n, min_periods=n // 2).max(), l.rolling(n, min_periods=n // 2).min()
        f[f"a_pos{n}"] = (c - lo) / (hi - lo + EPS)
    f["a_vol_1h_1d"] = sig60 / (sig1d + EPS)
    f["a_vol_1d_7d"] = sig1d / (sig7d + EPS)
    minute = idx.hour * 60 + idx.minute
    f["a_tod_sin"] = pd.Series(np.sin(2 * np.pi * minute / 1440), index=idx)
    f["a_tod_cos"] = pd.Series(np.cos(2 * np.pi * minute / 1440), index=idx)
    f["a_dow"] = pd.Series(idx.dayofweek.astype("float32"), index=idx)

    # ---------------------------------------------------------------- b_: order flow
    tb = k["taker_buy_volume"]
    signed = 2 * tb - v                                   # taker buy minus taker sell volume
    for n in (1, 5, 15, 60, 240):
        f[f"b_imb{n}"] = _roll_sum(signed, n) / (_roll_sum(v, n) + EPS)
    vavg = v.rolling(1440, min_periods=360).mean()
    for n in (1, 5, 60):
        f[f"b_vol{n}"] = _roll_sum(v, n) / (vavg * n + EPS)
    cnt = k["count"]
    f["b_cnt5"] = _roll_sum(cnt, 5) / (cnt.rolling(1440, min_periods=360).mean() * 5 + EPS)
    tsize = v / (cnt + EPS)
    f["b_tsize5"] = tsize.rolling(5, min_periods=1).mean() / (tsize.rolling(1440, min_periods=360).mean() + EPS)
    f["b_ret1"] = r1 / (sig60 + EPS)
    f["b_clv1"] = (c - l) / (h - l + EPS) * 2 - 1
    h5, l5 = h.rolling(5, min_periods=1).max(), l.rolling(5, min_periods=1).min()
    f["b_clv5"] = (c - l5) / (h5 - l5 + EPS) * 2 - 1
    f["b_range1"] = np.log(h / l) / (sig60 + EPS)
    # flow that price has not followed (absorption): imbalance minus the return it "should" have produced
    f["b_div15"] = f["b_imb15"] - np.tanh(f["a_ret15"])
    f["b_div60"] = f["b_imb60"] - np.tanh(f["a_ret60"])

    # ---------------------------------------------------------------- c_: positioning
    if metrics is not None and len(metrics):
        # treat each 5-minute snapshot as published 5 minutes after its timestamp (conservative)
        m = metrics.shift(freq="5min").reindex(idx, method="ffill", limit=30)
        loi = np.log(m["oi"].where(m["oi"] > 0))
        for n, name in ((5, "5m"), (60, "1h"), (240, "4h"), (1440, "1d")):
            f[f"c_oi_{name}"] = loi - loi.shift(n)
        for col in ("ls_acct", "top_ls_acct", "top_ls_pos"):
            x = np.log(m[col].where(m[col] > 0))
            f[f"c_{col}_z"] = _z(x, 10080)
            f[f"c_{col}_ch1h"] = x - x.shift(60)
        tr = np.log(m["taker_ratio"].where(m["taker_ratio"] > 0))
        f["c_taker"] = tr
        f["c_taker_1h"] = tr.rolling(60, min_periods=10).mean()
        # price up + OI up = new longs; price up + OI down = short covering (and mirrors)
        f["c_oi_x_ret_1h"] = f["c_oi_1h"] * np.sign(f["a_ret60"])
        f["c_oi_x_ret_4h"] = f["c_oi_4h"] * np.sign(f["a_ret240"])
    if funding is not None and len(funding):
        fr = funding["funding"].reindex(idx, method="ffill")
        f["c_funding"] = fr * 1e4
        fz = _z(funding["funding"], 30)
        f["c_funding_z"] = fz.reindex(idx, method="ffill")

    # ---------------------------------------------------------------- d_: leader
    if leader is not None and len(leader):
        L = leader.reindex(idx, method="ffill", limit=5)
        llc = np.log(L["close"])
        lr1 = llc.diff()
        lsig60 = lr1.rolling(60, min_periods=30).std()
        lsig1d = lr1.rolling(1440, min_periods=360).std()
        for n in (1, 5, 15, 60):
            f[f"d_ret{n}"] = (llc - llc.shift(n)) / ((lsig60 if n == 1 else lsig1d * np.sqrt(n)) + EPS)
        lsigned = 2 * L["taker_buy_volume"] - L["volume"]
        for n in (1, 5):
            f[f"d_imb{n}"] = _roll_sum(lsigned, n) / (_roll_sum(L["volume"], n) + EPS)
        f["d_lag1"] = f["d_ret1"] - f["b_ret1"]            # leader moved, this market has not (yet)
        f["d_lag5"] = f["d_ret5"] - f["a_ret5"]
        f["d_rel60"] = f["a_ret60"] - f["d_ret60"]
        f["d_rel1d"] = f["a_ret1440"] - (llc - llc.shift(1440)) / (lsig1d * np.sqrt(1440) + EPS)
        f["d_corr1d"] = r1.rolling(1440, min_periods=360).corr(lr1)

    out = pd.DataFrame(f, index=idx).replace([np.inf, -np.inf], np.nan).astype("float32")
    return out.clip(-50, 50)


def feature_groups(cols) -> dict[str, list[str]]:
    return {g: [c for c in cols if c.startswith(g + "_")] for g in ("a", "b", "c", "d")}


# -------------------------------------------------------------------- optional layers (research 2026-11-16)
def extra(k: pd.DataFrame, spot: pd.DataFrame | None = None, prem: pd.DataFrame | None = None) -> pd.DataFrame:
    """f_  spot market: Binance spot taker flow, spot share of volume, spot-futures basis, who moved first
       g_  futures premium index (how far futures trade above / below the index)
    k: futures 1m bars; spot: spot 1m bars (same columns); prem: premium index 1m klines (close)."""
    idx = k.index
    f = {}
    lc = np.log(k["close"])
    r1 = lc.diff()
    sig1d = r1.rolling(1440, min_periods=360).std()
    if spot is not None and len(spot):
        S = spot.reindex(idx, method="ffill", limit=2)
        sv = S["volume"].where(S["volume"] > 0, 0.0)
        ssigned = 2 * S["taker_buy_volume"] - sv
        for n in (1, 5, 15, 60):
            f[f"f_imb{n}"] = _roll_sum(ssigned, n) / (_roll_sum(sv, n) + EPS)
        perp_usd = k["volume"] * k["close"]
        spot_usd = sv * S["close"]
        share = _roll_sum(spot_usd, 60) / (_roll_sum(spot_usd, 60) + _roll_sum(perp_usd, 60) + EPS)
        f["f_share60"] = share / (share.rolling(1440, min_periods=360).mean() + EPS)
        basis = (lc - np.log(S["close"])) * 1e4
        f["f_basis"] = basis
        f["f_basis_z"] = _z(basis, 1440)
        f["f_basis_ch5"] = basis - basis.shift(5)
        f["f_basis_ch60"] = basis - basis.shift(60)
        slc = np.log(S["close"])
        for n in (1, 5):
            f[f"f_lead{n}"] = ((slc - slc.shift(n)) - (lc - lc.shift(n))) / (sig1d * np.sqrt(n) + EPS)
        pimb15 = _roll_sum(2 * k["taker_buy_volume"] - k["volume"], 15) / (_roll_sum(k["volume"], 15) + EPS)
        f["f_imbdiff15"] = f["f_imb15"] - pimb15
    if prem is not None and len(prem):
        P = prem["close"].reindex(idx, method="ffill", limit=2) * 1e4
        f["g_prem"] = P
        f["g_prem_z"] = _z(P, 1440)
        f["g_prem_ch15"] = P - P.shift(15)
        f["g_prem_ch60"] = P - P.shift(60)
    out = pd.DataFrame(f, index=idx).replace([np.inf, -np.inf], np.nan).astype("float32")
    return out.clip(-50, 50) if len(out.columns) else out
