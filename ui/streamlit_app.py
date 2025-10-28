import base64
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
BOOKS_JSON      = "assets/plots/books.json"
POSITIONS_JSON  = "assets/plots/positions.json"

st.set_page_config(page_title="Mesita — Control Panel", layout="wide")

# ---------------------- helpers ----------------------
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

def is_usd_sym(sym: str) -> bool:
    return sym.upper().endswith("D")

def ref_values_from_status(status: dict):
    mode = status.get("ref_mode", "tick")
    a2u_inst = status.get("ref_inst_a2u")
    a2u_ema  = status.get("ref_ema_a2u")
    u2a_inst = status.get("ref_inst_u2a")
    u2a_ema  = status.get("ref_ema_u2a")

    if mode == "tick":
        return a2u_inst, u2a_inst
    # hybrid: conservador
    a2u_candidates = [x for x in (a2u_inst, a2u_ema) if x is not None]
    u2a_candidates = [x for x in (u2a_inst, u2a_ema) if x is not None]
    a2u_ref = min(a2u_candidates) if a2u_candidates else None
    u2a_ref = max(u2a_candidates) if u2a_candidates else None
    return a2u_ref, u2a_ref

# sounds: cortos WAV embebidos (placeholders)
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")

# tonos simples (beeps) generados previamente; placeholders muy livianos
BEEP_EDGE = _b64(b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
BEEP_OPEN = _b64(b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
BEEP_WIN  = _b64(b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
BEEP_LOSS = _b64(b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
BEEP_FLAT = _b64(b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

def inject_audio_players():
    st.markdown(
        f"""
        <audio id="snd_edge"  src="data:audio/wav;base64,{BEEP_EDGE}" preload="auto"></audio>
        <audio id="snd_open"  src="data:audio/wav;base64,{BEEP_OPEN}" preload="auto"></audio>
        <audio id="snd_win"   src="data:audio/wav;base64,{BEEP_WIN}"  preload="auto"></audio>
        <audio id="snd_loss"  src="data:audio/wav;base64,{BEEP_LOSS}" preload="auto"></audio>
        <audio id="snd_flat"  src="data:audio/wav;base64,{BEEP_FLAT}" preload="auto"></audio>
        <script>
          window.mesita_play = function(kind){{
            try {{
              const id = {{
                edge: 'snd_edge',
                open: 'snd_open',
                win:  'snd_win',
                loss: 'snd_loss',
                flat: 'snd_flat'
              }}[kind] || 'snd_edge';
              const el = document.getElementById(id);
              if (el) el.play().catch(()=>{{}});
            }} catch(e) {{}}
          }};
        </script>
        """,
        unsafe_allow_html=True
    )

def fire_sound(kind: str):
    st.markdown(f"<script>window.mesita_play('{kind}');</script>", unsafe_allow_html=True)

# ---------------------- sidebar ----------------------
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

# ---------------------- main ----------------------
st.title("Mesita — Control Panel")

tab_market, tab_positions, tab_ref, tab_ctrl, tab_safety, tab_trace, tab_logs, tab_health = st.tabs(
    ["Market", "Positions", "Reference & Latency", "Controls", "Safety", "Trace", "Logs", "Health"]
)

inject_audio_players()  # audio elements + js

# ========= MARKET =========
with tab_market:
    st.subheader("Top-of-Book (Live) & Edge Alerts")

    bj = load_json(BOOKS_JSON)
    books = bj.get("books", {})
    if not books:
        st.info("No live books yet.")
    else:
        df = (
            pd.DataFrame.from_dict(books, orient="index")
            .reset_index()
            .rename(columns={"index":"Symbol", "bid":"Bid", "ask":"Ask", "bid_qty":"BidQty", "ask_qty":"AskQty", "ts":"TS"})
        )

        # filtros
        col1, col2, col3, col4 = st.columns([1,1,2,2])
        with col1:
            side_filter = st.selectbox("Side", ["All", "ARS leg", "USD leg"], index=0)
        with col2:
            sort_col = st.selectbox("Sort by", ["Symbol","Bid","Ask","BidQty","AskQty"], index=0)
        with col3:
            query = st.text_input("Filter (substring)", "")
        with col4:
            edge_bps_threshold = st.slider("Edge Alert Threshold (bps)", min_value=5, max_value=200, value=20, step=5)

        if side_filter == "ARS leg":
            df = df[~df["Symbol"].str.upper().str.endswith("D")]
        elif side_filter == "USD leg":
            df = df[df["Symbol"].str.upper().str.endswith("D")]

        if query:
            df = df[df["Symbol"].str.contains(query, case=False)]

        df = df.sort_values(by=sort_col, ascending=True)
        st.dataframe(df, use_container_width=True, height=380)

        # ---- edge detection over pairs (heurístico SIMB / SIMBD) ----
        a2u_ref, u2a_ref = ref_values_from_status(status)
        if a2u_ref and u2a_ref:
            # build quick lookup
            books_map = books
            edges_fired = 0
            # pair by "X" and "XD"
            base_syms = [s for s in books_map.keys() if not is_usd_sym(s)]
            for s in base_syms:
                sd = s + "D"
                qa = books_map.get(s)     # ARS leg
                qu = books_map.get(sd)    # USD leg
                if not qa or not qu:
                    continue
                # implieds
                try:
                    implied_a2u = (float(qa["ask"]) / float(qu["bid"])) if (qa["ask"]>0 and qu["bid"]>0) else None
                    implied_u2a = (float(qa["bid"]) / float(qu["ask"])) if (qa["bid"]>0 and qu["ask"]>0) else None
                except Exception:
                    implied_a2u = None; implied_u2a = None

                # edges en bps (solo si hay ref + implied)
                if implied_a2u and a2u_ref:
                    edge_bps = (a2u_ref - implied_a2u) / a2u_ref * 1e4
                    if edge_bps >= edge_bps_threshold:
                        st.toast(f"EDGE A2U {s}:{sd} = {edge_bps:.1f} bps (Implied {implied_a2u:.2f} < Ref {a2u_ref:.2f})", icon="✅")
                        fire_sound("edge"); edges_fired += 1
                if implied_u2a and u2a_ref:
                    edge_bps = (implied_u2a - u2a_ref) / u2a_ref * 1e4
                    if edge_bps >= edge_bps_threshold:
                        st.toast(f"EDGE U2A {s}:{sd} = {edge_bps:.1f} bps (Implied {implied_u2a:.2f} > Ref {u2a_ref:.2f})", icon="✅")
                        fire_sound("edge"); edges_fired += 1

            if edges_fired == 0:
                st.caption("No edge above threshold right now.")

# ========= POSITIONS =========
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

# ========= REFERENCE & LATENCY =========
with tab_ref:
    st.subheader("MEP Reference & Auto-Tune by Latency")

    # live reference display
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        ref_pair = status.get("ref_pair", {})
        st.metric("Ref Pair (ARS/USD)", f"{ref_pair.get('ars','?')} / {ref_pair.get('usd','?')}")
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

# ========= CONTROLS =========
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

# ========= SAFETY =========
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

# ========= TRACE =========
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

    try:
        trace_size = Path(trace_path).stat().st_size if os.path.exists(trace_path) else None
    except Exception:
        trace_size = None
    st.caption(f"File: {trace_path} — Size: {human_size(trace_size)}")
    if os.path.exists(trace_path):
        try:
            with open(trace_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-200:]
            st.text_area("Last 200 lines", value="".join(lines), height=240)
        except Exception as e:
            st.warning(f"Cannot read trace: {e}")

# ========= LOGS + ALERTS =========
with tab_logs:
    st.subheader("Live Trades")
    last_trades_seen = st.session_state.get("last_trades_rows", 0)
    trades_now = 0
    if os.path.exists(TRADES_CSV):
        try:
            df = pd.read_csv(TRADES_CSV)
            trades_now = len(df)
            st.dataframe(df.tail(300), use_container_width=True, height=300)
            # alertas por nuevos trades
            if trades_now > last_trades_seen:
                new_rows = trades_now - last_trades_seen
                st.toast(f"New trade(s): {new_rows}", icon="📈")
                fire_sound("open")
        except Exception as e:
            st.warning(f"Cannot read {TRADES_CSV}: {e}")
    else:
        st.info("No trades yet.")
    st.session_state["last_trades_rows"] = trades_now

    st.subheader("Execution Reports")
    last_er_seen = st.session_state.get("last_er_rows", 0)
    er_now = 0
    if os.path.exists(ER_CSV):
        try:
            df2 = pd.read_csv(ER_CSV)
            er_now = len(df2)
            st.dataframe(df2.tail(300), use_container_width=True, height=300)
            # alertas por nuevos ER
            if er_now > last_er_seen:
                # chequear últimos eventos para elegir sonido
                tail = df2.tail(er_now - last_er_seen)
                # esperamos columnas: status / side / symbol / price / qty
                for _, r in tail.iterrows():
                    status_str = str(r.get("status","")).upper()
                    sym = r.get("symbol","")
                    if status_str == "FILLED":
                        st.toast(f"FILLED {sym}", icon="✅"); fire_sound("win")
                    elif status_str in ("CANCELED","CANCELLED"):
                        st.toast(f"CANCELED {sym}", icon="⚠️"); fire_sound("flat")
                    elif status_str in ("REJECTED","REJ"):
                        st.toast(f"REJECTED {sym}", icon="❌"); fire_sound("loss")
                    else:
                        st.toast(f"{status_str} {sym}", icon="ℹ️")
        except Exception as e:
            st.warning(f"Cannot read {ER_CSV}: {e}")
    else:
        st.info("No execution reports yet.")
    st.session_state["last_er_rows"] = er_now

# ========= HEALTH =========
with tab_health:
    st.subheader("Health")
    st.write(f"Ref Pair: **{status.get('ref_pair',{}).get('ars','?')} / {status.get('ref_pair',{}).get('usd','?')}**")
    st.write(f"Ref Mode: **{status.get('ref_mode','-')}** — Half-Life (s): **{status.get('half_life_s','-')}** — Ref Tune: **{status.get('ref_tune','-')}**")
    st.write(f"Latency Probe (s): **{status.get('lat_probe_s','-')}** — K: **{status.get('ref_k','-')}** — Min/Max HL: **{status.get('ref_min','-')} / {status.get('ref_max','-')}**")
    st.caption("Sugerencia: si ves mucho flicker del MEP instantáneo, subí HALF_LIFE_S o activá REF_TUNE.")
