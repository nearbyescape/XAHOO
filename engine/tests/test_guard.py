import pandas as pd

from xahoo.live.guard import GuardConfig, evaluate

NOW = pd.Timestamp("2026-11-13 12:00", tz="UTC")
DAY = int(NOW.normalize().timestamp())


def trades(rs, start=DAY - 86400 * 30, step=3600):
    return [{"exit_time": start + i * step, "r": r} for i, r in enumerate(rs)]


def test_active_when_fine():
    g = evaluate(trades([2, -1, 2, -1, 2]), NOW)
    assert g["state"] == "ACTIVE" and g["risk_mult"] == 1.0


def test_day_stop_on_daily_loss():
    g = evaluate(trades([-1.0, -1.2], start=DAY + 60), NOW)
    assert g["state"] == "DAY_STOP" and g["risk_mult"] == 0.0


def test_half_size_then_pause_on_drawdown():
    assert evaluate(trades([5] + [-1] * 11), NOW)["state"] == "HALF"
    assert evaluate(trades([5] + [-1] * 21), NOW)["state"] == "PAUSED"


def test_edge_check_needs_enough_trades():
    bad = [-0.6] * 29
    assert evaluate(trades(bad), NOW, GuardConfig(pause_dd_r=100, half_dd_r=100))["state"] == "ACTIVE"
    g = evaluate(trades(bad + [-0.6]), NOW, GuardConfig(pause_dd_r=100, half_dd_r=100))
    assert g["state"] == "PAUSED" and "edge floor" in g["reasons"][0]


def test_resume_baseline_and_manual_pause():
    rs = trades([5] + [-1] * 21)
    assert evaluate(rs, NOW, baseline_ts=rs[-1]["exit_time"] + 1)["state"] == "ACTIVE"
    assert evaluate([], NOW, manual_pause="owner paused")["state"] == "PAUSED"
