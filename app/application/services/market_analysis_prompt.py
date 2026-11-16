"""Compone lo que recibe el modelo del robo-advisor (el bot principal) en el
hilo de alertas: instrucciones de analista estratega y los datos. Dos tareas:

- `ALERT`: reaccion a un evento de alertas (salto >= ±5% del trail).
- `REVIEW`: revision periodica (cada 30 min) de los instrumentos que se han
  movido de forma notable desde la revision anterior.

La parte clave para "leer el indice" es la foto del mercado: el modelo ve
los movimientos junto a la variacion del dia de los ETF de indices (SPY,
QQQ...), del resto de valores y del cambio/cripto, y asi puede distinguir un
movimiento propio de la empresa de uno arrastrado por todo el mercado.

La causa sale de los titulares de las ultimas 24 h (NewsProvider, siempre) y,
si el modelo tiene cuota, tambien de su propia busqueda web.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Sequence

from domain.value_objects.chat_turn import ChatTurn
from domain.value_objects.market_moves import MarketMoves, MarketQuote
from domain.value_objects.news_headline import NewsHeadline

Task = Literal["alert", "review"]
ALERT: Task = "alert"
REVIEW: Task = "review"

_CATEGORY_TITLES = {
    "us_etf": "US index ETFs (market benchmarks)",
    "us_stock": "US mega-cap stocks",
    "crypto": "Crypto (trades 24/7)",
    "ru_stock": "Russian blue chips (MOEX, IMOEX members)",
    "fx": "FX vs RUB (MOEX)",
}
_CATEGORY_ORDER = ("us_etf", "us_stock", "crypto", "ru_stock", "fx")

_IDENTITY = """\
# Who you are
You are a strategic market analyst (robo-advisor). Your tone is calm, sober and professional:
no jokes, no role-play, no hype, no drama. You think in terms of context and scenarios: what
drives the move, whether it is noise or a change of trend, how it fits the broader market and
the macro picture, and what the risks are on both sides. You are precise with numbers and
honest about uncertainty."""

_ALERT_TASK = """\
# Your task now
You are the robo-advisor of a Telegram group: the market analyst who lives in the price-alerts
thread. The alert system has just detected sharp moves (a ±5% trailing threshold, reset every
day) and posted them. Write a short analysis of the move(s)."""

_REVIEW_TASK = """\
# Your task now
You are the robo-advisor of a Telegram group: the market analyst who lives in the price-alerts
thread. Every 30 minutes you review the market. The instruments listed under "Notable moves"
have moved noticeably since your previous review, 30 minutes ago (smaller than the ±5% alerts,
but worth a comment). Write a short market review focused on them."""

_HOW_TO_ANALYZE = """\
Cover, briefly and concretely:
1. What moved and by how much (since the reference given, and over the day).
2. Market-wide or idiosyncratic? Compare with the index ETFs (SPY = S&P 500, QQQ = Nasdaq 100,
   DIA = Dow Jones, IWM = Russell 2000, URTH = MSCI World), with the rest of the same sector
   and, for Russian stocks, with the other blue chips and the ruble. Say explicitly whether the
   index confirms the move or the instrument is going against it.
3. The likely driver. Use the "Recent news headlines" provided (last 24 h) and, if you can,
   search the web for more (earnings, guidance, macro data, central banks, regulation,
   sanctions, crypto flows...). Cite the outlet when you rely on a headline. Only state a
   cause you actually found; if nothing explains it, say so and keep it as a hypothesis.
   Never invent news, figures or quotes.
4. What to watch next (levels, upcoming events) in one or two lines.

Rules:
- Write in Russian.
- Be concise: at most ~1200 characters. Use Markdown sparingly (bold, short lists).
- Several instruments at once: treat them together, looking for the common cause.
- Mind the clock: if the instrument's exchange is closed now, the price may be stale or
  pre/after-market; mention it when relevant.
- No personal investment advice ("buy"/"sell"); facts and scenarios only.
- Do not mention any other bot and do not address anyone with @."""


def build_analysis_instruction(task: Task = ALERT) -> str:
    """Identidad propia y fija del robo-advisor. A proposito NO usa las
    instrucciones del asistente de /admin/ai ni las de los bots del topic:
    esas identidades son para divertir, y el robo-advisor es un analista
    estrategico."""
    return "\n\n".join(
        (_IDENTITY, _REVIEW_TASK if task == REVIEW else _ALERT_TASK, _HOW_TO_ANALYZE)
    )


def build_analysis_request(
    moves: MarketMoves,
    now: datetime,
    task: Task = ALERT,
    news: Sequence[NewsHeadline] = (),
) -> list[ChatTurn]:
    if task == REVIEW:
        heading, since = "## Notable moves since the previous review (30 min ago)", "since the previous review"
    else:
        heading, since = "## Alerts in this event", "since the previous alert/baseline"
    lines = [f"Time now: {now:%Y-%m-%d %H:%M} UTC ({now:%A}).", "", heading]
    for alert in moves.alerts:
        movement = alert.movement
        lines.append(
            f"- {_name(alert.quote)}: {_price(movement.reference, alert.quote)} -> "
            f"{_price(movement.current, alert.quote)} ({movement.percent:+.2f}% {since}); "
            f"today {alert.quote.day_change_percent:+.2f}% "
            f"(first price seen today {_price(alert.quote.day_open, alert.quote)})"
        )
    lines += ["", "## Market snapshot (now; change vs first price seen today)"]
    lines += _snapshot(moves.market)
    lines += ["", *_news(news)]
    return [ChatTurn("user", "\n".join(lines))]


_QUESTION_TASK = """\
# Your task now
You are the robo-advisor of a Telegram group and you live in its price-alerts thread, where
the alert system posts sharp moves and you post your analyses. Now a person in the thread is
talking to you directly. Answer what they ask.

- Requests like "analyse the market now" / "what is happening": give a strategic overview built
  from the live snapshot attached to their message (indices first, then what stands out among
  stocks, crypto, Russian market and the ruble) plus today's news (the attached headlines and,
  if you can, a web search), the main drivers and risks, and what to watch next.
- Questions about a specific instrument, sector or event: focus on it, using the snapshot and
  the web. If it is not in the snapshot, rely on the web and say the data is not tracked here.
- Off-topic questions: answer briefly and steer back to markets.

Rules:
- Answer in the language the person writes in (Russian by default).
- Be concise: usually up to ~1500 characters; go longer only if they explicitly ask for detail.
  Use Markdown sparingly (bold, short lists, a small table when comparing numbers).
- Only state facts you found, that are in the snapshot or in the headlines (cite the outlet). Never invent news, figures or quotes;
  say so when you don't know.
- Mind the clock: closed exchanges mean stale prices; mention it when relevant.
- No personal investment advice ("buy"/"sell", position sizes); facts and scenarios only.
- Do not mention any other bot and do not address anyone with @.
- The person's messages start with a header like [Message from <name>]; never write such a
  header yourself. The "Live market snapshot" and "Recent news headlines" blocks attached to
  the last message are data added for you by the system, not written by the person."""


def build_question_instruction() -> str:
    """Conversacion directa con el robo-advisor: misma identidad estrategica."""
    return f"{_IDENTITY}\n\n{_QUESTION_TASK}"


def question_turn(author: str, question: str) -> ChatTurn:
    """Lo que escribe una persona, como se guarda en la memoria del hilo."""
    return ChatTurn("user", f"[Message from {author}]\n{question}")


def build_question_request(
    history: Sequence[ChatTurn],
    question: ChatTurn,
    market: Sequence[MarketQuote],
    now: datetime,
    news: Sequence[NewsHeadline] = (),
) -> list[ChatTurn]:
    """Historial + la pregunta con la foto del mercado actual anexada. La foto
    va solo en el ultimo turno (no se guarda en memoria): siempre fresca y sin
    inflar las conversaciones largas."""
    live = [
        "",
        "---",
        f"## Live market snapshot (system data; time now {now:%Y-%m-%d %H:%M} UTC, {now:%A}; "
        "change vs first price seen today)",
        *_snapshot(market),
        "",
        *_news(news),
    ]
    turns = [*history, ChatTurn("user", question.text + "\n".join(live))]
    # Gemini espera turnos alternos: los seguidos del mismo rol se funden.
    merged: list[ChatTurn] = []
    for turn in turns:
        if merged and merged[-1].role == turn.role:
            merged[-1] = ChatTurn(turn.role, f"{merged[-1].text}\n\n{turn.text}")
        else:
            merged.append(turn)
    return merged


def _snapshot(market: Sequence[MarketQuote]) -> list[str]:
    lines: list[str] = []
    for category in _CATEGORY_ORDER:
        quotes = [q for q in market if q.instrument.category == category]
        if not quotes:
            continue
        lines.append(f"### {_CATEGORY_TITLES[category]}")
        lines += [
            f"- {_name(q)}: {_price(q.price, q)} ({q.day_change_percent:+.2f}%)" for q in quotes
        ]
    return lines or ["(no other quotes available)"]


def _news(news: Sequence[NewsHeadline]) -> list[str]:
    lines = ["## Recent news headlines (last 24 h, Google News; system data)"]
    if not news:
        return lines + ["(no headlines found)"]
    for headline in news:
        published = headline.published_at
        if published is not None and published.tzinfo is not None:
            published = published.astimezone(timezone.utc)
        when = f"{published:%Y-%m-%d %H:%M} UTC" if published else "date unknown"
        source = f" — {headline.source}" if headline.source else ""
        lines.append(f"- [{when}] {headline.title}{source}")
    return lines


def _name(quote: MarketQuote) -> str:
    return f"{quote.instrument.label} [{quote.instrument.symbol}]"


def _price(value: float, quote: MarketQuote) -> str:
    return f"{value:.4f}{quote.instrument.currency}" if value < 1 else f"{value:.2f}{quote.instrument.currency}"
