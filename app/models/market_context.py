from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class MarketContext(BaseModel):
    """
    Tape context computed from SPY + QQQ.

    regime:
      - RISK_ON: tape supportive
      - NEUTRAL: mixed / unclear
      - RISK_OFF: tape hostile
      - UNKNOWN: insufficient data to decide

    risk_off:
      convenience boolean (True only when regime == RISK_OFF)

    rs_30m:
      relative strength vs QQQ over 30 minutes (added later; None for now)

    audit:
      short explanation strings so you can trust/debug the decision
    """

    regime: str
    risk_off: bool
    rs_30m: Optional[float] = None
    audit: List[str] = []
