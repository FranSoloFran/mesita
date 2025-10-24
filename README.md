# mesita

**Lightweight MEP arbitrage bot for Argentine markets.**  
Monitors bond pairs, computes implied FX rates, and auto-executes trades under configurable thresholds.  
Features a modular datafeed, risk-control logic, and an open-ended learning architecture for sizing and pair selection.

---

## Overview

Mesita is a rule-based and learning-augmented arbitrage engine designed to operate across peso and dollar-denominated bond pairs (e.g. `AL30 / AL30D`).  
It continuously monitors market quotes, calculates the implied FX rate (MEP), and executes trades whenever spreads exceed a configurable threshold.  

The architecture supports:
- Paper trading and Live mode (via Primary API)
- Procedural stress testing for execution robustness
- Reinforcement / open-ended learning for adaptive sizing and pair selection
- Detailed trade logs, PnL tracking, and configurable risk limits

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
cp .env.example .env  # llená creds y accounts
# sanity: quotes
python scripts/print_quotes.py
# bot
python scripts/live_ws.py
# ui (otra terminal)
streamlit run ui/streamlit_app.py
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
