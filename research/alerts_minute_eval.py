"""Strong-alert accuracy test on the minute-by-minute out-of-sample forecasts (docs/RESEARCH.md section 15).

  python research/alerts_minute_eval.py             # validation (2024H2 → 2026H1); final exam stays hidden
  python research/alerts_minute_eval.py --final P3  # the final exam (2026-07 → 2026-10) for ONE chosen version

The alert rule is replayed as the live server runs it: checked every minute, one open alert per coin, scored on the
mark price after 15 minutes and 1 hour. Centring, the alert level and the META model use earlier periods only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

ROOT = Path(__file__).resolve().parents[1]
MIN, PRED = ROOT / "data/preds/minute", ROOT / "data/preds"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
HS = ["5m", "15m", "1h", "4h"]
PERIODS = [("2024H1", "2024-01-01", "2024-07-01"), ("2024H2", "2024-07-01", "2025-01-01"), ("2025H1", "2025-01-01", "2025-07-01"),
           ("2025H2", "2025-07-01", "2026-01-01"), ("2026H1", "2026-01-01", "2026-07-01"), ("FINAL", "2026-07-01", "2026-11-01")]
VALIDATION = ["2024H2", "2025H1", "2025H2", "2026H1"]
VERSIONS = ["BASE", "P3", "P5", "BTC", "BREADTH+", "BREADTH-", "TREND", "FUNDING", "META", "COMBO"]
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))  # noqa: E731
META_COLS = ["absz", "q_5m", "q_15m", "q_1h", "q_4h", "a_vol_1h_1d", "a_vol_1d_7d", "hour", "dow", "lead", "breadth",
             "fund", "d20", "r_er1h", "r_er4h"]


def panel() -> dict[str, pd.DataFrame]:
    return {s: pd.read_parquet(MIN / f"{s}.parquet").dropna(subset=[f"p_{h}" for h in HS]) for s in COINS}


def zscores(P: dict[str, pd.DataFrame], start: pd.Timestamp):
    """Centred z for every coin and minute: each timeframe's log-odds minus its median before `start`; alert level =
    95th percentile of |z| before `start` (pooled coins)."""
    allL = pd.concat([pd.DataFrame({h: lg(d[f"p_{h}"].to_numpy()) for h in HS}, index=d.index) for d in P.values()])
    prev = allL[allL.index < start]
    if not len(prev):                       # 2024H1, the warm-up period (never scored): its own data sets the centre
        prev = allL[allL.index < start + pd.Timedelta(days=182)]
    med = prev.median()
    zc_prev = (prev - med).mean(axis=1)
    level = float(np.quantile(np.abs(zc_prev), 0.95))
    out = {}
    for s, d in P.items():
        Lc = pd.DataFrame({h: lg(d[f"p_{h}"].to_numpy()) - med[h] for h in HS}, index=d.index)
        out[s] = pd.DataFrame({"z": Lc.mean(axis=1), "agree": np.abs(np.sign(Lc).sum(axis=1)) == 4}, index=d.index)
    return out, level


def simulate(cand: np.ndarray, side: np.ndarray, t: np.ndarray, y15: np.ndarray, y60: np.ndarray, sym: str) -> list[dict]:
    """One open alert per coin: fires at a candidate minute, blocks the next 60 minutes."""
    rows, busy_until = [], -1
    for i in np.flatnonzero(cand):
        if t[i] < busy_until:
            continue
        busy_until = t[i] + 3600
        rows.append({"sym": sym, "t": int(t[i]), "side": int(side[i]), "ok15": bool(y15[i] * side[i] > 0),
                     "ok60": bool(y60[i] * side[i] > 0), "i": int(i)})
    return rows


def run(P, period: tuple, versions: list[str], meta_train: pd.DataFrame | None) -> tuple[dict, pd.DataFrame]:
    name, a, b = period[0], pd.Timestamp(period[1], tz="UTC"), pd.Timestamp(period[2], tz="UTC")
    Z, level = zscores(P, a)
    idx = sorted(set().union(*[d.index[(d.index >= a) & (d.index < b)] for d in P.values()]))
    idx = pd.DatetimeIndex(idx)
    zall = pd.DataFrame({s: Z[s]["z"].reindex(idx) for s in COINS})
    breadth_up = ((zall >= level / 2)).sum(axis=1).to_numpy()
    breadth_dn = ((zall <= -level / 2)).sum(axis=1).to_numpy()
    res, base_alerts = {v: [] for v in versions}, []
    for s in COINS:
        d = P[s].reindex(idx)
        z = zall[s].to_numpy()
        ag = Z[s]["agree"].reindex(idx).fillna(False).to_numpy(bool)
        side = np.sign(z)
        cond = ag & (np.abs(z) >= level) & np.isfinite(z)
        # same-side run length for the persistence versions
        run_len = np.zeros(len(z), int)
        for i in range(len(z)):
            run_len[i] = (run_len[i - 1] + 1 if i and cond[i - 1] and side[i - 1] == side[i] else 1) if cond[i] else 0
        lead = zall["ETHUSDT" if s == "BTCUSDT" else "BTCUSDT"].to_numpy()
        breadth = np.where(side > 0, breadth_up, breadth_dn)
        d20, fz = d["r_d20"].to_numpy(), d["c_funding_z"].to_numpy()
        t = (idx.asi8 // 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[idx.unit]).astype(np.int64)
        y15, y60 = d["y_15m"].to_numpy(), d["y_1h"].to_numpy()
        ok_y = np.isfinite(y15) & np.isfinite(y60)
        ctx = pd.DataFrame({"absz": np.abs(z), "a_vol_1h_1d": d["a_vol_1h_1d"].to_numpy(), "a_vol_1d_7d": d["a_vol_1d_7d"].to_numpy(),
                            "hour": idx.hour.to_numpy(), "dow": idx.dayofweek.to_numpy(), "lead": lead * side,
                            "breadth": breadth, "fund": fz * side, "d20": d20 * side,
                            "r_er1h": d["r_er1h"].to_numpy(), "r_er4h": d["r_er4h"].to_numpy(),
                            **{f"q_{h}": np.where(side > 0, d[f"p_{h}"].to_numpy(), 1 - d[f"p_{h}"].to_numpy()) for h in HS}})
        filt = {
            "BASE": cond, "P3": cond & (run_len >= 3), "P5": cond & (run_len >= 5),
            "BTC": cond & (lead * side > 0), "BREADTH+": cond & (breadth >= 4), "BREADTH-": cond & (breadth <= 2),
            "TREND": cond & (d20 * side > 0), "FUNDING": cond & ~((side > 0) & (fz > 2)) & ~((side < 0) & (fz < -2)),
            "COMBO": cond & (run_len >= 3) & (lead * side > 0) & (d20 * side > 0),
        }
        if "META" in versions and meta_train is not None and len(meta_train) > 200:
            mm = LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=100, subsample=0.8,
                                subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, random_state=1, verbose=-1)
            mm.fit(meta_train[META_COLS], meta_train["ok60"].astype(int))
            thr = float(np.median(mm.predict_proba(meta_train[META_COLS])[:, 1]))
            score = np.zeros(len(z))
            k = np.flatnonzero(cond)
            if len(k):
                score[k] = mm.predict_proba(ctx.iloc[k][META_COLS])[:, 1]
            filt["META"] = cond & (score >= thr)
        for v in versions:
            if v not in filt:
                continue
            al = simulate(filt[v] & ok_y, side, t, y15, y60, s)
            for r in al:
                r["period"] = name
            res[v] += al
            if v == "BASE":
                for r in al:
                    base_alerts.append({**ctx.iloc[r["i"]].to_dict(), "ok60": r["ok60"], "period": name})
    days = (b - a).days if name != "FINAL" else (min(b, idx.max()) - a).days
    return {v: (pd.DataFrame(x), days) for v, x in res.items()}, pd.DataFrame(base_alerts)


def summarize(frames: list[tuple[pd.DataFrame, int]]) -> dict:
    df = pd.concat([f for f, _ in frames if len(f)]) if any(len(f) for f, _ in frames) else pd.DataFrame()
    days = sum(d for _, d in frames)
    if not len(df):
        return {"n": 0}
    return {"n": int(len(df)), "per_coin_day": round(len(df) / 8 / days, 2), "hit15": round(float(df["ok15"].mean()), 4),
            "hit60": round(float(df["ok60"].mean()), 4), "long_share": round(float((df["side"] > 0).mean()), 3),
            "long_hit60": round(float(df[df["side"] > 0]["ok60"].mean()), 4) if (df["side"] > 0).any() else None,
            "short_hit60": round(float(df[df["side"] < 0]["ok60"].mean()), 4) if (df["side"] < 0).any() else None}


def main():
    final = "--final" in sys.argv
    pick = sys.argv[sys.argv.index("--final") + 1] if final else None
    P = panel()
    versions = VERSIONS if not final else sorted({"BASE", pick})
    meta_hist = pd.DataFrame()
    per = {v: {} for v in versions}
    for period in PERIODS:
        name = period[0]
        if name == "FINAL" and not final:                                  # the final exam stays closed
            continue
        out, base_ctx = run(P, period, versions, meta_hist if len(meta_hist) else None)
        meta_hist = pd.concat([meta_hist, base_ctx])                        # META learns only from earlier periods
        if name == "2024H1" or (final and name != "FINAL"):
            continue
        for v in versions:
            if v in out:
                per[v][name] = out[v]
        print(name, " ".join(f"{v}:{summarize([per[v][name]]).get('hit60')}" for v in versions if name in per[v]), flush=True)
    report = {}
    keep = VALIDATION if not final else ["FINAL"]
    for v in versions:
        frames = [per[v][p] for p in keep if p in per[v]]
        report[v] = {"all": summarize(frames), "by_period": {p: summarize([per[v][p]]) for p in keep if p in per[v]}}
    if not final:
        b = report["BASE"]
        for v in versions:
            if v == "BASE":
                continue
            r = report[v]
            better = sum(1 for p in VALIDATION if p in r["by_period"] and r["by_period"][p].get("n")
                         and r["by_period"][p]["hit15"] > b["by_period"][p]["hit15"] and r["by_period"][p]["hit60"] > b["by_period"][p]["hit60"])
            a = r["all"]
            r["pass"] = {"d15": round((a.get("hit15", 0) - b["all"]["hit15"]) * 100, 2), "d60": round((a.get("hit60", 0) - b["all"]["hit60"]) * 100, 2),
                         "periods_better": better, "per_coin_day": a.get("per_coin_day")}
            r["passes"] = bool(r["pass"]["d15"] >= 1.0 and r["pass"]["d60"] >= 1.0 and better >= 3 and (a.get("per_coin_day") or 0) >= 0.5)
    for v in versions:
        a = report[v]["all"]
        print(f"{v:9} n={a.get('n'):6} per coin/day {a.get('per_coin_day')}  15m {a.get('hit15')}  1h {a.get('hit60')}  long {a.get('long_share')} "
              f"(L {a.get('long_hit60')} S {a.get('short_hit60')})  " + (json.dumps(report[v].get('pass')) + f" PASS={report[v].get('passes')}" if v != "BASE" and not final else "")
              + "  | " + " ".join(f"{p}:{x.get('hit15')}/{x.get('hit60')}({x.get('n')})" for p, x in report[v]["by_period"].items()), flush=True)
    (PRED / f"alerts_minute_{'final_' + pick if final else 'validation'}.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
