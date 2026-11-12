"""Telegram delivery (PLAN §4). Messages use HTML parse mode.

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. Follow-ups are sent as replies to
the original signal message so each trade reads as one thread.
"""
from __future__ import annotations

import os
from html import escape

import requests

API = "https://api.telegram.org/bot{token}/{method}"
NAMES = {"XAUUSD": "XAUUSD · Gold", "XAGUSD": "XAGUSD · Silver"}
SETUP_LABEL = {"ema12_pullback": "EMA12 pullback", "ema200_retest": "EMA200 retest",
               "range": "Range edge", "sweep": "Liquidity sweep"}
ARROW = {1: "▲", 0: "■", -1: "▼"}


def _px(x: float, sym: str) -> str:
    return f"{x:,.{2 if sym == 'XAUUSD' else 3}f}"


def format_signal(s: dict) -> str:
    sym, d = s["symbol"], s["dir"]
    side = "🟢 BUY" if d == 1 else "🔴 SELL"
    risk = s["risk"]
    lines = [
        f"<b>{side}  {NAMES.get(sym, sym)}</b>  ·  <b>{s['grade']}</b> ({s['score']:.0f})  ·  {s['tf']}",
        "<pre>",
        f"Entry  {_px(s['entry'], sym)}",
        f"SL     {_px(s['sl'], sym)}   (-{_px(risk, sym)})",
        f"TP1    {_px(s['tp1'], sym)}   {abs(s['tp1'] - s['entry']) / risk:.1f}R",
        f"TP2    {_px(s['tp2'], sym)}   {abs(s['tp2'] - s['entry']) / risk:.1f}R",
        f"TP3    {_px(s['tp3'], sym)}   {abs(s['tp3'] - s['entry']) / risk:.1f}R",
        "</pre>",
        f"Bias 4h{ARROW[int(s.get('4h_bias', 0))]} 1h{ARROW[int(s.get('1h_bias', 0))]}  ·  "
        f"Setup: {escape(SETUP_LABEL.get(s['setup'], s['setup']))}",
        f"Session: {s.get('session', '-')}{' (overlap)' if s.get('overlap') else ''}",
        "TP1 hit → move SL to entry (cost to cost). Risk ≤ 1%.",
        f"<code>{escape(str(s.get('id', '')))}</code>",
    ]
    return "\n".join(lines)


UPDATE_TEXT = {
    "TP1": "🎯 TP1 hit (+{r:.1f}R so far) — move SL to entry",
    "TP2": "🎯🎯 TP2 hit (+{r:.1f}R so far) — trail the rest",
    "TP3": "🏁 TP3 hit — trade closed +{r:.2f}R",
    "BE": "⚖️ Closed at entry after TP1 — +{r:.2f}R",
    "SL": "❌ Stop loss hit — {r:.2f}R",
    "EXPIRED": "⏱ Time limit — closed at market, {r:+.2f}R",
    "INVALIDATED": "🚫 Setup invalidated before entry",
}


def format_update(state: str, r: float = 0.0) -> str:
    return UPDATE_TEXT[state].format(r=r)


def format_daily(stats: dict, day: str) -> str:
    return (f"<b>📊 XAHOO daily — {day}</b>\n<pre>"
            f"Signals   {stats.get('signals', 0)}\n"
            f"TP1 hit   {stats.get('tp1_hit_rate', 0)}%\n"
            f"Win rate  {stats.get('win_rate', 0)}%\n"
            f"Net       {stats.get('total_r', 0):+} R</pre>")


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str, reply_to: int | None = None) -> int | None:
        """Send a message; returns its message_id (store it to thread follow-ups)."""
        if not self.enabled:
            return None
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        r = requests.post(API.format(token=self.token, method="sendMessage"), json=payload, timeout=15)
        r.raise_for_status()
        return r.json()["result"]["message_id"]
