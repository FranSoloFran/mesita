# ui/streamlit_app.py
import base64
import json
import os
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
ENV_FILE        = ".env"

st.set_page_config(page_title="Mesita — Control Panel", layout="wide")

# ---------------- helpers ----------------
def load_json(path: str) -> dict:
    if not os.path.exists(path): return {}
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def save_json(path: str, obj: dict):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def merge_control(overrides: dict):
    cur = load_json(CONTROL_JSON); cur.update(overrides); save_json(CONTROL_JSON, cur)

def human_size(n: int | None) -> str:
    if n is None: return "n/a"
    units = ["B","KB","MB","GB","TB"]; x=float(n); i=0
    while x>=1024 and i<len(units)-1: x/=1024.0; i+=1
    return f"{x:.1f} {units[i]}"

def write_env(env_map: dict):
    # merge style: reescribe claves conocidas, preserva el resto si existen
    existing = {}
    if os.path.exists(ENV_FILE):
        try:
            for line in Path(ENV_FILE).read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.strip().startswith("#"): continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()
        except Exception:
            pass
    existing.update(env_map)
    lines = [f"{k}={v}" for k,v in existing.items()]
    Path(ENV_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")

def ref_values_from_status(status: dict):
    mode = status.get("ref_mode", "tick")
    a2u_inst = status.get("ref_inst_a2u"); a2u_ema = status.get("ref_ema_a2u")
    u2a_inst = status.get("ref_inst_u2a"); u2a_ema = status.get("ref_ema_u2a")
    if mode == "tick": return a2u_inst, u2a_inst
    a2u = [x for x in (a2u_inst, a2u_ema) if x is not None]
    u2a = [x for x in (u2a_inst, u2a_ema) if x is not None]
    return (min(a2u) if a2u else None, max(u2a) if u2a else None)

# ---------------- sidebar ----------------
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

# ---------------- main ----------------
st.title("Mesita — Control Panel")

tab_market, tab_positions, tab_ref, tab_ctrl, tab_safety, tab_trace, tab_logs, tab_health, tab_accounts = st.tabs(
    ["Market", "Positions", "Reference & Latency", "Controls", "Safety", "Trace", "Logs", "Health", "Accounts"]
)

# ========== MARKET ==========
with tab_market:
    st.subheader("Top-of-Book (Live)")
    bj = load_json(BOOKS_JSON); books = bj.get("books", {})
    if not books:
        st.info("No live books yet.")
    else:
        df = (pd.DataFrame.from_dict(books, orient="index").reset_index()
              .rename(columns={"index":"Symbol","bid":"Bid","ask":"Ask","bid_qty":"BidQty","ask_qty":"AskQty","ts":"TS"}))
        col1, col2, col3 = st.columns([1,1,2])
        side = col1.selectbox("Side", ["All","ARS leg","USD leg"], index=0)
        sort_col = col2.selectbox("Sort by", ["Symbol","Bid","Ask","BidQty","AskQty"], index=0)
        q = col3.text_input("Filter (substring)", "")
        if side == "ARS leg":
            df = df[~df["Symbol"].str.upper().str.endswith("D")]
        elif side == "USD leg":
            df = df[df["Symbol"].str.upper().str.endswith("D")]
        if q: df = df[df["Symbol"].str.contains(q, case=False)]
        st.dataframe(df.sort_values(by=sort_col), use_container_width=True, height=420)

# ========== POSITIONS ==========
with tab_positions:
    st.subheader("Positions & Cash")
    pj = load_json(POSITIONS_JSON)
    st.write(f"**Cash ARS:** {pj.get('cash_ars', status.get('cash_ars'))} — **Cash USD:** {pj.get('cash_usd', status.get('cash_usd'))}")
    pos = pj.get("positions", {})
    if pos:
        pdf = pd.DataFrame([{"Symbol":k,"Qty":v} for k,v in pos.items()]).sort_values("Symbol")
        st.dataframe(pdf, use_container_width=True, height=300)
    else:
        st.info("No positions reported yet.")

# ========== REFERENCE & LATENCY ==========
with tab_ref:
    st.subheader("MEP Reference & Auto-Tune")
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        rp = status.get("ref_pair", {})
        st.metric("Ref Pair (ARS/USD)", f"{rp.get('ars','?')} / {rp.get('usd','?')}")
        st.write(f"Instant A2U: **{status.get('ref_inst_a2u','-')}**")
        st.write(f"EMA A2U: **{status.get('ref_ema_a2u','-')}**")
    with col_r2:
        st.metric("Ref Mode", status.get("ref_mode","-"))
        st.write(f"Instant U2A: **{status.get('ref_inst_u2a','-')}**")
        st.write(f"EMA U2A: **{status.get('ref_ema_u2a','-')}**")

    st.divider()
    st.subheader("Parameters")
    ref_mode = st.selectbox("REF_MODE", options=["tick","hybrid"], index=0 if status.get("ref_mode","tick")=="tick" else 1)
    cols = st.columns(4)
    with cols[0]:
        ref_tune = st.checkbox("REF_TUNE (Auto-Adjust EMA)", value=bool(status.get("ref_tune", True)))
    with cols[1]:
        half_life_s = st.slider("HALF_LIFE_S (if REF_TUNE=off)", 0.0, 30.0, float(status.get("half_life_s",7.0)), 0.5)
    with cols[2]:
        ref_k = st.slider("REF_K (≈ K × median RTT s)", 1.0, 10.0, float(status.get("ref_k",4.0)), 0.5)
    with cols[3]:
        lat_probe_s = st.slider("LAT_PROBE_S (s)", 2.0, 60.0, float(status.get("lat_probe_s",10.0)), 1.0)

    col_min, col_max = st.columns(2)
    with col_min:
        ref_min_hl = st.slider("REF_MIN_HL_S", 0.0, 30.0, float(status.get("ref_min",2.0)), 0.5)
    with col_max:
        ref_max_hl = st.slider("REF_MAX_HL_S", 0.0, 60.0, float(status.get("ref_max",20.0)), 0.5)

    if st.button("Apply Reference/Latency", type="primary"):
        payload = {"REF_MODE":ref_mode,"REF_TUNE":ref_tune,"REF_K":ref_k,"REF_MIN_HL_S":ref_min_hl,"REF_MAX_HL_S":ref_max_hl,"LAT_PROBE_S":lat_probe_s}
        if not ref_tune: payload["HALF_LIFE_S"] = half_life_s
        merge_control(payload); st.success("Reference/Latency applied")

# ========== CONTROLS ==========
with tab_ctrl:
    st.subheader("General Controls")
    col1, col2, col3 = st.columns(3)
    with col1:
        balance_mode = st.selectbox("Balance Mode", ["risk_poll","er_reconcile"], index=0 if status.get("source","risk_poll")=="risk_poll" else 1)
        poll_s = st.number_input("poll_s (s)", 0.01, 2.0, float(status.get("poll_s",0.2)), 0.01)
        risk_poll_s = st.number_input("risk_poll_s (s)", 0.05, 5.0, float(status.get("risk_poll_s",0.5)), 0.05)
    with col2:
        thresh_pct = st.number_input("Threshold (fraction)", 0.0001, 0.01, float(status.get("thresh_pct",0.002)), 0.0001, format="%.4f")
        min_notional_ars = st.number_input("Min Notional ARS", 10000.0, 5_000_000.0, float(status.get("min_notional_ars",40000.0)), 1000.0)
        edge_tol_bps = st.number_input("Edge Tolerance (bps)", 0.0, 10.0, float(status.get("EDGE_TOL_BPS",1.0)), 0.1)
    with col3:
        unwind_mode = st.selectbox("Unwind Mode", ["smart","always","none"], index=["smart","always","none"].index(status.get("UNWIND_MODE","smart")))
        wait_ms  = st.number_input("WAIT_MS (ms)", 0, 5000, int(status.get("WAIT_MS",120)), 10)
        grace_ms = st.number_input("GRACE_MS (ms)", 0, 5000, int(status.get("GRACE_MS",800)), 10)

    if st.button("Apply Controls", type="primary"):
        merge_control({"balance_mode":balance_mode,"poll_s":poll_s,"risk_poll_s":risk_poll_s,"thresh_pct":thresh_pct,
                       "min_notional_ars":min_notional_ars,"EDGE_TOL_BPS":edge_tol_bps,
                       "UNWIND_MODE":unwind_mode,"WAIT_MS":wait_ms,"GRACE_MS":grace_ms})
        st.success("Controls applied")

# ========== SAFETY ==========
with tab_safety:
    st.subheader("Risk & Execution")
    st.caption("Caps diarios/por símbolo — placeholders: el core ya limita por profundidad y saldo.")
    c1,c2,c3 = st.columns(3)
    c1.number_input("Daily Notional Cap (ARS) [placeholder]", 0.0, value=0.0, step=100000.0)
    c2.number_input("Per-Trade Cap (ARS) [placeholder]", 0.0, value=0.0, step=10000.0)
    c3.number_input("Max Pending per Symbol [placeholder]", 0, value=0, step=1)

# ========== TRACE ==========
with tab_trace:
    st.subheader("Trace & Audit")
    trace_enabled = st.checkbox("trace_enabled", value=bool(status.get("trace_enabled", False)))
    trace_raw = st.checkbox("trace_raw (raw MD/ER)", value=bool(status.get("trace_raw", False)))
    a,b,c = st.columns(3)
    if a.button("Apply Trace Flags"): merge_control({"trace_enabled":trace_enabled,"trace_raw":trace_raw}); st.success("Trace updated")
    if b.button("Rotate Trace"): merge_control({"trace_rotate": True}); st.success("Rotation requested")
    if c.button("Clear Trace"):
        try:
            if os.path.exists(TRACE_PATH_DEF): open(TRACE_PATH_DEF,"w").close()
            st.success("Trace cleared")
        except Exception as e: st.error(f"Failed: {e}")
    try:
        tsz = Path(trace_path).stat().st_size if os.path.exists(trace_path) else None
    except Exception: tsz = None
    st.caption(f"File: {trace_path} — Size: {human_size(tsz)}")
    if os.path.exists(trace_path):
        try:
            with open(trace_path,"r",encoding="utf-8") as f: lines=f.readlines()[-200:]
            st.text_area("Last 200 lines", value="".join(lines), height=240)
        except Exception as e: st.warning(f"Cannot read trace: {e}")

# ========== LOGS ==========
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

# ========== HEALTH ==========
with tab_health:
    st.subheader("Health")
    rp = status.get("ref_pair", {})
    st.write(f"Ref Pair: **{rp.get('ars','?')} / {rp.get('usd','?')}**")
    st.write(f"Ref Mode: **{status.get('ref_mode','-')}** — Half-Life (s): **{status.get('half_life_s','-')}** — Ref Tune: **{status.get('ref_tune','-')}**")
    st.write(f"Latency Probe (s): **{status.get('lat_probe_s','-')}** — K: **{status.get('ref_k','-')}** — Min/Max HL: **{status.get('ref_min','-')} / {status.get('ref_max','-')}**")

# ========== ACCOUNTS (NUEVO) ==========
with tab_accounts:
    st.subheader("Accounts & Credentials")
    st.caption("Se guardan en **.env** (texto plano). Úsalo en servidor controlado.")
    env_current = status.get("env", "paper")
    env_sel = st.selectbox("Environment", ["paper","live"], index=0 if env_current=="paper" else 1, help="Afecta `settings.env`.")

    # inputs
    st.markdown("**Paper Credentials**")
    colp1, colp2, colp3 = st.columns(3)
    paper_user = colp1.text_input("primary_paper_username", value=os.getenv("PRIMARY_PAPER_USERNAME",""))
    paper_pass = colp2.text_input("primary_paper_password", type="password", value=os.getenv("PRIMARY_PAPER_PASSWORD",""))
    paper_acct = colp3.text_input("account_paper", value=os.getenv("ACCOUNT_PAPER",""))

    st.markdown("**Live Credentials**")
    coll1, coll2, coll3 = st.columns(3)
    live_user = coll1.text_input("primary_live_username", value=os.getenv("PRIMARY_LIVE_USERNAME",""))
    live_pass = coll2.text_input("primary_live_password", type="password", value=os.getenv("PRIMARY_LIVE_PASSWORD",""))
    live_acct = coll3.text_input("account_live", value=os.getenv("ACCOUNT_LIVE",""))

    st.markdown("**Other**")
    colx1, colx2 = st.columns(2)
    proprietary = colx1.text_input("proprietary_tag", value=os.getenv("PROPRIETARY_TAG","PBCP"))
    base_override = colx2.text_input("primary_base_url (opt)", value=os.getenv("PRIMARY_BASE_URL",""))
    ws_override   = st.text_input("primary_ws_url (opt)", value=os.getenv("PRIMARY_WS_URL",""))

    # actions
    a1, a2, a3 = st.columns(3)
    if a1.button("Save Credentials (.env)", type="primary"):
        write_env({
            "ENV": env_sel,
            "PRIMARY_PAPER_USERNAME": paper_user,
            "PRIMARY_PAPER_PASSWORD": paper_pass,
            "ACCOUNT_PAPER": paper_acct,
            "PRIMARY_LIVE_USERNAME": live_user,
            "PRIMARY_LIVE_PASSWORD": live_pass,
            "ACCOUNT_LIVE": live_acct,
            "PROPRIETARY_TAG": proprietary,
            "PRIMARY_BASE_URL": base_override,
            "PRIMARY_WS_URL": ws_override,
        })
        st.success("Saved to .env. Reinicia el bot live para aplicar, o usa 'Apply & Switch Env (Hot)'.")
    if a2.button("Apply & Switch Env (Hot)"):
        merge_control({
            "env": env_sel,
            "primary_paper_username": paper_user,
            "primary_paper_password": paper_pass,
            "account_paper": paper_acct,
            "primary_live_username": live_user,
            "primary_live_password": live_pass,
            "account_live": live_acct,
            "proprietary_tag": proprietary,
            "primary_base_url": base_override,
            "primary_ws_url": ws_override,
        })
        st.success("Overrides enviados. El loop debería tomar nuevas credenciales y endpoints en caliente.")
    if a3.button("Logout Now"):
        merge_control({"panic_stop": True, "force_flatten": True})
        st.warning("Panic + Flatten enviados. (Opcional: puedo agregar 'force_reauth' para re-login automático.)")
