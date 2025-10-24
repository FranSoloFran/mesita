import requests
from settings import settings

def fetch_all_symbols() -> list[dict]:
    rest, _ = settings.urls()
    r = requests.get(f"{rest}/rest/instruments/all", timeout=settings.primary_timeout_s)
    r.raise_for_status()
    j = r.json()
    return j if isinstance(j, list) else j.get("instruments", [])

def build_pairs() -> list[tuple[str,str]]:
    items = fetch_all_symbols()
    exists = {it.get("symbol",""): it for it in items if it.get("symbol")}
    pairs: list[tuple[str,str]] = []
    for sym in list(exists.keys()):
        if sym.endswith("D"):
            usd = sym
            ars = sym[:-1]
            if ars in exists:
                pairs.append((ars, usd))
    return sorted(list({tuple(p) for p in pairs}))
