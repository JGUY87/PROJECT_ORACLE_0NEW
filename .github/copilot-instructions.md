# Copilot Instructions for PROJECT_ORACLE_0_NEW

## Big Picture Architecture
- The project is a modular trading bot system optimized for Bybit REST v5 (category='linear', accountType='UNIFIED').
- Major components:
  - `src/main_realtime.py`: Real-time trading entrypoint.
  - `src/main_backtest.py`: Backtesting entrypoint.
  - `src/market_features.py`: Feature computation and snapshot logging.
  - `src/strategy_recommender.py`: Strategy selection logic (PPO prioritized, fallback strategies unified).
  - `src/trade_executor_async.py`: Asynchronous trade execution, uses preflight checks.
  - `src/model_loader.py`: Loads ML models for strategy.
  - `src/report_utils.py`: Standardized reporting and engine status.
- Data flows: Features are computed from external data, passed to strategy recommender, which drives trade execution. Reports and logs are standardized (6-column format).

## Developer Workflows
- **Environment Setup:**
  - Use Python 3.10.x and create a venv in `trading_env/`.
  - Install dependencies via `pip install -r requirements/base.txt`.
  - Copy `.env.example` to `.env` and fill in API keys.
- **Running:**
  - Real-time: `python src/main_realtime.py`
  - Backtest: `python src/main_backtest.py`
- **Diagnostics:**
  - Bybit v5: `python -m tools.diag_bybit_v5`
  - Network: `python -m tools.diag_network`
- **Preflight:**
  - All orders should go through `tools.sitecustomize.preflight_and_place()` for automatic retry/adjustment on error 110007 (insufficient balance).

## Project-Specific Conventions
- All Bybit API calls use fixed parameters (`category='linear'`, `accountType='UNIFIED'`).
- Use `.env` with `DRY_RUN=true` for safe validation before live trading.
- Feature computation is standardized; use `compute_features()` and pass to `strategy_recommender.ai_recommend_strategy_strategy_live()`.
- Telegram notifications are async by default, with sync wrappers available.
- All code and text files are UTF-8/LF where possible; `__init__.py` is present in all Python folders.

## Integration Points & Patterns
- External data is loaded via Pandas/NumPy, minimal dependencies.
- ML models (PPO) loaded via `src/model_loader.py`.
- Reports/logs written to `outputs/` (see 6-column format in `report_utils.py`).
- All trading logic is routed through preflight wrappers for safety and compliance.

## Key Files & Directories
- `src/` – Main source code (see above for key modules)
- `configs/` – All config files (accounts, risk, logging, etc.)
- `outputs/` – Reports, logs, model outputs
- `requirements/` – Dependency lists
- `trading_env/` – Python virtual environment

---

For unclear or incomplete sections, please provide feedback or specify which workflows, conventions, or integration points need further documentation.
