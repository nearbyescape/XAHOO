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
               "range": "Range edge", "sweep": "Liquidity sweep", "impulse_pullback": "Impulse → EMA12 pullback → breakdown",
               "liquidity_pressure": "Liquidity sweep + pressure"}
ARROW = {1: "▲", 0: "■", -1: "▼"}


def _px(x: float, sym: str) -> str:
    return f"{x:,.{2 if sym == 'XAUUSD' else 3}f}"


def format_signal(s: dict) -> str:
    sym, d = s["symbol"], s["dir"]
    side = "🟢 BUY" if d == 1 else "🔴 SELL"
    risk = s["risk"]
    if s.get("add_price"):
        levels = [
            f"Entry  {_px(s['entry'], sym)}   lot 1 now",
            f"Add    {_px(s['add_price'], sym)}   lot 2 (limit, EMA12)",
            f"SL     {_px(s['sl'], sym)}   (-{_px(risk, sym)} per lot)",
            f"TP     {_px(s['tp1'], sym)}   {abs(s['tp1'] - s['entry']) / risk:.1f}R from entry",
        ]
        size = "0.25% (HALF SIZE — drawdown rule)" if s.get("risk_mult", 1.0) < 1 else "0.5%"
        manage = f"At +1R move SL to average entry. Size: {size} risk per lot."
    else:
        levels = [
            f"Entry  {_px(s['entry'], sym)}",
            f"SL     {_px(s['sl'], sym)}   (-{_px(risk, sym)})",
            f"TP1    {_px(s['tp1'], sym)}   {abs(s['tp1'] - s['entry']) / risk:.1f}R",
            f"TP2    {_px(s['tp2'], sym)}   {abs(s['tp2'] - s['entry']) / risk:.1f}R",
            f"TP3    {_px(s['tp3'], sym)}   {abs(s['tp3'] - s['entry']) / risk:.1f}R",
        ]
        manage = "TP1 hit → move SL to entry (cost to cost). Risk ≤ 1%."
    lines = [
        f"<b>{side}  {NAMES.get(sym, sym)}</b>  ·  <b>{s['grade']}</b> ({s['score']:.0f})  ·  {s['tf']}",
        "<pre>", *levels, "</pre>",
        f"Bias 4h{ARROW[int(s.get('4h_bias', 0))]} 1h{ARROW[int(s.get('1h_bias', 0))]}  ·  "
        f"Setup: {escape(SETUP_LABEL.get(s['setup'], s['setup']))}",
        f"Session: {s.get('session', '-')}{' (overlap)' if s.get('overlap') else ''}",
        *(["📰 <b>NEWS IMPULSE</b> — historically the strongest signals (no size increase until proven live)"]
          if s.get("news_impulse") else []),
        manage,
        f"<code>{escape(str(s.get('id', '')))}</code>",
    ]
    return "\n".join(lines)


UPDATE_TEXT = {
    "ADDED": "➕ Lot 2 filled at the add zone{px}",
    "RISK_FREE": "🛡 +1R reached — move SL to average entry (trade is risk-free)",
    "TP": "🏁 Target hit — {r:+.2f}R",
    "TRAIL": "🏁 Trailing stop hit in profit — {r:+.2f}R",
    "TIME": "⏱ Time limit — closed at market, {r:+.2f}R",
    "TP1": "🎯 TP1 hit (+{r:.1f}R so far) — move SL to entry",
    "TP2": "🎯🎯 TP2 hit (+{r:.1f}R so far) — trail the rest",
    "TP3": "🏁 TP3 hit — trade closed +{r:.2f}R",
    "BE": "⚖️ Closed at the protected stop — {r:+.2f}R",
    "SL": "❌ Stop loss hit — {r:.2f}R",
    "EXPIRED": "⏱ Time limit — closed at market, {r:+.2f}R",
    "INVALIDATED": "🚫 Setup invalidated before entry",
    "CANCELLED": "✖️ Setup cancelled — no breakdown in time. No trade.",
}


def format_prealert(w: dict) -> str:
    sym, d = w["symbol"], w["dir"]
    side = "SELL" if d == -1 else "BUY"
    beyond = "below" if d == -1 else "above"
    return "\n".join([
        f"⏳ <b>GET READY — {side} {NAMES.get(sym, sym)}</b> setup forming (5m)",
        "<pre>",
        f"Impulse  {w['impulse_atr']:.1f}× ATR done, pullback reached EMA12 ({_px(w['ema12'], sym)})",
        f"Trigger  5m candle CLOSES {beyond} {_px(w['trigger'], sym)}  (≤ {w['bars_left'] * 5} min)",
        f"Stop ≈   {_px(w['sl_est'], sym)}",
        "</pre>",
        "Not a trade yet — about 1 in 5 of these becomes a signal.",
    ])


def format_update(state: str, r: float = 0.0, price: float | None = None) -> str:
    return UPDATE_TEXT[state].format(r=r, px=f" @ {price:,.2f}" if price else "")


def format_daily(stats: dict, day: str) -> str:
    return (f"<b>📊 XAHOO daily — {day}</b>\n<pre>"
            f"Signals   {stats.get('signals', 0)}\n"
            f"TP1 hit   {stats.get('tp1_hit_rate', 0)}%\n"
            f"Win rate  {stats.get('win_rate', 0)}%\n"
            f"Net       {stats.get('total_r', 0):+} R</pre>")


class TelegramError(RuntimeError):
    """Telegram API failure. The message never contains the bot token (it is part of the request URL)."""


def _call(token: str, method: str, payload: dict | None = None, timeout: float = 15) -> dict:
    try:
        r = requests.post(API.format(token=token, method=method), json=payload or {}, timeout=timeout)
    except requests.RequestException as e:
        raise TelegramError(f"{method}: network error ({type(e).__name__})") from None
    try:
        data = r.json()
    except ValueError:
        raise TelegramError(f"{method}: HTTP {r.status_code}") from None
    if not data.get("ok"):
        raise TelegramError(f"{method}: {data.get('error_code', r.status_code)} {data.get('description', '')}".strip())
    return data["result"]


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
                   "link_preview_options": {"is_disabled": True}}
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        return _call(self.token, "sendMessage", payload)["message_id"]


def find_chats(updates: list[dict]) -> dict[int, dict]:
    """Chats the bot has seen (private chat, group or channel) from getUpdates results."""
    chats = {}
    for u in updates:
        for key in ("message", "channel_post", "my_chat_member", "edited_message", "edited_channel_post"):
            chat = (u.get(key) or {}).get("chat")
            if chat:
                name = chat.get("title") or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
                chats[chat["id"]] = {"id": chat["id"], "type": chat.get("type"), "name": name or chat.get("username", "")}
    return chats


def setup() -> int:
    """`python -m xahoo.telegram`: check the bot token, list chats the bot can see (with their IDs), and send a test
    message if TELEGRAM_CHAT_ID is set."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN is empty. Create a bot with @BotFather and put the token in .env")
        return 1
    try:
        me = _call(token, "getMe")
        print(f"bot ok: @{me['username']} ({me.get('first_name', '')})")
        chats = find_chats(_call(token, "getUpdates", {"limit": 100, "timeout": 0}))
    except TelegramError as e:
        print(f"Telegram error: {e}")
        return 1
    if chats:
        print("chats the bot can see (use the id as TELEGRAM_CHAT_ID):")
        for c in chats.values():
            print(f"  {c['id']:>16}  {c['type']:<10} {c['name']}")
    else:
        print("no chats yet: add the bot to your channel as admin (or send /start to the bot), post one message, "
              "then run this again")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if chat_id:
        try:
            Telegram(token, chat_id).send("✅ <b>XAHOO connected</b>\nSignals, pre-alerts and trade updates will arrive here.")
            print(f"test message sent to {chat_id}")
        except TelegramError as e:
            print(f"could not send to {chat_id}: {e}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(setup())
