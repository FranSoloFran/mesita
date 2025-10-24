# mesita

**Lightweight MEP arbitrage bot for Argentine markets.**  
Monitors bond pairs, computes implied FX rates, and auto-executes trades under configurable thresholds.  
Features a modular datafeed, risk-control logic, and an open-ended learning architecture for sizing and pair selection.

---

## Overview

Mesita is a rule-based and learning-augmented arbitrage engine designed to operate across peso and dollar-denominated bond pairs (e.g. `AL30 / AL30D`).  
It continuously monitors market quotes, calculates the **implied FX rate (MEP)**, and executes trades whenever spreads exceed a configurable threshold.  

The architecture supports:
- **Paper trading** and **Live mode** (via Veta broker API)
- **Procedural stress testing** for execution robustness
- **Reinforcement / open-ended learning** for adaptive sizing and pair selection
- Detailed **trade logs, PnL tracking,** and **configurable risk limits**

---

## Structure

```
mesita/
  .env.example
  requirements.txt
  settings.py
  assets/
    plots/
      .gitkeep
  util/
    trace.py
  agent/
    rules.py
  discover/
    instruments.py
  datafeed/
    base.py
    primary_ws.py
  exec/
    state.py
    reconciler.py
    sync.py
  sim/
    mep_ref.py
  scripts/
    print_quotes.py
    er_logger.py
    live_ws.py
  ui/
    streamlit_app.py
```

---

## Quickstart

### Install
```bash
git clone https://github.com/youruser/mesita.git
cd mesita
pip install -r requirements.txt
```

### Paper trading
```bash
python scripts/paper.py   --csv assets/data/al30_ars.csv   --csvd assets/data/al30_usd.csv
```
Generates:
- `assets/plots/trades.csv`
- `assets/plots/equity.png`

### Live (Veta)
```bash
export VETA_BASE_URL="https://api.veta.com.ar"
export VETA_API_KEY="your_key"
python scripts/live_paper_veta.py --ars AL30 --usd AL30D
```

---

## Roadmap

| Stage | Goal | Status |
|-------|------|---------|
| Rule-based trading | Fixed thresholds (0.2%) | Done |
| Procedural sim | Randomized liquidity, cost & latency | WIP |
| Open-ended RL | Adaptive sizing & pair selection | Soon |

---

## Disclaimer

For **research and educational purposes only**.  
Not financial advice. Use at your own risk.

---

## License

[Apache License 2.0](LICENSE)

---

*"Todo se cura con amor" - RIP [Miguel Angel Russo](https://en.wikipedia.org/wiki/Miguel_%C3%81ngel_Russo) 1956-2025*
