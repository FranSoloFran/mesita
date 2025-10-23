from pydantic import BaseSettings
from typing import List, Tuple

class Settings(BaseSettings):
    # runtime
    mode: str = "primary_ws"           # primary_ws por ahora solo Primary
    env: str = "paper"                 # paper | live - paper para cuenta de Remarkets  y live para cuenta con guita real
    poll_s: float = 0.25
    primary_timeout_s: float = 3.0

    # urls (si dejás vacío, se autoconfiguran según env)
    primary_base_url: str = ""         # https://api.remarkets.primary.com.ar | https://api.primary.com.ar
    primary_ws_url: str = ""           # wss://api.remarkets.primary.com.ar/ws | wss://api.primary.com.ar/ws

    # credenciales separadas por entorno
    primary_paper_username: str = ""
    primary_paper_password: str = ""
    primary_live_username: str = ""
    primary_live_password: str = ""

    # trading
    pairs: str = "AL30:AL30D"
    min_notional_ars: float = 40000.0 # monto operable en pesos debe ser mayor o igual a $40000
    thresh_pct: float = 0.002 # 0,2% tipo de cambio minimo por debajo del mep de referencia
    cost_bps: float = 0.0     # por defecto sin comisión (veta flat). si fuera con comisión por ej. 0,15%, poner 15
    slip_bps: float = 0.0 # deslizamiento de precio para el backtesting, si fuera por ej 0.08% poner 8, igual si miramos las puntas y operamos limit no hace falta

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
            raise ValueError(f"env inválido: {self.env}")
        return (self.primary_base_url or rest, self.primary_ws_url or ws)

    def auth_creds(self) -> Tuple[str, str]:
        if self.env.lower() == "paper":
            return (self.primary_paper_username, self.primary_paper_password)
        if self.env.lower() == "live":
            return (self.primary_live_username, self.primary_live_password)
        raise ValueError(f"env inválido: {self.env}")

    def parsed_pairs(self) -> List[tuple]:
        out = []
        for raw in self.pairs.split(","):
            raw = raw.strip()
            if not raw or ":" not in raw: continue
            a, b = [x.strip() for x in raw.split(":")]
            out.append((a, b))
        return out

settings = Settings()
