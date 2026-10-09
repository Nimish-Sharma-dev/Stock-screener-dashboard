"""Terminal screener.   python cli.py            (never trades)
                        python cli.py --trade    (may place ONE UAT order)"""
import argparse
from datetime import datetime

from screener.runtime import Runtime
from screener.settings import IST


def print_table(rows, title):
    print(f"\n=== {title}  ({datetime.now(IST):%H:%M:%S} IST) ===")
    print(f"{'SYMBOL':<12}{'CLOSE':>10}{'MEAN20':>10}{'STD20':>9}{'Z':>8}  SRC   NOTE")

    def f(v, w):
        return f"{v:>{w}.2f}" if v is not None else f"{'n/a':>{w}}"

    for r in rows:  # engine already sorts by z, lowest first
        print(f"{r['symbol']:<12}{f(r['close'], 10)}{f(r['mean'], 10)}{f(r['std'], 9)}"
              f"{f(r['z'], 8)}  {r['src']:<5} {r['reason']}")


def main():
    parser = argparse.ArgumentParser(description="20-day z-score screener")
    parser.add_argument("--trade", action="store_true",
                        help="enable the single guarded UAT order (logs in to UAT)")
    args = parser.parse_args()

    rt = Runtime(trade=args.trade).start()
    print("Running. Ctrl+C to stop.")
    try:
        rt.engine.run_forever(rt.stop, on_update=print_table)
    except KeyboardInterrupt:
        rt.stop.set()
        print("\nStopped by user.")


if __name__ == "__main__":
    main()
