import json
import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

STATUS_JSON = "assets/plots/status.json"
CONTROL_JSON = "assets/plots/control.json"
TRACE_PATH_DEFAULT = "assets/plots/trace.log"
TRADES_CSV = "assets/plots/live_trades.csv"
ER_CSV = "assets/plots/execution_reports.csv"

st.set_page_config(page_title="mesita ui", layout="wide")

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

def human_size(bytes_val: int) -> str:
    if bytes_val is None:
        return "n/a"
    units = ["B","KB","MB","GB","TB"]
    x = float(bytes_val)
    i = 0
    while x >= 1024 and i < len(units)-1:
        x /= 1024.0
        i += 1
    return f"{x:.1f} {units[i]}"

# --- sidebar: status live ---
st.sidebar.title("estado")
status = load_json(STATUS_JSON)
st.sidebar.write(f"modo balance: **{status.get('source','?')}**")
st.sidebar.write(f"trading enabled: **{status.get('trading_enabled', False)}**")
st.sidebar.write(f"cash ars: **{status.get('cash_ars','?')}**")
st.sidebar.write(f"cash usd: **{status.get('cash_usd','?')}**")
st.sidebar.write(f"ref mode: **{status.get('ref_mode','?')}**")
st.sidebar.write(f"half-life s: **{status.get('half_life_s','?')}**")
st.sidebar.write(f"ref tune: **{status.get('ref_tune','?')}**")
st.sidebar.caption(f"ts: {status.get('ts','-')}")

trace_path = status.get("trace_path", TRACE_PATH_DEFAULT)
try:
    trace_size = Path(trace_path).stat().st_size if os.path.exists(trace_path) else None
except Exception:
    trace_size = None
st.sidebar.write(f"trace: **{human_size(trace_size)}**")

with st.sidebar.expander("acciones rápidas"):
    col_a, col_b = st.columns(2)
    if col_a.button("panic stop", use_container_width=True):
        merge_control({"panic_stop": True})
        st.success("panic enviado")
    if col_b.button("resume", use_container_width=True):
        merge_control({"resume": True})
        st.success("resume enviado")
    col_c, col_d = st.columns(2)
    if col_c.button("reload instruments", use_container_width=True):
        merge_control({"reload_instruments_now": True})
        st.success("reload enviado")
    if col_d.button("force flatten", use_container_width=True):
        merge_control({"force_flatten": True})
        st.success("flatten enviado")

# --- main layout ---
st.title("mesita — control panel")

tab_ctrl, tab_ref, tab_safety, tab_trace, tab_logs = st.tabs(
    ["controles", "referencia/latencia", "riesgos/ejecución", "trace", "logs"]
)

# -------- controles generales --------
with tab_ctrl:
    st.subheader("parámetros generales")
    col1, col2, col3 = st.columns(3)

    with col1:
        balance_mode = st.selectbox(
            "balance mode",
            options=["risk_poll", "er_reconcile"],
            index=0 if status.get("source","risk_poll") == "risk_poll" else 1,
            help="risk_poll: lee cash del api cada X seg. er_reconcile: usa fills en vivo + refresh periódico."
        )
        poll_s = st.number_input("poll_s (loop sleep, seg)", min_value=0.01, max_value=2.0, value=float(status.get("overrides",{}).get("poll_s", status.get("poll_s",0.2))), step=0.01)
        risk_poll_s = st.number_input("risk_poll_s (seg)", min_value=0.05, max_value=5.0, value=float(status.get("risk_poll_s",0.5)), step=0.05)

    with col2:
        thresh_pct = st.number_input("umbral (fracción, ej 0.002=20 bps)", min_value=0.0001, max_value=0.01, value=float(status.get("overrides",{}).get("thresh_pct", status.get("thresh_pct",0.002))), step=0.0001, format="%.4f")
        min_notional_ars = st.number_input("min_notional_ars", min_value=10000.0, max_value=5_000_000.0, value=float(status.get("overrides",{}).get("min_notional_ars", status.get("min_notional_ars",40000.0))), step=1000.0)
        edge_tol_bps = st.number_input("edge_tol_bps (para unwind smart)", min_value=0.0, max_value=10.0, value=float(status.get("overrides",{}).get("EDGE_TOL_BPS", status.get("EDGE_TOL_BPS",1.0))), step=0.1)

    with col3:
        unwind_mode = st.selectbox("unwind_mode", options=["smart","always","none"], index=["smart","always","none"].index(status.get("UNWIND_MODE","smart")))
        wait_ms  = st.number_input("WAIT_MS (ms)", min_value=0, max_value=5000, value=int(status.get("overrides",{}).get("WAIT_MS", status.get("WAIT_MS",120))), step=10)
        grace_ms = st.number_input("GRACE_MS (ms)", min_value=0, max_value=5000, value=int(status.get("overrides",{}).get("GRACE_MS", status.get("GRACE_MS",800))), step=10)

    if st.button("aplicar controles", type="primary"):
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
        st.success("controles aplicados")

# -------- referencia / latencia --------
with tab_ref:
    st.subheader("referencia mep & auto-tune por latencia")

    ref_mode = st.selectbox(
        "REF_MODE",
        options=["tick","hybrid"],
        index=0 if status.get("ref_mode","tick")=="tick" else 1,
        help="tick: usa solo el mep instantáneo. hybrid: combina instantáneo con EMA temporal (min/max)."
    )

    cols = st.columns(4)
    with cols[0]:
        ref_tune = st.checkbox("REF_TUNE (auto-ajustar EMA)", value=bool(status.get("ref_tune", True)))
    with cols[1]:
        half_life_s = st.slider("HALF_LIFE_S (si REF_TUNE=off)", min_value=0.0, max_value=30.0, value=float(status.get("half_life_s",7.0)), step=0.5)
    with cols[2]:
        ref_k = st.slider("REF_K (hl ≈ K × median_rtt_s)", min_value=1.0, max_value=10.0, value=float(status.get("ref_k",4.0)), step=0.5)
    with cols[3]:
        lat_probe_s = st.slider("LAT_PROBE_S (seg)", min_value=2.0, max_value=60.0, value=float(status.get("lat_probe_s",10.0)), step=1.0)

    col_min, col_max = st.columns(2)
    with col_min:
        ref_min_hl = st.slider("REF_MIN_HL_S", min_value=0.0, max_value=30.0, value=float(status.get("ref_min",2.0)), step=0.5)
    with col_max:
        ref_max_hl = st.slider("REF_MAX_HL_S", min_value=0.0, max_value=60.0, value=float(status.get("ref_max",20.0)), step=0.5)

    if st.button("aplicar referencia/latencia", type="primary"):
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
        st.success("referencia/latencia aplicadas")

# -------- riesgos / ejecución (caps y límites) --------
with tab_safety:
    st.subheader("riesgo y ejecución")
    st.caption("ajustes finos; si querés límites diarios/notionales, agregalos acá cuando estén soportados por el core.")
    col1, col2, col3 = st.columns(3)
    with col1:
        # placeholders para futuros caps diarios / por símbolo
        st.number_input("cap notional diario (ars) [placeholder]", min_value=0.0, value=0.0, step=100000.0)
    with col2:
        st.number_input("cap por trade (ars) [placeholder]", min_value=0.0, value=0.0, step=10000.0)
    with col3:
        st.number_input("max pendientes por símbolo [placeholder]", min_value=0, value=0, step=1)
    st.info("estos caps son placeholders visuales; el core aplicará los caps por profundidad y saldo automáticamente.")

# -------- trace --------
with tab_trace:
    st.subheader("trace y auditoría")
    trace_enabled = st.checkbox("trace_enabled", value=bool(status.get("trace_enabled", False)))
    trace_raw = st.checkbox("trace_raw (md/er crudo)", value=bool(status.get("trace_raw", False)))
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("aplicar trace flags"):
            merge_control({"trace_enabled": trace_enabled, "trace_raw": trace_raw})
            st.success("trace actualizado")
    with col_b:
        if st.button("rotar trace"):
            # señal al proceso para que rote (interpreta control y rota)
            merge_control({"trace_rotate": True})
            st.success("pedido de rotación enviado")
    with col_c:
        if st.button("limpiar trace"):
            try:
                if os.path.exists(TRACE_PATH_DEFAULT):
                    open(TRACE_PATH_DEFAULT, "w").close()
                st.success("trace limpiado")
            except Exception as e:
                st.error(f"no se pudo limpiar: {e}")

    st.caption(f"archivo: {trace_path} — tamaño: {human_size(trace_size)}")
    # preview tail (si existe)
    if os.path.exists(trace_path):
        try:
            with open(trace_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-200:]
            st.text_area("últimas 200 líneas", value="".join(lines), height=240)
        except Exception as e:
            st.warning(f"no se pudo leer el trace: {e}")

# -------- logs (trades y er) --------
with tab_logs:
    st.subheader("trades en vivo")
    if os.path.exists(TRADES_CSV):
        try:
            df = pd.read_csv(TRADES_CSV)
            st.dataframe(df.tail(300), use_container_width=True, height=300)
        except Exception as e:
            st.warning(f"no se pudo leer {TRADES_CSV}: {e}")
    else:
        st.info("aún no hay trades.")

    st.subheader("execution reports")
    if os.path.exists(ER_CSV):
        try:
            df2 = pd.read_csv(ER_CSV)
            st.dataframe(df2.tail(300), use_container_width=True, height=300)
        except Exception as e:
            st.warning(f"no se pudo leer {ER_CSV}: {e}")
    else:
        st.info("aún no hay execution reports.")

st.caption("tip: la ui escribe overrides en assets/plots/control.json; el bot los lee y aplica en caliente.")
