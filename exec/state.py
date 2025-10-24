import requests
from settings import settings

class AccountState:
    def __init__(self, token: str):
        self.token = token
        self.ars = 0.0
        self.usd = 0.0

    def refresh_from_risk(self):
        rest, _ = settings.urls()
        acc = settings.account_for_env()
        h = {"X-Auth-Token": self.token, "accept":"application/json"}
        r = requests.get(f"{rest}/rest/risk/accountReport/{acc}", headers=h, timeout=5)
        r.raise_for_status()
        j = r.json()
        det = j.get("detailedPosition", j)
        self.ars = float(det.get("availableCashARS", det.get("cashARS", 0.0)) or 0.0)
        self.usd = float(det.get("availableCashUSD", det.get("cashUSD", 0.0)) or 0.0)
        return dict(cash_ars=self.ars, cash_usd=self.usd)
