"""The one guarded UAT order. Only engine.py calls this."""
import time

from .settings import DELIVERY_TYPE, EXCHANGE, ORDER_QTY, STRAT_TAG

FINAL = ("EXECUTED", "REJECTED", "CANCELLED", "EXPIRED")


class UatOrderPlacer:
    def __init__(self, uat_instruments, uat_trader, emit):
        self.instruments = uat_instruments
        self.trader = uat_trader
        self.emit = emit

    def place_limit_buy(self, symbol, live_paise):
        """LIMIT BUY, quantity 1, at the live price rounded to the UAT tick size."""
        inst = self.instruments.get_instrument_by_symbol(symbol, exchange=EXCHANGE)  # UAT ref_id
        if inst is None:
            self.emit("order", f"{symbol} not found in UAT instruments; no order sent")
            return
        tick = int(inst.tick_size)
        price = max(((int(live_paise) + tick // 2) // tick) * tick, tick)  # nearest tick, integer math
        self.emit("order", f"BUY {ORDER_QTY} {symbol} (UAT ref_id={inst.ref_id}) LIMIT @ {price} paise "
                           f"(Rs {price / 100:.2f}, tick {tick}, live {live_paise})")
        result = self.trader.create_order({
            "refId": inst.ref_id,
            "qty": ORDER_QTY,
            "side": "BUY",
            "deliveryType": DELIVERY_TYPE,
            "priceType": "LIMIT",
            "validityType": "DAY",
            "isMultiLeg": False,
            "executionMode": "ENTRY",
            "entryPrice": price,
            "stratTags": [STRAT_TAG],
        })
        order = result.orders[0]
        self.emit("order", f"accepted, intentOrderId={order.intentOrderId}, status={order.status}")

        latest = order
        for _ in range(5):                         # read the status back for ~5 seconds
            time.sleep(1)
            found = self.trader.get_order(order.intentOrderId)
            if found:
                latest = found[0]
                if any(s in str(latest.status).upper() for s in FINAL):
                    break
        self.emit("order", f"status read back: {latest.status} | filled {latest.filledQty}/"
                           f"{latest.orderQty} | rejection: {getattr(latest, 'rejectionMsg', None) or '-'}")
