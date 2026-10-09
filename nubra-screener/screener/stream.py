"""Realtime index stream. The callback only stores the latest price (index_value is PAISE)."""
import threading

from nubra_python_sdk.ticker import websocketdata

from .settings import EXCHANGE


def start_stream(client, symbols, state):
    watch = set(symbols)
    unknown = set()

    def on_index_data(msg):
        name = getattr(msg, "indexname", None)
        if name not in watch:
            if name not in unknown:
                unknown.add(name)
                state.add_event("stream", f"ignoring update for unexpected name: {name!r}")
            return
        state.set_live(name, msg.index_value)

    def on_connect(msg):
        state.set_socket("connected")
        state.add_event("stream", f"connected: {msg}")

    def on_close(reason):
        state.set_socket("closed")
        state.add_event("stream", f"closed: {reason} (no auto-reconnect)")

    def on_error(err):
        state.add_event("stream", f"error: {err}")

    socket = websocketdata.NubraDataSocket(
        client=client,
        on_index_data=on_index_data,
        on_connect=on_connect,
        on_close=on_close,
        on_error=on_error,
    )
    socket.connect()
    socket.subscribe(list(symbols), data_type="index", exchange=EXCHANGE)
    threading.Thread(target=socket.keep_running, daemon=True).start()
    state.add_event("stream", f"subscribed to {len(symbols)} symbols")
    return socket
