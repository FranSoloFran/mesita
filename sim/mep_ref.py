import math
from collections import deque
from typing import Optional

class MEPRef:
    """
    mantiene dos referencias:
      - instantánea (tick a tick)
      - ema temporal (half-life en segundos, independiente de cadencia de ticks)
    """
    def __init__(self, half_life_s: float = 7.0):
        self.half = max(float(half_life_s), 0.0)
        self._tau = self.half / math.log(2) if self.half > 0 else None
        self._last_ts: Optional[float] = None

        self._inst_a2u: Optional[float] = None
        self._inst_u2a: Optional[float] = None
        self._ema_a2u: Optional[float] = None
        self._ema_u2a: Optional[float] = None

    @staticmethod
    def _safe_ratio(num, den):
        try:
            num = float(num or 0); den = float(den or 0)
            if num > 0 and den > 0:
                return num/den
        except Exception:
            pass
        return None

    def update(self, ts_unix: float, ask_peso_al30, bid_usd_al30d, bid_peso_al30, ask_usd_al30d):
        a2u_now = self._safe_ratio(ask_peso_al30, bid_usd_al30d)
        u2a_now = self._safe_ratio(bid_peso_al30, ask_usd_al30d)
        if a2u_now: self._inst_a2u = a2u_now
        if u2a_now: self._inst_u2a = u2a_now

        if self.half <= 0 or self._tau is None:
            # sin ema (equivale a modo tick)
            self._ema_a2u = self._inst_a2u
            self._ema_u2a = self._inst_u2a
            self._last_ts = ts_unix
            return

        if self._last_ts is None:
            self._ema_a2u = a2u_now
            self._ema_u2a = u2a_now
            self._last_ts = ts_unix
            return

        dt = max(ts_unix - self._last_ts, 0.0)
        self._last_ts = ts_unix
        if dt == 0 or (a2u_now is None and u2a_now is None):
            return

        alpha = 1.0 - math.exp(-dt / self._tau)
        if a2u_now is not None:
            self._ema_a2u = (1 - alpha) * (self._ema_a2u if self._ema_a2u is not None else a2u_now) + alpha * a2u_now
        if u2a_now is not None:
            self._ema_u2a = (1 - alpha) * (self._ema_u2a if self._ema_u2a is not None else u2a_now) + alpha * u2a_now

    # getters
    @property
    def inst_a2u(self): return self._inst_a2u
    @property
    def inst_u2a(self): return self._inst_u2a
    @property
    def ema_a2u(self): return self._ema_a2u
    @property
    def ema_u2a(self): return self._ema_u2a

    # referencias por modo
    def ref_a2u(self, mode: str):
        if mode == "tick":
            return self._inst_a2u
        # hybrid: conservador (barato de verdad)
        candidates = [x for x in (self._inst_a2u, self._ema_a2u) if x]
        return min(candidates) if candidates else None

    def ref_u2a(self, mode: str):
        if mode == "tick":
            return self._inst_u2a
        # hybrid: conservador (caro de verdad)
        candidates = [x for x in (self._inst_u2a, self._ema_u2a) if x]
        return max(candidates) if candidates else None
