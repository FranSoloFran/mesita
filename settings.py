from pydantic import BaseSettings
from typing import Tuple

class Settings(BaseSettings):
    env: str = "paper"                 # paper | live - paper para cuenta de Remarkets y live para cuenta con guita real
    poll_s: float = 0.2
    primary_timeout_s: float = 3.0

    primary_base_url: str = ""
    primary_ws_url: str = ""

    primary_paper_username: str = ""
    primary_paper_password: str = ""
    primary_live_username: str = ""
    primary_live_password: str = ""

    account_paper: str = ""
    account_live: str = ""
    proprietary_tag: str = "PBCP"      # o ISV_PBCP

    min_notional_ars: float = 40000.0 # monto operable en pesos debe ser mayor o igual a $40000
    thresh_pct: float = 0.002 # 0,2% tipo de cambio minimo por debajo del mep de referencia
    cost_bps: float = 0.0 # por defecto sin comisión (veta flat). si fuera con comisión por ej. 0,15%, poner 15
    slip_bps: float = 0.0 # deslizamiento de precio para el backtesting, si fuera por ej 0.08% poner 8

    balance_mode: str = "risk_poll"    # risk_poll | er_reconcile
    risk_poll_s: float = 0.5
    risk_refresh_s: float = 30.0

    instrument_refresh_s: float = 24*60*60

    # sync / unwind
    WAIT_MS: int = 120
    GRACE_MS: int = 800
    EDGE_TOL_BPS: float = 1.0
    UNWIND_MODE: str = "smart"         # smart | always | none

    # reference mode
    REF_MODE: str = "hybrid"           # "tick" (instantáneo) | "hybrid" (inst + ema) esto depende de la latencia
    HALF_LIFE_S: float = 7.0           # half-life de la ema temporal (segundos)

    # ui control file
    control_path: str = "assets/plots/control.json"

    # trace
    trace_enabled: bool = False
    trace_path: str = "assets/plots/trace.log"
    trace_rotate_mb: int = 20
    trace_raw: bool = False

    class Config:
        env_file = ".env"

    def urls(self) -> Tuple[str, str]:
        if self.env.lower() == "paper":
            rest = "https://api.remarkets.primary.com.ar"
            ws   = "wss://api.remarkets.primary.com.ar/ws"
        elif self.env.lower() == "live":
            rest = "https://api.primary.com.ar"
            ws   = "wss://api.primary.com.ar/ws"
        else:
            raise ValueError("env inválido")
        return (self.primary_base_url or rest, self.primary_ws_url or ws)

    def auth_creds(self) -> Tuple[str, str]:
        if self.env.lower() == "paper":
            return (self.primary_paper_username, self.primary_paper_password)
        return (self.primary_live_username, self.primary_live_password)

    def account_for_env(self) -> str:
        return self.account_paper if self.env.lower()=="paper" else self.account_live

settings = Settings()
