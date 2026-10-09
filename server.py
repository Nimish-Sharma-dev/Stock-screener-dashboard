"""Local dashboard. Run from the repo root:  python -m app.server [--trade]
View only: there is no endpoint that places an order. Login happens in the terminal first."""
import argparse
import asyncio
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from screener import settings
from screener.runtime import Runtime

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Z-score screener")
runtime = None  # set in main() before the server starts


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def api_state():
    return runtime.state.view()


@app.websocket("/ws")
async def ws_state(ws: WebSocket):
    """Push a fresh view whenever the engine/stream/risk layer changes something."""
    await ws.accept()
    last = -1
    try:
        while True:
            version = runtime.state.version      # in-memory read, no SDK calls
            if version != last:
                await ws.send_json(runtime.state.view())
                last = version
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        pass


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main():
    global runtime
    parser = argparse.ArgumentParser(description="Z-score screener dashboard")
    parser.add_argument("--trade", action="store_true",
                        help="enable the single guarded UAT order (logs in to UAT)")
    parser.add_argument("--host", default=settings.HOST)
    parser.add_argument("--port", type=int, default=settings.PORT)
    args = parser.parse_args()

    runtime = Runtime(trade=args.trade).start()          # logins + OTP prompts happen here
    threading.Thread(target=runtime.engine.run_forever, args=(runtime.stop,), daemon=True).start()
    print(f"Dashboard: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
