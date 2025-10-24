from dataclasses import dataclass
from typing import Dict

@dataclass
class Cash:
    ars: float = 0.0
    usd: float = 0.0

class Reconciler:
    """
    lleva cash aproximado y posiciones por símbolo aplicando execution reports (ws: type 'er').
    en modo er_reconcile: este objeto es fuente de verdad de cash; en risk_poll, lo usamos para posiciones.
    """
    def __init__(self, initial_ars: float = 0.0, initial_usd: float = 0.0):
        self.cash = Cash(initial_ars, initial_usd)
        self.pos: Dict[str, int] = {}

    def apply_er(self, er):
        status = (er.status or "").upper()
        if status not in ("FILLED", "PARTIALLY_FILLED"):
            return
        sym = (er.symbol or "").upper()
        q = int(er.qty or 0)
        px = float(er.price or 0.0)
        if q <= 0:
            return

        sign = 1 if (er.side == "BUY") else -1
        self.pos[sym] = self.pos.get(sym, 0) + sign * q
        if self.pos[sym] == 0:
            self.pos.pop(sym, None)

        if sym.endswith("D"):
            if er.side == "SELL": self.cash.usd += q
            elif er.side == "BUY": self.cash.usd -= q
        else:
            notional_ars = q * px
            if er.side == "BUY": self.cash.ars -= notional_ars
            elif er.side == "SELL": self.cash.ars += notional_ars

    def full_refresh(self, ars_from_api: float, usd_from_api: float):
        self.cash.ars = float(ars_from_api or 0.0)
        self.cash.usd = float(usd_from_api or 0.0)

    def snapshot_positions(self) -> Dict[str, int]:
        return dict(self.pos)
