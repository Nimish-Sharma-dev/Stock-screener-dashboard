# nubra-screener

Live 20-day z-score screener for the top-16 NIFTY 50 stocks, as a terminal tool and a local web dashboard.
Both share one engine, so the table in the terminal and in the browser can never disagree.

## Setup
```bash
python -m pip install -r requirements.txt
cp .env.example .env        # then put your real PHONE_NO and MPIN in .env
```
The SDK still asks for the OTP in the terminal at login (twice with `--trade`: PROD and UAT).

## Run
```bash
python cli.py                      # terminal table, never trades
python cli.py --trade              # may place ONE UAT order
python -m app.server               # dashboard at http://127.0.0.1:8000 (view only)
python -m app.server --trade       # same, plus the one guarded UAT order
python -m pytest                   # tests (no login needed)
```
Start the dashboard with `python -m app.server` from the repo root (not `python app/server.py`).
Login (and the OTP prompt) happens in the terminal *before* the web server starts.

## Files
| File | Job |
| --- | --- |
| `cli.py` | terminal entry point, prints the table every refresh |
| `app/server.py` | FastAPI: serves the page, pushes each new table over a websocket |
| `app/static/*` | the page: table, status badges, event log |
| `screener/settings.py` | watchlist, window, thresholds, timings |
| `screener/session.py` | PROD login always, UAT login only with `--trade` |
| `screener/history.py` | 60 daily candles in batches of 5, UTC dates, rate limiter, symbol check |
| `screener/stats.py` | pure maths: build series, mean, std, z |
| `screener/state.py` | thread-safe store shared by stream, engine and server |
| `screener/stream.py` | websocket client; callback only stores the live price (paise) |
| `screener/engine.py` | recompute loop, -2 cross detection, the only caller of orders |
| `screener/risk.py` | the hard rules and printed refusal reasons |
| `screener/orders.py` | UAT lookup, one LIMIT BUY, status read-back |
| `screener/runtime.py` | start-up wiring shared by `cli.py` and `app/server.py` |

## Safety notes
- The dashboard has no buttons or endpoints that trade; only the engine can reach `orders.py`.
- Keep the server on `127.0.0.1`. It runs on your logged-in session and should not be exposed to a network.
- Risk rules: at most one order per run, quantity 1, only if z < -2, never a stretched high (z > +2).
- The limit price comes from the live PROD price, but the order goes to UAT (sandbox), so it may not fill.
