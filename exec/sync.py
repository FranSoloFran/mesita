import asyncio, time
from typing import Optional, Tuple, Callable
from settings import settings
from datafeed.primary_ws import PrimaryWS

def _edge_ok(implied_now: float, ref: float, dir_: str, tol_bps: float) -> Tuple[bool, bool]:
    if not implied_now or not ref: return (False, False)
    tol = tol_bps/10000.0
    if dir_ == "A2U":
        return (implied_now <= ref*(1 - settings.thresh_pct - tol),
                implied_now <= ref*(1 - tol))
    else:
        return (implied_now >= ref*(1 + settings.thresh_pct + tol),
                implied_now >= ref*(1 + tol))

async def leg_buy_ioc_then_sell_smart(
    feed: PrimaryWS,
    buy_symbol: str, buy_price: Optional[float], buy_qty_cap: int,
    sell_symbol: str, sell_price: Optional[float],
    get_refs_and_implied: Callable[[], dict],
    wait_ms: int | None = None, grace_ms: int | None = None
) -> dict:
    wait_ms  = settings.WAIT_MS if wait_ms is None else wait_ms
    grace_ms = settings.GRACE_MS if grace_ms is None else grace_ms
    tol_bps  = settings.EDGE_TOL_BPS

    if buy_price is None:
        await feed.send_market(buy_symbol, "BUY", buy_qty_cap, tif="IOC")
    else:
        await feed.send_limit(buy_symbol, "BUY", buy_qty_cap, buy_price, tif="IOC")

    t_end = time.time() + (wait_ms/1000)
    bought = 0; sold = 0
    while time.time() < t_end:
        try:
            er = await asyncio.wait_for(feed.next_exec_report(), timeout=0.05)
            if er.symbol == buy_symbol and er.side == "BUY" and er.status in ("FILLED","PARTIALLY_FILLED"):
                bought += int(er.qty or 0)
        except asyncio.TimeoutError:
            pass
    if bought <= 0:
        return {"bought":0, "sold":0, "unwound":False}

    if sell_price is None:
        await feed.send_market(sell_symbol, "SELL", bought, tif="IOC")
    else:
        await feed.send_limit(sell_symbol, "SELL", bought, sell_price, tif="DAY")

    t_grace = time.time() + (grace_ms/1000)
    while time.time() < t_grace and sold < bought:
        try:
            er = await asyncio.wait_for(feed.next_exec_report(), timeout=0.05)
            if er.symbol == sell_symbol and er.side == "SELL" and er.status in ("FILLED","PARTIALLY_FILLED"):
                sold += int(er.qty or 0)
        except asyncio.TimeoutError:
            pass

    rem = bought - sold
    if rem <= 0 or settings.UNWIND_MODE.lower() == "none":
        return {"bought": bought, "sold": sold, "unwound": False}

    if settings.UNWIND_MODE.lower() == "always":
        await feed.send_market(buy_symbol, "SELL", rem, tif="IOC")
        return {"bought": bought, "sold": sold, "unwound": True}

    info = get_refs_and_implied()
    dir_ = info.get("dir"); ref = info.get("ref"); implied_now = info.get("implied_now")
    book_ok = bool(info.get("book_ok")); rem_sell_px = info.get("rem_sell_px")
    still_edge, break_even = _edge_ok(implied_now, ref, dir_, tol_bps)

    if book_ok and (still_edge or break_even):
        if rem_sell_px is None:
            await feed.send_market(sell_symbol, "SELL", rem, tif="IOC")
        else:
            await feed.send_limit(sell_symbol, "SELL", rem, rem_sell_px, tif="IOC")
        return {"bought": bought, "sold": sold, "unwound": False}

    await feed.send_market(buy_symbol, "SELL", rem, tif="IOC")
    return {"bought": bought, "sold": sold, "unwound": True}
