"""Sweep-and-pullback trade signals: walk-through test of the rules pre-registered in docs/RESEARCH.md section 13.

  python research/sweep_eval.py              # validation report for all 12 versions (final exam stays hidden)
  python research/sweep_eval.py --final V4   # the final exam (2026-07 → 2026-10) for ONE chosen version

Signals on 5-minute candles; fills, stops and targets simulated minute by minute; costs and funding included.
Results in R (risk = entry-to-stop distance). Writes data/preds/sweep_{validation|final}.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BN, PRED = ROOT / "data/binance", ROOT / "data/preds"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
MIN = 60
MAKER, TAKER, SLIP = 0.0002, 0.0005, 0.0002
HOLD_MIN = 480
PERIODS = [("2022H1", "2022-01-01", "2022-07-01"), ("2022H2", "2022-07-01", "2023-01-01"),
           ("2023H1", "2023-01-01", "2023-07-01"), ("2023H2", "2023-07-01", "2024-01-01"),
           ("2024H1", "2024-01-01", "2024-07-01"), ("2024H2", "2024-07-01", "2025-01-01"),
           ("2025H1", "2025-01-01", "2025-07-01"), ("2025H2", "2025-07-01", "2026-01-01"),
           ("2026H1", "2026-01-01", "2026-07-01"), ("FINAL", "2026-07-01", "2026-11-01")]
VALIDATION = ["2024H1", "2024H2", "2025H1", "2025H2", "2026H1"]
VERSIONS = {   # filters, exit style, entry
    "V1": ((), "A", "limit"), "V2": (("oi",), "A", "limit"), "V3": (("delta",), "A", "limit"),
    "V4": (("oi", "delta"), "A", "limit"), "V5": (("oi", "delta", "trend"), "A", "limit"),
    "V6": (("oi", "delta"), "B", "limit"), "V7": (("oi", "delta"), "C", "limit"),
    "V8": (("oi", "delta"), "A", "market"), "V9": (("oi", "delta", "trend"), "B", "limit"),
    "V10": (("oi", "delta", "model"), "A", "limit"), "V11": ((), "B", "limit"), "V12": (("oi", "delta", "trend"), "C", "limit"),
}


def period_of(ts: int) -> str:
    t = pd.Timestamp(ts, unit="s", tz="UTC")
    for name, a, b in PERIODS:
        if pd.Timestamp(a, tz="UTC") <= t < pd.Timestamp(b, tz="UTC"):
            return name
    return "?"


# ------------------------------------------------------------------------------------------------ data
class Coin:
    def __init__(self, sym: str):
        self.sym = sym
        k = pd.read_parquet(BN / f"{sym}_1m.parquet", columns=["open", "high", "low", "close", "volume", "taker_buy_volume"])
        k = k[~k.index.duplicated()].sort_index()
        self.t1 = (k.index.asi8 // 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[k.index.unit]).astype(np.int64)
        self.h1, self.l1, self.c1 = k["high"].to_numpy(), k["low"].to_numpy(), k["close"].to_numpy()
        b = k.resample("5min", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                                  "volume": "sum", "taker_buy_volume": "sum"}).dropna()
        self.t5 = (b.index.asi8 // 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[b.index.unit]).astype(np.int64)
        self.h5, self.l5, self.c5 = b["high"].to_numpy(), b["low"].to_numpy(), b["close"].to_numpy()
        self.d5 = (2 * b["taker_buy_volume"] - b["volume"]).to_numpy()            # taker buy minus taker sell
        prev_c = np.r_[self.c5[0], self.c5[:-1]]
        tr = np.maximum(self.h5 - self.l5, np.maximum(np.abs(self.h5 - prev_c), np.abs(self.l5 - prev_c)))
        self.atr = pd.Series(tr).rolling(14, min_periods=14).mean().shift(1).to_numpy()   # known before each candle
        # previous UTC day and Asian session (00-08 UTC) extremes, per 5m candle
        day = b.index.floor("1D")
        dh, dl = b["high"].groupby(day).max(), b["low"].groupby(day).min()
        self.pdh = dh.shift(1).reindex(day).to_numpy(); self.pdl = dl.shift(1).reindex(day).to_numpy()
        asia = b[b.index.hour < 8]
        ah, al = asia["high"].groupby(asia.index.floor("1D")).max(), asia["low"].groupby(asia.index.floor("1D")).min()
        after8 = b.index.hour >= 8
        self.ash = np.where(after8, ah.reindex(day).to_numpy(), np.nan)
        self.asl = np.where(after8, al.reindex(day).to_numpy(), np.nan)
        # swing points: (usable from, formed at, price)
        self.piv = {"hi": [], "lo": []}
        for rule, n, keep in (("60min", 3, 72 * 3600), ("240min", 2, 7 * 86400)):
            r = k.resample(rule, label="left", closed="left").agg({"high": "max", "low": "min"}).dropna()
            tr_s = (r.index.asi8 // 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[r.index.unit]).astype(np.int64)
            step = int(pd.Timedelta(rule).total_seconds())
            H, L = r["high"].to_numpy(), r["low"].to_numpy()
            for j in range(n, len(r) - n):
                if H[j] == H[j - n:j + n + 1].max():
                    self.piv["hi"].append((tr_s[j] + (n + 1) * step, tr_s[j], H[j], keep))
                if L[j] == L[j - n:j + n + 1].min():
                    self.piv["lo"].append((tr_s[j] + (n + 1) * step, tr_s[j], L[j], keep))
        for s in self.piv:
            self.piv[s].sort()
        # open interest as published (5 minutes after its timestamp)
        m = pd.read_parquet(BN / f"{sym}_metrics.parquet", columns=["oi"])["oi"].dropna()
        m = m[~m.index.duplicated()].sort_index()
        self.oi_t = (m.index.asi8 // 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[m.index.unit]).astype(np.int64) + 300
        self.oi = m.to_numpy()
        f = pd.read_parquet(BN / f"{sym}_funding.parquet")["funding"]
        self.fund_t = (f.index.asi8 // 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[f.index.unit]).astype(np.int64)
        self.fund = f.to_numpy()
        h4 = k["close"].resample("240min", label="left", closed="left").last().dropna()
        self.h4_t = (h4.index.asi8 // 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[h4.index.unit]).astype(np.int64) + 4 * 3600   # usable at close
        self.h4_c, self.h4_e = h4.to_numpy(), h4.ewm(span=20, adjust=False).mean().to_numpy()
        try:
            p = pd.read_parquet(PRED / "ema_15m.parquet")
            p = p[p["sym"] == sym].sort_index()
            self.mp_t = (p.index.asi8 // 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[p.index.unit]).astype(np.int64) + 60
            self.mp = p["p"].to_numpy()
        except FileNotFoundError:
            self.mp_t, self.mp = np.array([], np.int64), np.array([])

    def asof(self, ts_arr, vals, t):
        i = np.searchsorted(ts_arr, t, side="right") - 1
        return vals[i] if i >= 0 else np.nan

    def levels(self, side: str, k: int) -> list[float]:
        """Liquidity below price (side 'lo', for longs) or above it ('hi', for shorts) known before candle k."""
        t = self.t5[k]
        out = [x for x in ((self.pdl[k], self.asl[k]) if side == "lo" else (self.pdh[k], self.ash[k])) if x == x]
        P = self.piv[side]
        j = self._pp[side]
        while j < len(P) and P[j][0] <= t:
            self._act[side].append(P[j]); j += 1
        self._pp[side] = j
        self._act[side] = [x for x in self._act[side] if x[1] >= t - x[3]]
        out += [x[2] for x in self._act[side]]
        return out


# ------------------------------------------------------------------------------------------------ setups
def setups(cn: Coin) -> list[dict]:
    """Every sweep + change of direction, both sides, with its filter flags (decided at the signal candle)."""
    cn._pp, cn._act = {"hi": 0, "lo": 0}, {"hi": [], "lo": []}
    n = len(cn.t5)
    lo12 = pd.Series(cn.l5).rolling(12).min().shift(1).to_numpy()
    hi12 = pd.Series(cn.h5).rolling(12).max().shift(1).to_numpy()
    out, skip = [], {1: -1, -1: -1}
    for k in range(20, n - 20):
        lv_lo, lv_hi = cn.levels("lo", k), cn.levels("hi", k)
        a = cn.atr[k]
        if a != a:
            continue
        for side in (1, -1):
            if k <= skip[side]:
                continue
            if side == 1:
                if not cn.l5[k] < lo12[k]:
                    continue
                swept = [L for L in lv_lo if cn.l5[k] <= L - 0.1 * a and lo12[k] > L]
                if not swept:
                    continue
                L = min(swept)
                c = next((j for j in range(k, min(k + 3, n)) if cn.c5[j] > L), None)
            else:
                if not cn.h5[k] > hi12[k]:
                    continue
                swept = [L for L in lv_hi if cn.h5[k] >= L + 0.1 * a and hi12[k] < L]
                if not swept:
                    continue
                L = max(swept)
                c = next((j for j in range(k, min(k + 3, n)) if cn.c5[j] < L), None)
            if c is None:
                continue
            X = cn.l5[k:c + 1].min() if side == 1 else cn.h5[k:c + 1].max()
            H = cn.h5[k - 6:k].max() if side == 1 else cn.l5[k - 6:k].min()
            m = next((j for j in range(c + 1, min(c + 7, n)) if (cn.c5[j] > H if side == 1 else cn.c5[j] < H)), None)
            if m is None:
                continue
            T = cn.h5[k:m + 1].max() if side == 1 else cn.l5[k:m + 1].min()
            t_sig = int(cn.t5[m] + 300)                                      # close of the change-of-direction candle
            oi0, oi1 = cn.asof(cn.oi_t, cn.oi, cn.t5[k] - 1800), cn.asof(cn.oi_t, cn.oi, t_sig)
            d_sweep, d_after = cn.d5[k:c + 1].sum(), cn.d5[c + 1:m + 1].sum()
            h4c, h4e = cn.asof(cn.h4_t, cn.h4_c, t_sig), cn.asof(cn.h4_t, cn.h4_e, t_sig)
            mp = cn.asof(cn.mp_t, cn.mp, t_sig) if len(cn.mp) else np.nan
            opp = [x for x in (lv_hi if side == 1 else lv_lo)]
            out.append({"sym": cn.sym, "side": side, "k": k, "m": m, "t_sig": t_sig, "level": L, "X": X, "T": T, "atr": a,
                        "close_m": cn.c5[m], "opp": opp,
                        "oi": bool(oi0 == oi0 and oi1 == oi1 and oi0 > 0 and oi1 / oi0 - 1 <= -0.002),
                        "delta": bool((d_sweep < 0 and d_after > 0) if side == 1 else (d_sweep > 0 and d_after < 0)),
                        "trend": bool(h4c == h4c and ((h4c > h4e) if side == 1 else (h4c < h4e))),
                        "model": None if mp != mp else bool((mp > 0.5) if side == 1 else (mp < 0.5))})
            skip[side] = m
    return out


# ------------------------------------------------------------------------------------------------ trades
def run_exit(cn: Coin, side: int, f: int, E: float, S: float, style: str, tp_c: float | None, entry_fee: float) -> dict:
    """From fill minute index f: stop / targets / time limit. Returns net R and details."""
    R = abs(E - S)
    end = min(f + HOLD_MIN, len(cn.t1) - 1)
    hi, lo, cl = cn.h1[f:end + 1], cn.l1[f:end + 1], cn.c1[f:end + 1]
    up = side == 1

    def stop_hit(stop, frm):
        x = (lo[frm:] <= stop) if up else (hi[frm:] >= stop)
        return frm + int(np.argmax(x)) if x.any() else None

    def tgt_hit(tp, frm):
        x = (hi[frm:] >= tp) if up else (lo[frm:] <= tp)
        return frm + int(np.argmax(x)) if x.any() else None

    def leg(frm, stop, tp):
        """First of stop / target from offset frm (same minute -> stop). Returns (kind, offset, price)."""
        s_i, t_i = stop_hit(stop, frm), tgt_hit(tp, frm)
        if s_i is not None and (t_i is None or s_i <= t_i):
            return "stop", s_i, stop
        if t_i is not None:
            return "tp", t_i, tp
        return "time", len(cl) - 1, cl[-1]

    cost = lambda kind, px: (MAKER if kind == "tp" else TAKER + SLIP if kind == "stop" else TAKER) * px / R  # noqa: E731
    gain = lambda px: (px - E) * side / R  # noqa: E731
    if ((lo[0] <= S) if up else (hi[0] >= S)):                              # stopped in the fill minute
        parts = [(1.0, "stop", 0, S)]
    elif style == "B":
        kind, i1, px = leg(1, S, E + side * R)
        if kind != "tp":
            parts = [(1.0, kind, i1, px)]
        else:
            k2, i2, px2 = leg(i1 + 1, E, E + side * 2 * R) if i1 + 1 < len(cl) else ("time", i1, cl[-1])
            parts = [(0.5, "tp", i1, px), (0.5, k2, i2, px2)]
    else:
        tp = E + side * 2 * R if style == "A" else tp_c
        parts = [(1.0, *leg(1, S, tp))]
    net, last = 0.0, 0
    for w, kind, i, px in parts:
        net += w * (gain(px) - cost(kind, px))
        last = max(last, i)
    net -= entry_fee * E / R
    t_in, t_out = cn.t1[f], cn.t1[f + last]
    a, b = np.searchsorted(cn.fund_t, t_in, side="right"), np.searchsorted(cn.fund_t, t_out, side="right")
    net -= side * cn.fund[a:b].sum() * E / R                                 # longs pay positive funding
    return {"r": float(net), "exit": parts[-1][1], "t_in": int(t_in), "t_out": int(t_out), "hold_min": int(last)}


def trade(cn: Coin, s: dict, style: str, entry: str) -> dict | None:
    side, X, T, a = s["side"], s["X"], s["T"], s["atr"]
    S = X - side * 0.1 * a
    t0 = s["t_sig"]
    f0 = np.searchsorted(cn.t1, t0)
    if f0 >= len(cn.t1) - 10:
        return None
    if entry == "market":
        E, f, fee = s["close_m"], f0, TAKER
    else:
        E = X + 0.5 * (T - X)
        R = abs(E - S)
        f1 = np.searchsorted(cn.t1, t0 + 3600)
        hi, lo = cn.h1[f0:f1], cn.l1[f0:f1]
        fill = (lo <= E) if side == 1 else (hi >= E)
        miss = (hi >= E + R) if side == 1 else (lo <= E - R)
        fi = int(np.argmax(fill)) if fill.any() else None
        mi = int(np.argmax(miss)) if miss.any() else None
        if fi is None or (mi is not None and mi <= fi):
            return None
        f, fee = f0 + fi, MAKER
    R = abs(E - S)
    if not (0.0025 <= R / E <= 0.03) or (S - E) * side >= 0:
        return None
    tp_c = None
    if style == "C":
        cands = sorted((L for L in s["opp"] if (L - E) * side >= 1.5 * R), key=lambda L: abs(L - E))
        tp_c = cands[0] if cands else E + side * 2 * R
    res = run_exit(cn, side, f, E, S, style, tp_c, fee)
    res.update(sym=cn.sym, side=side, risk_pct=R / E, tp_r=(abs(tp_c - E) / R if tp_c else (2.0 if style != "B" else None)))
    return res


def baseline(cn: Coin, tr: dict, style: str, rng: np.random.Generator) -> float | None:
    """Same coin, side, stop distance and exits, entered (limit fee) at a random minute of the same month."""
    t = pd.Timestamp(tr["t_in"], unit="s", tz="UTC")
    a, b = t.to_period("M").start_time.tz_localize("UTC"), t.to_period("M").end_time.tz_localize("UTC")
    i0, i1 = np.searchsorted(cn.t1, a.timestamp()), np.searchsorted(cn.t1, b.timestamp()) - HOLD_MIN - 1
    if i1 <= i0:
        return None
    f = int(rng.integers(i0, i1))
    E = cn.c1[f]
    side = tr["side"]
    S = E * (1 - side * tr["risk_pct"])
    R = abs(E - S)
    tp_c = E + side * tr["tp_r"] * R if style == "C" and tr["tp_r"] else None
    return run_exit(cn, side, f + 1, E, S, style, tp_c, MAKER)["r"]


# ------------------------------------------------------------------------------------------------ report
def stats(df: pd.DataFrame) -> dict:
    if not len(df):
        return {"n": 0}
    r = df.sort_values("t_in")["r"].to_numpy()
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    streak = run = 0
    for x in r:
        run = run + 1 if x <= 0 else 0
        streak = max(streak, run)
    pos, neg = r[r > 0].sum(), -r[r <= 0].sum()
    return {"n": int(len(r)), "win": round(float((r > 0).mean()), 3), "avg_r": round(float(r.mean()), 4),
            "total_r": round(float(r.sum()), 1), "pf": round(float(pos / neg), 3) if neg > 0 else None,
            "max_dd_r": round(dd, 1), "losing_streak": int(streak)}


def main():
    final = "--final" in sys.argv
    pick = sys.argv[sys.argv.index("--final") + 1] if final else None
    coins = {s: Coin(s) for s in COINS}
    all_setups = {}
    for s, cn in coins.items():
        all_setups[s] = setups(cn)
        print(f"{s}: {len(all_setups[s])} sweep + change-of-direction setups", flush=True)
    rng = np.random.default_rng(7)
    report = {}
    for v, (filt, style, entry) in VERSIONS.items():
        if final and v != pick:
            continue
        rows = []
        for s, cn in coins.items():
            for st in all_setups[s]:
                if any((st[f] is not True) for f in filt):
                    continue
                tr = trade(cn, st, style, entry)
                if tr is None:
                    continue
                tr["period"] = period_of(tr["t_in"])
                if (tr["period"] == "FINAL") != final:
                    continue
                if "model" in filt and tr["period"] < "2024":
                    continue
                b = [baseline(cn, tr, style, rng) for _ in range(5)]
                b = [x for x in b if x is not None]
                tr["base_r"] = float(np.mean(b)) if b else np.nan
                rows.append(tr)
        df = pd.DataFrame(rows)
        if not len(df):
            report[v] = {"n": 0}
            continue
        val = df[df["period"].isin(VALIDATION)] if not final else df
        by_p = {p: stats(g) for p, g in df.groupby("period")}
        rep = {"filters": list(filt), "exit": style, "entry": entry, "all": stats(val), "baseline_avg_r": round(float(val["base_r"].mean()), 4),
               "by_period": {p: {"n": x["n"], "avg_r": x.get("avg_r"), "win": x.get("win")} for p, x in by_p.items()},
               "long": stats(val[val["side"] == 1]), "short": stats(val[val["side"] == -1]),
               "by_coin": {s: stats(g)["avg_r"] for s, g in val.groupby("sym")},
               "exits": val["exit"].value_counts().to_dict(), "avg_hold_min": round(float(val["hold_min"].mean()), 1),
               "avg_risk_pct": round(float(val["risk_pct"].mean() * 100), 3)}
        if not final:
            pos = sum(1 for p in VALIDATION if by_p.get(p, {}).get("avg_r", -1) > 0)
            a = rep["all"]
            rep["pass"] = {"periods_positive": pos, "pf_ok": bool(a.get("pf") and a["pf"] >= 1.2), "n_ok": a["n"] >= 200,
                           "beats_baseline": bool(a.get("avg_r", -9) > rep["baseline_avg_r"])}
            rep["passes"] = pos >= 4 and all(rep["pass"][x] for x in ("pf_ok", "n_ok", "beats_baseline"))
        report[v] = rep
        a = rep["all"]
        print(f"{v:4} {style} {entry:6} {'+'.join(filt) or '-':18} n={a['n']:5d} win {a.get('win', 0)*100:5.1f}% avgR {a.get('avg_r', 0):+.3f} "
              f"PF {a.get('pf')} base {rep['baseline_avg_r']:+.3f} dd {a.get('max_dd_r')}R streak {a.get('losing_streak')} | "
              + " ".join(f"{p}:{by_p[p]['avg_r']:+.2f}({by_p[p]['n']})" for p in sorted(by_p)) + ("" if final else f" | PASS={rep['passes']}"), flush=True)
    (PRED / f"sweep_{'final_' + pick if final else 'validation'}.json").write_text(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
