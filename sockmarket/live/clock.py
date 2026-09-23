"""US equity-market clock: is the market open right now, and if not, when next?

Regular NYSE/Nasdaq session is 09:30-16:00 America/New_York, Monday-Friday,
excluding market holidays. This uses a static holiday table (2024-2027) plus a
few early-close days; refresh it yearly. Standard library only (``zoneinfo``).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

REGULAR_OPEN = dt.time(9, 30)
REGULAR_CLOSE = dt.time(16, 0)
EARLY_CLOSE = dt.time(13, 0)

# Full-day market holidays (NYSE), as ISO dates. Refresh yearly.
MARKET_HOLIDAYS: frozenset[dt.date] = frozenset(
    dt.date.fromisoformat(d)
    for d in [
        # 2024
        "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
        "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
        # 2025
        "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
        "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
        # 2026
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
        "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
        # 2027
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
        "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    ]
)

# Half-days (early close at 13:00 ET).
EARLY_CLOSE_DAYS: frozenset[dt.date] = frozenset(
    dt.date.fromisoformat(d)
    for d in [
        "2024-07-03", "2024-11-29", "2024-12-24",
        "2025-07-03", "2025-11-28", "2025-12-24",
        "2026-11-27", "2026-12-24",
        "2027-11-26",
    ]
)


@dataclass
class MarketClock:
    """Answers market-hours questions in America/New_York time."""

    tz: ZoneInfo = NY

    def now(self) -> dt.datetime:
        return dt.datetime.now(self.tz)

    def _close_time(self, day: dt.date) -> dt.time:
        return EARLY_CLOSE if day in EARLY_CLOSE_DAYS else REGULAR_CLOSE

    def is_trading_day(self, day: dt.date) -> bool:
        return day.weekday() < 5 and day not in MARKET_HOLIDAYS

    def is_open(self, at: dt.datetime | None = None) -> bool:
        at = at or self.now()
        at = at.astimezone(self.tz)
        day = at.date()
        if not self.is_trading_day(day):
            return False
        return REGULAR_OPEN <= at.time() < self._close_time(day)

    def next_open(self, at: dt.datetime | None = None) -> dt.datetime:
        at = (at or self.now()).astimezone(self.tz)
        # If before today's open on a trading day, it's today; else scan forward.
        day = at.date()
        if self.is_trading_day(day) and at.time() < REGULAR_OPEN:
            return dt.datetime.combine(day, REGULAR_OPEN, self.tz)
        probe = day + dt.timedelta(days=1)
        for _ in range(15):  # at most ~2 weeks of closures
            if self.is_trading_day(probe):
                return dt.datetime.combine(probe, REGULAR_OPEN, self.tz)
            probe += dt.timedelta(days=1)
        raise RuntimeError("no trading day found within 15 days (stale holiday table?)")

    def next_close(self, at: dt.datetime | None = None) -> dt.datetime:
        at = (at or self.now()).astimezone(self.tz)
        day = at.date()
        if self.is_trading_day(day) and at.time() < self._close_time(day):
            return dt.datetime.combine(day, self._close_time(day), self.tz)
        # otherwise the close of the next trading day
        nxt_open = self.next_open(at)
        d = nxt_open.date()
        return dt.datetime.combine(d, self._close_time(d), self.tz)

    def seconds_until_open(self, at: dt.datetime | None = None) -> float:
        at = at or self.now()
        return max(0.0, (self.next_open(at) - at.astimezone(self.tz)).total_seconds())
