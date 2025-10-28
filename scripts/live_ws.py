# scripts/live_ws.py
import asyncio
import json
import math
import os
import time
from asyncio import Lock
from typing import Dict, List, Optional

import pandas as pd

from settings import settings
from discover.instruments import build_pairs
from datafeed.primary_ws import PrimaryWS
from sim.mep_ref import MEPRef
from agent.rules import signal_ars_to_usd, signal_usd_to_ars
from exec.state import AccountState
from exec.reconciler import Reconciler
from exec.sync import leg_buy_ioc_then_sell_smart
from exec.latency import periodic_latency_probe
from util.trace import Trace

# ----- paths para UI -----
STATUS_JSON     = "assets/plots/status.json"
TRADES_CSV      = "assets/plots/live_trades.csv"
BOOKS_JSON      = "assets/plots/books.json"
POSITIONS_JSON  = "assets/plots/positions.json"

# ----- helpers ui/control -----
def load_control() -> dict:
    p = settings.control_path
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def write_json(path: str, obj: dict):
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass

def apply_overrides(ctrl: dict):
    """
    aplica en caliente overrides venidos desde control.json (ui),
    incluyendo credenciales, urls y entorno (paper/live).
    """
    changed = {}

    keys_numeric = [
        "WAIT_MS", "GRACE_MS", "EDGE_TOL_BPS",
        "thresh_pct", "min_notional_ars",
        "risk_poll_s", "risk_refresh_s", "poll_s",
        "HALF_LIFE_S", "REF_K", "REF_MIN_HL_S", "REF_MAX_HL_S", "LAT_PROBE_S",
        "instrument_refresh_s"
    ]
    keys_bool = ["trace_enabled", "trace_raw", "REF_TUNE"]
    keys_text = [
        "REF_MODE", "UNWIND_MODE", "balance_mode",
        # credenciales/urls/env
        "env", "primary_base_url", "primary_ws_url", "proprietary_tag",
        "primary_paper_username", "primary_paper_password", "account_paper",
        "primary_live_username", "primary_live_password", "account_live",
    ]

    for k in keys_numeric:
        if k in ctrl:
            try:
                v = ctrl[k]
                setattr(settings, k, type(getattr(settings, k))(v))
                changed[k] = v
            except Exception:
                pass
    for k in keys_bool:
        if k in ctrl:
            try:
                v = bool(ctrl[k])
                setattr(settings, k, v)
                changed[k] = v
            except Exception:
                pass
    for k in keys_text:
        if k in ctrl:
            try:
                v = str(ctrl[k])
                setattr(settings, k, v)
                changed[k] = v
            except Exception:
                pass

    return changed

def operable_ars_a2u(qa, qu, implied) -> float:
    if implied is None:
        return 0.0
    # pesos máximos operables dados los top-of-book
    return min(qa.ask_qty * qa.ask, qu.bid_qty * qu.bid * implied)

def operable_ars_u2a(qa, qu, implied_rev) -> float:
    if implied_rev is None:
        return 0.0
    return min(qa.bid_qty * qa.bid, qu.ask_qty * qu.ask * implied_rev)

async def er_consumer(feed: PrimaryWS, rec: Reconciler):
    while True:
        er = await feed.next_exec_report()
        rec.apply_er(er)

async def periodic_refresh(acct: AccountState, rec: Reconciler):
    while True:
        acct.refresh_from_risk()
        rec.full_refresh(acct.ars, acct.usd)
        await asyncio.sleep(settings.risk_refresh_s)

async def periodic_instrument_refresh(feed: PrimaryWS, pairs_ref: dict, lock: Lock):
    while True:
        await asyncio.sleep(settings.instrument_refresh_s)
        try:
            new_pairs = build_pairs()
            new_symbols = sorted({s for a, b in new_pairs for s in (a, b)})
            await feed.update_symbols(new_symbols)
            async with lock:
                pairs_ref["pairs"] = new_pairs
        except Exception:
            # loguear si querés
            pass

async def force_flatten_positions(feed: PrimaryWS, rec: Reconciler):
    pos: Dict[str, int] = rec.snapshot_positions()
    for sym, qty in pos.items():
        q = abs(int(qty or 0))
        if q <= 0:
            continue
        side = "SELL" if qty > 0 else "BUY"
        try:
            # market/IOC para sacarse posición rápido
            await feed.send_market(sym, side, q, tif="IOC")
        except Exception:
            pass

# ----- montaje principal -----
async def main():
    # descubrimos pares (ARS/USD)
    pairs = build_pairs()
    if not pairs:
        raise SystemExit("no hay pares ars/usd descubiertos")

    # par ref por default: AL30/AL30D
    ref_pair = next((p for p in pairs if p[0].upper() == "AL30" and p[1].upper() == "AL30D"), pairs[0])

    symbols = sorted({s for a, b in pairs for s in (a, b)})

    # feed ws/rest (urls/creds salen de settings, que a su vez mapea .env / overrides)
    feed = PrimaryWS(symbols)

    # referencia mep (ema auto-tune por latencia si REF_TUNE=True)
    ref = MEPRef(half_life_s=float(settings.HALF_LIFE_S))

    tracer: Optional[Trace] = Trace(settings.trace_path, settings.trace_rotate_mb) if settings.trace_enabled else None
    task_ws = asyncio.create_task(feed.run())

    # hot-reload de instrumentos
    pairs_ref = {"pairs": pairs}
    pairs_lock = asyncio.Lock()
    task_discover = asyncio.create_task(periodic_instrument_refresh(feed, pairs_ref, pairs_lock))

    # esperamos token para armar account
    while not feed.token_value():
        await asyncio.sleep(0.05)

    acct = AccountState(feed.token_value())
    acct.refresh_from_risk()

    balance_mode = settings.balance_mode.lower()
    rec = Reconciler(acct.ars, acct.usd)

    # consumidor de ER + (opcional) refresco periódico de risk (si er_reconcile)
    tasks_extra: List[asyncio.Task] = [asyncio.create_task(er_consumer(feed, rec))]
    if balance_mode == "er_reconcile":
        tasks_extra.append(asyncio.create_task(periodic_refresh(acct, rec)))

    # probe de latencia + auto-tune hl
    stop_probe = asyncio.Event()
    task_probe = asyncio.create_task(periodic_latency_probe(feed, tracer, ref, stop_probe))

    trading_enabled = True
    force_reload_flag = False
    force_flatten_flag = False
    last_ctrl_apply = 0.0

    # logging de señales
    rows = []

    try:
        while True:
            # ---- control en caliente ----
            ctrl = load_control()
            applied = {}

            if ctrl:
                # panic / resume
                if ctrl.get("panic_stop") is True:
                    trading_enabled = False
                    if tracer: tracer.log("control.panic")
                if ctrl.get("resume") is True:
                    trading_enabled = True
                    if tracer: tracer.log("control.resume")
                    try:
                        ctrl["resume"] = False
                        with open(settings.control_path, "w", encoding="utf-8") as f:
                            json.dump(ctrl, f)
                    except Exception:
                        pass

                # reload instruments on demand
                if ctrl.get("reload_instruments_now") is True:
                    force_reload_flag = True
                    if tracer: tracer.log("control.reload")
                    try:
                        ctrl["reload_instruments_now"] = False
                        with open(settings.control_path, "w", encoding="utf-8") as f:
                            json.dump(ctrl, f)
                    except Exception:
                        pass

                # flatten on demand
                if ctrl.get("force_flatten") is True:
                    force_flatten_flag = True
                    if tracer: tracer.log("control.force_flatten")
                    try:
                        ctrl["force_flatten"] = False
                        with open(settings.control_path, "w", encoding="utf-8") as f:
                            json.dump(ctrl, f)
                    except Exception:
                        pass

                # aplicar overrides (incluye credenciales/urls/env)
                if time.time() - last_ctrl_apply > 0.25:
                    applied = apply_overrides(ctrl)
                    last_ctrl_apply = time.time()
                    # si tocan HALF_LIFE y estamos sin auto-tune
                    if "HALF_LIFE_S" in applied and not settings.REF_TUNE:
                        try:
                            ref.set_half_life(float(settings.HALF_LIFE_S))
                        except Exception:
                            pass
                    if tracer and applied:
                        tracer.log("overrides.apply", **applied)

                # reautenticar en caliente si te lo pide la UI
                if ctrl.get("force_reauth") is True:
                    if tracer: tracer.log("control.force_reauth")
                    try:
                        ctrl["force_reauth"] = False
                        with open(settings.control_path, "w", encoding="utf-8") as f:
                            json.dump(ctrl, f)
                    except Exception:
                        pass
                    # cerramos ws actual
                    try:
                        await feed.stop()
                    except Exception:
                        pass
                    # recreamos feed con nuevas urls/creds de settings
                    new_symbols = feed.subscribed_symbols()
                    feed = PrimaryWS(new_symbols)
                    task_ws.cancel()
                    task_ws = asyncio.create_task(feed.run())
                    # esperamos token nuevo
                    while not feed.token_value():
                        await asyncio.sleep(0.05)
                    # refrescamos estado de cuenta y reconciliador
                    acct = AccountState(feed.token_value())
                    acct.refresh_from_risk()
                    rec = Reconciler(acct.ars, acct.usd)

            if force_reload_flag:
                try:
                    new_pairs = build_pairs()
                    new_symbols = sorted({s for a, b in new_pairs for s in (a, b)})
                    await feed.update_symbols(new_symbols)
                    async with pairs_lock:
                        pairs_ref["pairs"] = new_pairs
                except Exception:
                    pass
                force_reload_flag = False

            if force_flatten_flag:
                try:
                    await force_flatten_positions(feed, rec)
                finally:
                    force_flatten_flag = False

            # ---- snapshot de mercado ----
            snap = feed.snapshot()

            # ---- cash source (risk_poll o er_reconcile) ----
            if settings.balance_mode.lower() == "er_reconcile":
                cash_ars, cash_usd = rec.cash.ars, rec.cash.usd
                last_refresh = time.time()
                src = "er_reconcile"
            else:
                t = time.time()
                if t - getattr(main, "_last_poll", 0.0) >= settings.risk_poll_s:
                    acct.refresh_from_risk()
                    setattr(main, "_last_poll", t)
                cash_ars, cash_usd = acct.ars, acct.usd
                last_refresh = getattr(main, "_last_poll", 0.0)
                src = "risk_poll"

            # ---- volcados para UI ----
            # top-of-book
            try:
                books = {
                    s: dict(
                        bid=q.bid, ask=q.ask,
                        bid_qty=q.bid_qty, ask_qty=q.ask_qty,
                        ts=str(q.ts),
                    )
                    for s, q in snap.items()
                }
                write_json(BOOKS_JSON, dict(ts=time.time(), books=books))
            except Exception:
                pass

            # posiciones + cash
            try:
                write_json(POSITIONS_JSON, dict(
                    ts=time.time(),
                    positions=rec.snapshot_positions(),
                    cash_ars=cash_ars,
                    cash_usd=cash_usd
                ))
            except Exception:
                pass

            # ---- referencias MEP ----
            async with pairs_lock:
                cur_pairs = list(pairs_ref["pairs"])
            if not cur_pairs:
                await asyncio.sleep(settings.poll_s)
                continue
            if ref_pair not in cur_pairs:
                ref_pair = next(
                    (p for p in cur_pairs if p[0].upper() == "AL30" and p[1].upper() == "AL30D"),
                    cur_pairs[0]
                )

            qa_ref = snap.get(ref_pair[0])
            qu_ref = snap.get(ref_pair[1])

            if qa_ref and qu_ref:
                # update ref (tick + ema)
                ref.update(
                    ts_unix=time.time(),
                    ask_peso_al30=qa_ref.ask,
                    bid_usd_al30d=qu_ref.bid,
                    bid_peso_al30=qa_ref.bid,
                    ask_usd_al30d=qu_ref.ask
                )
                a2u_ref = ref.ref_a2u(settings.REF_MODE)
                u2a_ref = ref.ref_u2a(settings.REF_MODE)

                # status enriquecido para ui
                write_json(STATUS_JSON, dict(
                    ts=time.time(),
                    env=settings.env,
                    mode=settings.balance_mode,
                    last_refresh=last_refresh,
                    cash_ars=cash_ars,
                    cash_usd=cash_usd,
                    source=src,
                    trading_enabled=trading_enabled,
                    poll_s=settings.poll_s,
                    risk_poll_s=settings.risk_poll_s,
                    ref_mode=settings.REF_MODE,
                    half_life_s=settings.HALF_LIFE_S,
                    ref_tune=settings.REF_TUNE,
                    ref_k=settings.REF_K,
                    ref_min=settings.REF_MIN_HL_S,
                    ref_max=settings.REF_MAX_HL_S,
                    lat_probe_s=settings.LAT_PROBE_S,
                    ref_inst_a2u=ref.inst_a2u,
                    ref_ema_a2u=ref.ema_a2u,
                    ref_inst_u2a=ref.inst_u2a,
                    ref_ema_u2a=ref.ema_u2a,
                    ref_pair=dict(ars=ref_pair[0], usd=ref_pair[1]),
                ))

                # ---- trading loop: ARS -> USD ----
                if trading_enabled and a2u_ref:
                    for ars_sym, usd_sym in cur_pairs:
                        qa = snap.get(ars_sym)
                        qu = snap.get(usd_sym)
                        if not qa or not qu:
                            continue
                        implied = (qa.ask / qu.bid) if (qa.ask > 0 and qu.bid > 0) else None
                        op_ars = operable_ars_a2u(qa, qu, implied)

                        if implied and signal_ars_to_usd(
                            implied, a2u_ref, op_ars,
                            settings.min_notional_ars, settings.thresh_pct
                        ):
                            # caps por profundidad y cash
                            cap_by_depth = int(min(qu.bid_qty, qa.ask_qty))
                            cap_by_cash  = int(max(int(cash_ars // max(qa.ask, 1)), 0))
                            nom_cap      = max(min(cap_by_depth, cap_by_cash), 0)

                            if nom_cap > 0 and nom_cap * qa.ask >= settings.min_notional_ars:
                                async def refs():
                                    s2 = feed.snapshot()
                                    qa2, qu2 = s2.get(ars_sym), s2.get(usd_sym)
                                    implied_now = (qa2.ask / qu2.bid) if (qa2 and qu2 and qa2.ask > 0 and qu2.bid > 0) else None
                                    return dict(
                                        dir="A2U", ref=a2u_ref, implied_now=implied_now,
                                        book_ok=bool(qu2 and qu2.bid_qty > 0),
                                        rem_sell_px=(qu2.bid if qu2 else None)
                                    )

                                if settings.trace_enabled and tracer:
                                    tracer.log("signal.a2u",
                                               pair=f"{ars_sym}:{usd_sym}",
                                               implied=implied, ref=a2u_ref,
                                               cap_depth=int(min(qu.bid_qty, qa.ask_qty)),
                                               cap_cash=int(max(int(cash_ars // max(qa.ask, 1)), 0)),
                                               nom_cap=nom_cap,
                                               ref_inst=ref.inst_a2u, ref_ema=ref.ema_a2u, mode=settings.REF_MODE)

                                res = await leg_buy_ioc_then_sell_smart(
                                    feed,
                                    buy_symbol=ars_sym,  buy_price=qa.ask,  buy_qty_cap=nom_cap,
                                    sell_symbol=usd_sym, sell_price=qu.bid,
                                    get_refs_and_implied=refs,
                                    wait_ms=settings.WAIT_MS, grace_ms=settings.GRACE_MS
                                )

                                if settings.trace_enabled and tracer:
                                    tracer.log("exec.a2u.result", pair=f"{ars_sym}:{usd_sym}", **res)

                                rows.append(dict(
                                    ts=str(qa.ts), pair=f"{ars_sym}:{usd_sym}", dir="ARS->USD",
                                    implied=implied, mep_ref=a2u_ref, nom=nom_cap, px_ars=qa.ask, px_usd=qu.bid
                                ))

                # ---- trading loop: USD -> ARS (elige el mejor implied_rev) ----
                if trading_enabled and u2a_ref and rec.cash.usd > 0:
                    cands = []
                    for ars_sym, usd_sym in cur_pairs:
                        qa = snap.get(ars_sym)
                        qu = snap.get(usd_sym)
                        if not qa or not qu:
                            continue
                        implied_rev = (qa.bid / qu.ask) if (qa.bid > 0 and qu.ask > 0) else None
                        op_ars_rev = operable_ars_u2a(qa, qu, implied_rev)

                        if implied_rev and signal_usd_to_ars(
                            implied_rev, u2a_ref, op_ars_rev,
                            settings.min_notional_ars, settings.thresh_pct
                        ):
                            cands.append((implied_rev, ars_sym, usd_sym, qa, qu))

                    if cands:
                        implied_rev, ars_sym, usd_sym, qa, qu = max(cands, key=lambda x: x[0])
                        cap_by_depth = int(min(qa.bid_qty, qu.ask_qty))
                        cap_by_cash  = int(max(int(rec.cash.usd // max(qu.ask, 1)), 0))
                        nom_cap      = max(min(cap_by_depth, cap_by_cash), 0)

                        if nom_cap > 0 and nom_cap * qa.bid >= settings.min_notional_ars:
                            async def refs_u2a():
                                s2 = feed.snapshot()
                                qa2, qu2 = s2.get(ars_sym), s2.get(usd_sym)
                                implied_now = (qa2.bid / qu2.ask) if (qa2 and qu2 and qa2.bid > 0 and qu2.ask > 0) else None
                                return dict(
                                    dir="U2A", ref=u2a_ref, implied_now=implied_now,
                                    book_ok=bool(qa2 and qa2.bid_qty > 0),
                                    rem_sell_px=(qa2.bid if qa2 else None)
                                )

                            if settings.trace_enabled and tracer:
                                tracer.log("signal.u2a",
                                           pair=f"{ars_sym}:{usd_sym}",
                                           implied=implied_rev, ref=u2a_ref,
                                           cap_depth=int(min(qa.bid_qty, qu.ask_qty)),
                                           cap_cash=int(max(int(rec.cash.usd // max(qu.ask, 1)), 0)),
                                           nom_cap=nom_cap,
                                           ref_inst=ref.inst_u2a, ref_ema=ref.ema_u2a, mode=settings.REF_MODE)

                            res = await leg_buy_ioc_then_sell_smart(
                                feed,
                                buy_symbol=usd_sym,  buy_price=None,   buy_qty_cap=nom_cap,
                                sell_symbol=ars_sym, sell_price=qa.bid,
                                get_refs_and_implied=refs_u2a,
                                wait_ms=settings.WAIT_MS, grace_ms=settings.GRACE_MS
                            )

                            if settings.trace_enabled and tracer:
                                tracer.log("exec.u2a.result", pair=f"{ars_sym}:{usd_sym}", **res)

                            rows.append(dict(
                                ts=str(qa.ts), pair=f"{ars_sym}:{usd_sym}", dir="USD->ARS",
                                implied=implied_rev, mep_ref=u2a_ref, nom=nom_cap, px_ars=qa.bid
                            ))

                # flush parcial de trades para la ui
                if rows and len(rows) % 10 == 0:
                    try:
                        pd.DataFrame(rows).to_csv(TRADES_CSV, index=False)
                    except Exception:
                        pass

            # loop pacing
            await asyncio.sleep(settings.poll_s)

    finally:
        # flush final
        try:
            if rows:
                pd.DataFrame(rows).to_csv(TRADES_CSV, index=False)
        except Exception:
            pass

        # detener tareas auxiliares
        try:
            stop_probe.set()
        except Exception:
            pass

        for t in tasks_extra:
            t.cancel()
        task_discover.cancel()

        # cerrar feed ws
        try:
            await feed.stop()
            await task_ws
        except Exception:
            pass

        try:
            await task_probe
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
