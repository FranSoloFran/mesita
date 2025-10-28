import asyncio, statistics, time
from collections import deque
from typing import Optional
from settings import settings
from util.trace import Trace

class RTTMedian:
    def __init__(self, maxlen: int = 60):
        self.buf = deque(maxlen=maxlen)
        self.last_ms: Optional[float] = None

    def add(self, ms: float):
        self.last_ms = float(ms)
        self.buf.append(self.last_ms)

    def median_ms(self) -> Optional[float]:
        if not self.buf: return None
        return float(statistics.median(self.buf))

async def periodic_latency_probe(feed, tracer: Optional[Trace], ref_obj, stop_evt: asyncio.Event):
    """
    manda BUY IOC con precio minúsculo (no ejecuta) y mide RTT por clOrdId.
    ajusta HALF_LIFE_S = clamp(REF_K * median_rtt, [REF_MIN_HL_S, REF_MAX_HL_S]) si REF_TUNE=true.
    """
    est = RTTMedian(maxlen=120)
    while not stop_evt.is_set():
        try:
            # probe: símbolo neutral (usa al30 si está suscripto, si no cualquiera)
            syms = feed.subscribed_symbols() or ["AL30"]
            sym = "AL30" if "AL30" in syms else syms[0]
            t0 = time.time()
            clid = await feed.send_limit(symbol=sym, side="BUY", qty=1, price=0.01, tif="IOC")
            # esperar er del mismo clOrdId
            while True:
                er = await feed.next_exec_report()
                if er.cl_ord_id == clid:
                    rtt_ms = (time.time() - t0) * 1000.0
                    est.add(rtt_ms)
                    if tracer: tracer.log("latency.rtt", symbol=sym, rtt_ms=rtt_ms)
                    break

            med = est.median_ms()
            if settings.REF_TUNE and med is not None:
                target = settings.REF_K * (med/1000.0)
                hl = max(settings.REF_MIN_HL_S, min(settings.REF_MAX_HL_S, target))
                # actualizar settings y el ref en caliente
                settings.HALF_LIFE_S = hl
                if hasattr(ref_obj, "set_half_life"):
                    ref_obj.set_half_life(hl)
                if tracer: tracer.log("latency.hlf_update", median_ms=med, new_hl_s=hl)
        except Exception:
            # silencioso; seguimos probando
            pass
        await asyncio.sleep(max(1.0, float(settings.LAT_PROBE_S)))
