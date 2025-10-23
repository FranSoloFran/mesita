from pydantic import BaseSettings
from typing import List

class Settings(BaseSettings):
    mode: str = "primary_ws"     # "primary_ws" | "primary" | "csv" según si usar WS, REST o testing con CSV personalizados
    poll_s: float = 0.25

    primary_base_url: str = ""
    primary_ws_url: str = ""
    primary_username: str = ""
    primary_password: str = ""
    primary_timeout_s: float = 3.0

    pairs: str = "AL30:AL30D" # de donde tomamos el valor del MEP
    min_notional_ars: float = 40000.0 
    thresh_pct: float = 0.002
    cost_bps: float = 12
    slip_bps: float = 8

    csv_ars: str = "assets/data/al30_ars.csv"
    csv_usd: str = "assets/data/al30_usd.csv"

    class Config:
        env_file = ".env"

    def parsed_pairs(self) -> List[tuple]:
        out = []
        for raw in self.pairs.split(","):
            raw = raw.strip()
            if not raw:
                continue
            a, b = [x.strip() for x in raw.split(":")]
            out.append((a, b))
        return out

settings = Settings()
