from pydantic import BaseSettings

class Settings(BaseSettings):
    mode: str = "csv"
    csv_ars: str = "assets/data/al30_ars.csv"
    csv_usd: str = "assets/data/al30_usd.csv"
    veta_base_url: str = ""
    veta_api_key: str = ""
    min_notional_ars: float = 40000.0
    thresh_pct: float = 0.002
    cost_bps: float = 12
    slip_bps: float = 8

    class Config:
        env_file = ".env"

settings = Settings()
