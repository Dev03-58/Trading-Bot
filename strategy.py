"""
Trading Strategy Module (Phase 3)
Calculates technical indicators and generates trading signals.

Strictly READ-ONLY: Decides signals ('BUY', 'SELL', 'HOLD') based on live market data.
Does not place, simulate, or execute any orders.
"""

import sys
import time
from typing import Optional
import pandas as pd
import config
import data


class IndicatorDict(dict):
    """
    Dictionary container for rounded indicator values with attribute access
    support (e.g. indicators.rsi, indicators.ema_fast).
    """
    def __init__(self, ema_fast: Optional[float], ema_slow: Optional[float], rsi: Optional[float]):
        fast_val = round(float(ema_fast), 2) if ema_fast is not None and not pd.isna(ema_fast) else None
        slow_val = round(float(ema_slow), 2) if ema_slow is not None and not pd.isna(ema_slow) else None
        rsi_val = round(float(rsi), 2) if rsi is not None and not pd.isna(rsi) else None

        super().__init__({
            "ema_fast": fast_val,
            "ema_slow": slow_val,
            "rsi": rsi_val,
        })

    @property
    def ema_fast(self) -> Optional[float]:
        return self["ema_fast"]

    @property
    def ema_slow(self) -> Optional[float]:
        return self["ema_slow"]

    @property
    def rsi(self) -> Optional[float]:
        return self["rsi"]


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes technical indicators on the candles DataFrame:
    - EMA(9) on close  -> column 'ema_fast'
    - EMA(21) on close -> column 'ema_slow'
    - RSI(14) on close -> column 'rsi'

    Uses pandas-ta if healthy, falling back cleanly to pure pandas .ewm() and
    Wilder's RSI smoothing if pandas-ta errors or returns all-NaN outputs.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # Attempt computation via pandas-ta
    computed_via_ta = False
    try:
        import pandas_ta as ta  # type: ignore
        ema_fast_ta = df.ta.ema(length=9)
        ema_slow_ta = df.ta.ema(length=21)
        rsi_ta = df.ta.rsi(length=14)

        if (
            ema_fast_ta is not None
            and not ema_fast_ta.isna().all()
            and ema_slow_ta is not None
            and not ema_slow_ta.isna().all()
            and rsi_ta is not None
            and not rsi_ta.isna().all()
        ):
            df["ema_fast"] = ema_fast_ta
            df["ema_slow"] = ema_slow_ta
            df["rsi"] = rsi_ta
            computed_via_ta = True
    except Exception:
        computed_via_ta = False

    # Robust fallback using plain pandas with Wilder's smoothing
    if not computed_via_ta:
        df["ema_fast"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()

        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        df["rsi"] = 100 - (100 / (1 + rs))

    return df


def get_signal(df: pd.DataFrame) -> str:
    """
    Evaluates trading conditions and returns 'BUY', 'SELL', or 'HOLD'.

    Rules:
    - BUY: EMA9 crossed ABOVE EMA21 on the latest candle:
           (previous candle ema_fast <= ema_slow AND current ema_fast > ema_slow)
           AND current RSI < 70
    - SELL: EMA9 crossed BELOW EMA21 on the latest candle:
           (previous candle ema_fast >= ema_slow AND current ema_fast < ema_slow)
    - Otherwise: HOLD
    - If indicators are NaN or fewer than ~25 candles: returns HOLD
    """
    if df is None or len(df) < 25:
        return "HOLD"

    # Compute indicators if not already present
    if "ema_fast" not in df.columns or "ema_slow" not in df.columns or "rsi" not in df.columns:
        df = compute_indicators(df)

    if len(df) < 2:
        return "HOLD"

    prev_fast = df["ema_fast"].iloc[-2]
    prev_slow = df["ema_slow"].iloc[-2]
    curr_fast = df["ema_fast"].iloc[-1]
    curr_slow = df["ema_slow"].iloc[-1]
    curr_rsi = df["rsi"].iloc[-1]

    # Guard against NaN values on the decision rows
    if any(pd.isna(x) for x in [prev_fast, prev_slow, curr_fast, curr_slow, curr_rsi]):
        return "HOLD"

    # BUY condition: EMA9 crossed above EMA21 AND RSI < 70
    if (prev_fast <= prev_slow) and (curr_fast > curr_slow) and (curr_rsi < 70):
        return "BUY"

    # SELL condition: EMA9 crossed below EMA21
    if (prev_fast >= prev_slow) and (curr_fast < curr_slow):
        return "SELL"

    return "HOLD"


def get_indicators(df: pd.DataFrame) -> IndicatorDict:
    """
    Returns latest ema_fast, ema_slow, and rsi as rounded readable values.
    Returns IndicatorDict with None values if data is insufficient or NaN.
    """
    if df is None or df.empty:
        return IndicatorDict(None, None, None)

    # Compute indicators if not already present
    if "ema_fast" not in df.columns or "ema_slow" not in df.columns or "rsi" not in df.columns:
        df = compute_indicators(df)

    curr_fast = df["ema_fast"].iloc[-1]
    curr_slow = df["ema_slow"].iloc[-1]
    curr_rsi = df["rsi"].iloc[-1]

    return IndicatorDict(curr_fast, curr_slow, curr_rsi)


if __name__ == "__main__":
    print("=" * 65, flush=True)
    print("           CRYPTO TRADING STRATEGY TEST (PHASE 3)             ", flush=True)
    print("=" * 65, flush=True)
    print(f"Mode                : {'TESTNET' if config.USE_TESTNET else 'LIVE'}", flush=True)
    print(f"Trading Symbol      : {config.SYMBOL}", flush=True)
    print(f"Candle Timeframe    : {config.TIMEFRAME}", flush=True)
    print(f"Strategy Type       : EMA(9) / EMA(21) Crossover + RSI(14) Filter", flush=True)
    print(f"Execution Plan      : 3 Real-time cycles, 30 seconds apart", flush=True)
    print("=" * 65, flush=True)

    try:
        print("\nConnecting to Binance via data.py (READ-ONLY)...", flush=True)
        exchange = data.get_exchange()
        print("Connected successfully to exchange.\n", flush=True)

        total_cycles = 3
        sleep_interval = 30

        for cycle in range(1, total_cycles + 1):
            print("-" * 65, flush=True)
            print(f"[Cycle {cycle}/{total_cycles}] Fetching fresh market data...", flush=True)

            # Fetch fresh live candles via data.py
            df_candles = data.get_candles(exchange, config.SYMBOL, config.TIMEFRAME, limit=200)
            df_with_indicators = compute_indicators(df_candles)

            newest_candle = df_with_indicators.iloc[-1]
            newest_timestamp = newest_candle["timestamp"]
            current_close = newest_candle["close"]

            indicators = get_indicators(df_with_indicators)
            signal = get_signal(df_with_indicators)

            print(f"  - Newest Candle Timestamp : {newest_timestamp}", flush=True)
            print(f"  - Current Close Price     : ${current_close:,.2f}", flush=True)
            print(f"  - Indicators (EMA9/21,RSI): {indicators}", flush=True)
            print(f"  - Strategy Signal         : >>> {signal} <<<", flush=True)

            if cycle < total_cycles:
                print(f"\nWaiting {sleep_interval}s for next cycle to demonstrate real-time updates...", flush=True)
                time.sleep(sleep_interval)

        print("\n" + "=" * 65, flush=True)
        print("    STRATEGY TEST COMPLETED SUCCESSFULLY - ALL CYCLES VERIFIED    ", flush=True)
        print("=" * 65, flush=True)

    except Exception as exc:
        print("\n" + "!" * 65, flush=True)
        print("STRATEGY EXECUTION ERROR", flush=True)
        print("!" * 65, flush=True)
        print(f"Error: {exc}", flush=True)
        print("Please check your exchange connection and market data in data.py.", flush=True)
        print("!" * 65, flush=True)
        sys.exit(1)
