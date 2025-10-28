import json
import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

STATUS_JSON     = "assets/plots/status.json"
CONTROL_JSON    = "assets/plots/control.json"
TRACE_PATH_DEF  = "assets/plots/trace.log"
TRADES_CSV      = "assets/plots/live_trades.csv"
ER_CSV          = "assets/plots/execution_reports.csv"
BOOKS_JSON      = "assets/plots/books.json"       # NEW
POSITIONS_JSON  = "assets/plots/positions.json"   # NEW

st.set_page_config(page_title="Mesita Control Panel", layout="wide")

def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(path: str, obj: dict):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def merge_control(overrides: dict):
    cur = load_json(CONTROL_JSON)
    cur.update(overrides)
    save_json(CONTROL_JSON, cur)

def human_size(bytes_val: int | None) -> str:
    if bytes_val is None:
        return "n/a"
    units = ["B","KB","MB","GB","TB"]
    x = float(bytes_val); i = 0
    while x >= 1024 and i < len(units)-1:
        x /= 1024.0; i += 1
    return f"{x:.1f} {units[i]}"

# ---------- SIDEBAR ----------
st.sidebar.title("Status")
status = load_json(STATUS_JSON)
st.sidebar.write(f"Balance Mode: **{status.get('source','?')}**")
st.sidebar.write(f"Trading Enabled: **{status.get('trading_enabled', False)}**")
st.sidebar.write(f"Cash ARS: **{status.get('cash_ars','?')}**")
st.sidebar.write(f"Cash USD: **{status.get('cash_usd','?')}**")
st.sidebar.write(f"Ref Mode: **{status.get('ref_mode','?')}**")
st.sidebar.write(f"Half-Life (s): **{status.get('half_life_s','?')}**")
st.sidebar.write(f"Ref Tune: **{status.get('ref_tune','?')}**")
st.sidebar.caption(f"TS: {status.get('ts','-')}")

trace_path = status.get("trace_path", TRACE_PATH_DEF)
try:
    trace_size = Path(trace_path).stat().st_size if os.path.exists(trace_path) else None
except Exception:
    trace_size = None
st.sidebar.write(f"Trace: **{human_size(trace_size)}**")

with st.sidebar.expander("Quick Actions"):
    col_a, col_b = st.columns(2)
    if col_a.button("Panic Stop", use_container_width=True):
        merge_control({"panic_stop": True}); st.success("Panic sent")
    if col_b.button("Resume", use_container_width=True):
        merge_control({"resume": True}); st.success("Resume sent")
    col_c, col_d = st.columns(2)
    if col_c.button("Reload Instruments", use_container_width=True):
        merge_control({"reload_instruments_now": True}); st.success("Reload sent")
    if col_d.button("Force Flatten", use_container_width=True):
        merge_control({"force_flatten": True}); st.success("Flatten sent")

# ---------- MAIN ----------
st.title("Mesita — Control Panel")

tab_market, tab_positions, tab_ref, tab_ctrl, tab_safety, tab_trace, tab_logs, tab_health = st.tabs(
    ["Market", "Positions", "Reference & Latency", "Controls", "Safety", "Trace", "Logs", "Health"]
)

# ======== MARKET ========
with tab_market:
    st.subheader("Top-of-Book (Live)")

    bj = load_json(BOOKS_JSON)
    books = bj.get("books", {})
    if not books:
        st.info("No live books yet."); 
    else:
        df = (
            pd.DataFrame.from_dict(books, orient="index")
            .reset_index()
            .rename(columns={"index":"Symbol", "bid":"Bid", "ask":"Ask", "bid_qty":"BidQty", "ask_qty":"AskQty", "ts":"TS"})
        )
        # optional filter: ARS/USD or search
        col1, col2, col3 = st.columns([1,1,2])
        with col1:
            side_filter = st.selectbox("Side", ["All", "ARS leg", "USD leg"], index=0,
                help="Heurístico: símbolos en USD suelen terminar en 'D' (AL30D).")
        with col2:
            sort_col = st.selectbox("Sort by", ["Symbol","Bid","Ask","BidQty","AskQty"], index=0)
        with col3:
            query = st.text_input("Filter (substring)", "")

        def is_usd(sym: str) -> bool:
            return sym.upper().endswith("D")

        if side_filter == "ARS leg":
            df = df[~df["Symbol"].str.upper().str.endswith("D")]
        elif side_filter == "USD leg":
            df = df[df["Symbol"].str.upper().str.endswith("D")]

        if query:
            df = df[df["Symbol"].str.contains(query, case=False)]

        df = df.sort_values(by=sort_col, ascending=True)
        st.dataframe(df, use_container_width=True, height=420)

# ======== POSITIONS ========
with tab_positions:
    st.subheader("Positions & Cash")
    pj = load_json(POSITIONS_JSON)
    pos = pj.get("positions", {})
    cash_ars = pj.get("cash_ars", status.get("cash_ars"))
    cash_usd = pj.get("cash_usd", status.get("cash_usd"))

    st.write(f"**Cash ARS:** {cash_ars} — **Cash USD:** {cash_usd}")
    if pos:
        pdf = pd.DataFrame([{"Symbol":k, "Qty":v} for k,v in pos.items()]).sort_values(by="Symbol")
        st.dataframe(pdf, use_container_width=True, height=300)
    else:
        st.info("No positions reported yet.")

# ======== REFERENCE & LATENCY ========
with tab_ref:
    st.subheader("MEP Reference & Auto-Tune by Latency")

    # live reference display
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.metric("Ref Pair (ARS/USD)", f"{status.get('ref_pair',{}).get('ars','?')} / {status.get('ref_pair',{}).get('usd','?')}")
        st.write(f"Instant A2U: **{status.get('ref_inst_a2u','-')}**")
        st.write(f"EMA A2U: **{status.get('ref_ema_a2u','-')}**")
    with col_r2:
        st.metric("Ref Mode", status.get("ref_mode","-"))
        st.write(f"Instant U2A: **{status.get('ref_inst_u2a','-')}**")
        st.write(f"EMA U2A: **{status.get('ref_ema_u2a','-')}**")

    st.divider()
    st.subheader("Parameters")

    ref_mode = st.selectbox(
        "REF_MODE",
        options=["tick","hybrid"],
        index=0 if status.get("ref_mode","tick")=="tick" else 1,
        help="tick: usa solo el MEP instantáneo. hybrid: combina instantáneo con EMA temporal (min/max)."
    )

    cols = st.columns(4)
    with cols[0]:
        ref_tune = st.checkbox("REF_TUNE (Auto-Adjust EMA)", value=bool(status.get("ref_tune", True)))
    with cols[1]:
        half_life_s = st.slider("HALF_LIFE_S (if REF_TUNE = off)", min_value=0.0, max_value=30.0, value=float(status.get("half_life_s",7.0)), step=0.5)
    with cols[2]:
        ref_k = st.slider("REF_K (HL ≈ K × median RTT s)", min_value=1.0, max_value=10.0, value=float(status.get("ref_k",4.0)), step=0.5)
    with cols[3]:
        lat_probe_s = st.slider("LAT_PROBE_S (s)", min_value=2.0, max_value=60.0, value=float(status.get("lat_probe_s",10.0)), step=1.0)

    col_min, col_max = st.columns(2)
    with col_min:
        ref_min_hl = st.slider("REF_MIN_HL_S", min_value=0.0, max_value=30.0, value=float(status.get("ref_min",2.0)), step=0.5)
    with col_max:
        ref_max_hl = st.slider("REF_MAX_HL_S", min_value=0.0, max_value=60.0, value=float(status.get("ref_max",20.0)), step=0.5)

    if st.button("Apply Reference/Latency", type="primary"):
        payload = {
            "REF_MODE": ref_mode,
            "REF_TUNE": ref_tune,
            "REF_K": ref_k,
            "REF_MIN_HL_S": ref_min_hl,
            "REF_MAX_HL_S": ref_max_hl,
            "LAT_PROBE_S": lat_probe_s
        }
        if not ref_tune:
            payload["HALF_LIFE_S"] = half_life_s
        merge_control(payload)
        st.success("Reference/Latency applied")

# ======== CONTROLS ========
with tab_ctrl:
    st.subheader("General Controls")
    col1, col2, col3 = st.columns(3)

    with col1:
        balance_mode = st.selectbox(
            "Balance Mode",
            options=["risk_poll", "er_reconcile"],
            index=0 if status.get("source","risk_poll") == "risk_poll" else 1,
            help="risk_poll: lee cash del API cada X seg. er_reconcile: usa fills + refresh periódico."
        )
        poll_s = st.number_input("poll_s (loop sleep, s)", min_value=0.01, max_value=2.0, value=float(status.get("overrides",{}).get("poll_s", status.get("poll_s",0.2))), step=0.01)
        risk_poll_s = st.number_input("risk_poll_s (s)", min_value=0.05, max_value=5.0, value=float(status.get("risk_poll_s",0.5)), step=0.05)

    with col2:
        thresh_pct = st.number_input("Threshold (fraction, e.g., 0.002 = 20 bps)", min_value=0.0001, max_value=0.01, value=float(status.get("overrides",{}).get("thresh_pct", status.get("thresh_pct",0.002))), step=0.0001, format="%.4f")
        min_notional_ars = st.number_input("Min Notional ARS", min_value=10000.0, max_value=5_000_000.0, value=float(status.get("overrides",{}).get("min_notional_ars", status.get("min_notional_ars",40000.0))), step=1000.0)
        edge_tol_bps = st.number_input("Edge Tolerance (bps for smart unwind)", min_value=0.0, max_value=10.0, value=float(status.get("overrides",{}).get("EDGE_TOL_BPS", status.get("EDGE_TOL_BPS",1.0))), step=0.1)

    with col3:
        unwind_mode = st.selectbox("Unwind Mode", options=["smart","always","none"], index=["smart","always","none"].index(status.get("UNWIND_MODE","smart")))
        wait_ms  = st.number_input("WAIT_MS (ms)", min_value=0, max_value=5000, value=int(status.get("overrides",{}).get("WAIT_MS", status.get("WAIT_MS",120))), step=10)
        grace_ms = st.number_input("GRACE_MS (ms)", min_value=0, max_value=5000, value=int(status.get("overrides",{}).get("GRACE_MS", status.get("GRACE_MS",800))), step=10)

    if st.button("Apply Controls", type="primary"):
        merge_control({
            "balance_mode": balance_mode,
            "poll_s": poll_s,
            "risk_poll_s": risk_poll_s,
            "thresh_pct": thresh_pct,
            "min_notional_ars": min_notional_ars,
            "EDGE_TOL_BPS": edge_tol_bps,
            "UNWIND_MODE": unwind_mode,
            "WAIT_MS": wait_ms,
            "GRACE_MS": grace_ms
        })
        st.success("Controls applied")

# ======== SAFETY ========
with tab_safety:
    st.subheader("Risk & Execution")
    st.caption("Caps diarios y por símbolo — placeholders visuales; el core ya limita por profundidad y saldo.")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.number_input("Daily Notional Cap (ARS) [placeholder]", min_value=0.0, value=0.0, step=100000.0)
    with col2:
        st.number_input("Per-Trade Cap (ARS) [placeholder]", min_value=0.0, value=0.0, step=10000.0)
    with col3:
        st.number_input("Max Pending per Symbol [placeholder]", min_value=0, value=0, step=1)
    st.info("Los caps reales por profundidad y saldo se aplican automáticamente en el core.")

# ======== TRACE ========
with tab_trace:
    st.subheader("Trace & Audit")
    trace_enabled = st.checkbox("trace_enabled", value=bool(status.get("trace_enabled", False)))
    trace_raw = st.checkbox("trace_raw (raw MD/ER)", value=bool(status.get("trace_raw", False)))
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("Apply Trace Flags"):
            merge_control({"trace_enabled": trace_enabled, "trace_raw": trace_raw}); st.success("Trace updated")
    with col_b:
        if st.button("Rotate Trace"):
            merge_control({"trace_rotate": True}); st.success("Rotation requested")
    with col_c:
        if st.button("Clear Trace"):
            try:
                if os.path.exists(TRACE_PATH_DEF):
                    open(TRACE_PATH_DEF, "w").close()
                st.success("Trace cleared")
            except Exception as e:
                st.error(f"Failed: {e}")

    st.caption(f"File: {trace_path} — Size: {human_size(trace_size)}")
    if os.path.exists(trace_path):
        try:
            with open(trace_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-200:]
            st.text_area("Last 200 lines", value="".join(lines), height=240)
        except Exception as e:
            st.warning(f"Cannot read trace: {e}")

# ======== LOGS ========
with tab_logs:
    st.subheader("Live Trades")
    if os.path.exists(TRADES_CSV):
        try:
            df = pd.read_csv(TRADES_CSV)
            st.dataframe(df.tail(300), use_container_width=True, height=300)
        except Exception as e:
            st.warning(f"Cannot read {TRADES_CSV}: {e}")
    else:
        st.info("No trades yet.")

    st.subheader("Execution Reports")
    if os.path.exists(ER_CSV):
        try:
            df2 = pd.read_csv(ER_CSV)
            st.dataframe(df2.tail(300), use_container_width=True, height=300)
        except Exception as e:
            st.warning(f"Cannot read {ER_CSV}: {e}")
    else:
        st.info("No execution reports yet.")

# ======== HEALTH ========
with tab_health:
    st.subheader("Health")
    st.write(f"Ref Pair: **{status.get('ref_pair',{}).get('ars','?')} / {status.get('ref_pair',{}).get('usd','?')}**")
    st.write(f"Ref Mode: **{status.get('ref_mode','-')}** — Half-Life (s): **{status.get('half_life_s','-')}** — Ref Tune: **{status.get('ref_tune','-')}**")
    st.write(f"Latency Probe (s): **{status.get('lat_probe_s','-')}** — K: **{status.get('ref_k','-')}** — Min/Max HL: **{status.get('ref_min','-')} / {status.get('ref_max','-')}**")
    st.caption("Sugerencia: si ves mucho flicker del MEP instantáneo, subí HALF_LIFE_S o activá REF_TUNE.")
