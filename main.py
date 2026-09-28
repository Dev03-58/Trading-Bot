"""
Main Trading Engine (Phase 7 - Soak-Test Configuration)
Orchestrates live market data, strategy evaluation, risk management,
and order execution in a resilient continuous loop on Binance SPOT TESTNET.

Key Features & Soak-Test Additions:
- 1h Candlestick evaluation (V0 baseline: EMA9/21 cross + RSI<70 filter)
- 300s (5-minute) cycle sleep interval
- Daily Telegram status report at DAILY_REPORT_HOUR_UTC (balance, open position, trades count, uptime, errors)
- In-memory tracking of trades_count and errors_count
- Resilient loop that never crashes (try/except wrapped per cycle)
- Computes signals strictly on CLOSED candles (drops still-forming candle)
- One position at a time via position.json persistence
- Only sells exact position quantity, never whole account BTC
- Graceful shutdown on Ctrl+C (KeyboardInterrupt) with Telegram notice
- Heartbeat logged every cycle with 1h indicators
"""

import os
import sys
import time
import signal
import threading
import argparse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

import config
import data
import strategy
import risk
import trader
import telegram_bot

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")

stop_requested = threading.Event()
shutdown_completed = threading.Event()

# Soak-Test In-Memory State
bot_start_time: datetime = datetime.now(timezone.utc)
trades_count: int = 0
errors_count: int = 0
last_daily_report_date: Optional[str] = None


def log_event(message: str, console: bool = True):
    """Logs an event with full timestamp to console and bot.log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    if console:
        print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[Logging Error] Failed writing to {LOG_FILE}: {e}", flush=True)


def get_bot_uptime_str() -> str:
    """Calculates formatted bot uptime since startup."""
    uptime = datetime.now(timezone.utc) - bot_start_time
    total_seconds = int(uptime.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m {seconds}s"
    elif hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    else:
        return f"{minutes}m {seconds}s"


def log_heartbeat(
    current_price: float,
    signal: str,
    position: Optional[Dict[str, Any]],
    indicators: Optional[Dict[str, Any]] = None,
):
    """
    Prints and appends the cycle heartbeat line reflecting 1h timeframe and indicators:
    [HH:MM:SS] Alive [1h] | Price: $X | Signal: HOLD | EMA9: $X | EMA21: $X | RSI: X | Position: none
    """
    now_str = datetime.now().strftime("%H:%M:%S")
    if position and position.get("qty_filled"):
        qty = position.get("qty_filled")
        entry = float(position.get("entry_price", 0))
        pos_str = f"{qty} BTC @ ${entry:,.2f}"
    else:
        pos_str = "none"

    ind_str = ""
    if indicators:
        ema9 = indicators.get("ema_fast")
        ema21 = indicators.get("ema_slow")
        rsi_val = indicators.get("rsi")
        parts = []
        if ema9 is not None:
            parts.append(f"EMA9: ${ema9:,.2f}")
        if ema21 is not None:
            parts.append(f"EMA21: ${ema21:,.2f}")
        if rsi_val is not None:
            parts.append(f"RSI: {rsi_val:.1f}")
        if parts:
            ind_str = " | " + " | ".join(parts)

    line = f"[{now_str}] Alive [{config.TIMEFRAME}] | Price: ${current_price:,.2f} | Signal: {signal}{ind_str} | Position: {pos_str}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[Logging Error] Failed writing heartbeat to {LOG_FILE}: {e}", flush=True)


def print_startup_banner():
    """Prints and logs the trading bot configuration on startup."""
    mode = "TESTNET (Paper Trading)" if config.USE_TESTNET else "LIVE TRADING"
    today_str = datetime.now().strftime("%Y-%m-%d")
    banner = "=" * 65 + "\n"
    banner += "             CRYPTO TRADING BOT - MAIN ENGINE                 \n"
    banner += f"             *** SOAK TEST MODE ({today_str}) ***            \n"
    banner += "=" * 65 + "\n"
    banner += f"Phase               : SOAK TEST MODE ({today_str})\n"
    banner += f"Mode                : {mode}\n"
    banner += f"Trading Symbol      : {config.SYMBOL}\n"
    banner += f"Timeframe           : {config.TIMEFRAME}\n"
    banner += f"Strategy            : EMA(9) / EMA(21) Crossover + RSI(14) Filter\n"
    banner += f"Risk Per Trade (%)  : {config.RISK_PER_TRADE_PCT}%\n"
    banner += f"Stop Loss (%)       : {config.STOP_LOSS_PCT}%\n"
    banner += f"Take Profit (%)     : {config.TAKE_PROFIT_PCT}%\n"
    banner += f"Cycle Sleep Interval: {config.SLEEP_SECONDS} seconds\n"
    banner += f"Daily Report Hour   : {config.DAILY_REPORT_HOUR_UTC:02d}:00 UTC\n"
    banner += f"Startup retry       : enabled (10 attempts / 30s)\n"
    banner += "=" * 65
    print(banner, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(banner + "\n")
    except Exception:
        pass


def send_daily_report_summary(exchange) -> bool:
    """Collects current metrics and sends the daily summary to Telegram."""
    global errors_count
    # Current balance
    try:
        balance = data.get_balance(exchange)
        balance_str = f"${balance.USDT:,.2f} USDT"
        if balance.BTC > 0:
            balance_str += f" | {balance.BTC:.6f} BTC"
    except Exception as e:
        balance_str = f"Error: {e}"

    # Open position (or none)
    open_pos = trader.load_position()
    if open_pos and open_pos.get("qty_filled"):
        qty = open_pos.get("qty_filled")
        entry = float(open_pos.get("entry_price", 0))
        pos_str = f"{qty} BTC @ ${entry:,.2f}"
        try:
            curr_price = data.get_current_price(exchange, config.SYMBOL)
            if curr_price > 0 and entry > 0:
                pnl_pct = ((curr_price - entry) / entry) * 100
                pos_str += f" (Now: ${curr_price:,.2f}, PnL: {pnl_pct:+.2f}%)"
        except Exception:
            pass
    else:
        pos_str = "None"

    uptime_str = get_bot_uptime_str()
    errors_reported = errors_count

    log_event(
        f"[DAILY REPORT] Balance: {balance_str} | Position: {pos_str} | "
        f"Trades: {trades_count} | Uptime: {uptime_str} | Errors: {errors_reported}"
    )

    success = telegram_bot.send_daily_report(
        balance_str=balance_str,
        position_str=pos_str,
        trades_count=trades_count,
        uptime_str=uptime_str,
        errors_count=errors_reported,
    )

    # Reset errors counted since this report
    errors_count = 0
    return success


def check_daily_report(exchange):
    """Checks if the scheduled daily report should be sent at DAILY_REPORT_HOUR_UTC."""
    global last_daily_report_date
    now_utc = datetime.now(timezone.utc)
    current_date_str = now_utc.strftime("%Y-%m-%d")

    # Send once per day at DAILY_REPORT_HOUR_UTC
    if now_utc.hour == config.DAILY_REPORT_HOUR_UTC and last_daily_report_date != current_date_str:
        log_event(f"Triggering scheduled daily report for {current_date_str} ({now_utc.strftime('%H:%M')} UTC)...")
        send_daily_report_summary(exchange)
        last_daily_report_date = current_date_str


def evaluate_signal(exchange) -> Tuple[str, Dict[str, Any], float]:
    """
    Fetches fresh candles (limit=200) and computes indicators on CLOSED candles only.
    Drops the last row (still-forming candle) to prevent signal flickering.

    Returns:
        (signal, indicators, latest_close_price)
    """
    df = data.get_candles(exchange, config.SYMBOL, config.TIMEFRAME, limit=200)
    if df is None or len(df) < 26:
        return "HOLD", {}, 0.0

    # CRITICAL: Drop the last row to calculate strictly on CLOSED candles
    closed_df = df.iloc[:-1].copy()

    # Compute technical indicators
    closed_df = strategy.compute_indicators(closed_df)

    signal = strategy.get_signal(closed_df)
    indicators = strategy.get_indicators(closed_df)
    latest_close_price = float(closed_df["close"].iloc[-1])

    return signal, indicators, latest_close_price


def run_cycle(exchange):
    """Executes a single cycle of market evaluation and trade management."""
    global trades_count
    # 1. Load active position state from disk
    position = trader.load_position()

    # 2. Evaluate strategy signal on closed candles
    signal, indicators, latest_closed_price = evaluate_signal(exchange)

    # 3. Fetch latest live market price
    current_price = data.get_current_price(exchange, config.SYMBOL)
    if current_price <= 0:
        current_price = latest_closed_price

    # 4. Trade decision logic
    if not position:
        # No position is currently open
        if signal == "BUY":
            log_event(f"BUY signal triggered at ${current_price:,.2f} with indicators {indicators}")
            balance = data.get_balance(exchange)
            sizing = risk.position_size(balance.USDT, current_price)

            if sizing and sizing.get("quantity"):
                qty_to_buy = sizing["quantity"]
                log_event(f"Position sizing approved: Buying {qty_to_buy} {config.SYMBOL} (Risk: ${sizing['risk_amount_usdt']:,.2f} USDT)")
                position = trader.buy(exchange, qty_to_buy, config.SYMBOL)
                trades_count += 1
                log_event(f"BUY executed: {position['qty_filled']} {config.SYMBOL} @ ${position['entry_price']:,.2f} (Order ID: {position['order_id']}) [Total Trades: {trades_count}]")
            else:
                reason = getattr(sizing, "reason", "Insufficient balance or invalid sizing")
                log_event(f"BUY skipped: {reason}")

        elif signal == "SELL":
            log_event("SELL ignored — no position open")

    else:
        # A position is already open
        entry_price = float(position.get("entry_price", current_price))
        exit_trigger = risk.check_exit(entry_price, current_price)

        if signal == "SELL":
            exit_trigger = "STRATEGY_EXIT"

        if exit_trigger:
            log_event(f"Exit trigger '{exit_trigger}' hit (Entry: ${entry_price:,.2f}, Current: ${current_price:,.2f})")
            sell_result = trader.sell(exchange, position, config.SYMBOL)
            log_event(f"SELL executed: {sell_result['qty_sold']} {config.SYMBOL} @ ${sell_result['exit_price']:,.2f} | P&L: ${sell_result['pnl_usdt']:+,.2f} ({sell_result['pnl_pct']:+.2f}%)")
            position = None

    # 5. Output heartbeat for this cycle with 1h indicators
    log_heartbeat(current_price, signal, position, indicators=indicators)

    # 6. Check scheduled daily report
    check_daily_report(exchange)


def interruptible_sleep(seconds: int, stop_flag: threading.Event):
    """Sleeps in 1-second intervals so shutdown signals are processed immediately."""
    for _ in range(int(seconds)):
        if stop_flag.is_set():
            break
        time.sleep(1)


def handle_shutdown(signum=None, frame=None):
    """Cleanly handles shutdown, sending Telegram notice and preserving open positions."""
    if shutdown_completed.is_set():
        return
    shutdown_completed.set()
    stop_requested.set()

    print("\n" + "=" * 65, flush=True)
    print("Shutdown signal received. Stopping trading bot gracefully...", flush=True)
    print("=" * 65, flush=True)
    log_event("Shutdown signal received. Stopping trading bot gracefully...")

    open_pos = trader.load_position()
    if open_pos:
        pos_msg = (
            f"Active open position preserved:\n"
            f"• Symbol: {open_pos.get('symbol')}\n"
            f"• Quantity: {open_pos.get('qty_filled')} BTC\n"
            f"• Entry Price: ${float(open_pos.get('entry_price', 0)):,.2f}\n"
            f"• Order ID: {open_pos.get('order_id')}\n"
            f"• Preserved in position.json (will be resumed on next run)."
        )
        log_event(f"Notice: Open position retained on shutdown: {open_pos.get('qty_filled')} BTC @ ${open_pos.get('entry_price')}")
        telegram_bot.send_message(f"🛑 <b>Trading Bot Stopped Manually</b>\n\n{pos_msg}")
    else:
        log_event("Notice: No open positions upon shutdown.")
        telegram_bot.send_message("🛑 <b>Trading Bot Stopped Manually</b>\n\n• No open positions were active.")

    log_event("Trading bot shutdown complete. Exited cleanly.")
    print("Trading bot shutdown complete. Exited cleanly.\n", flush=True)
    sys.exit(0)


def listen_for_input():
    """Background listener for stop commands or flags."""
    while not stop_requested.is_set():
        try:
            line = sys.stdin.readline()
            if line and line.strip().lower() in ("stop", "quit", "exit", "q"):
                handle_shutdown()
                break
        except Exception:
            break


def main():
    parser = argparse.ArgumentParser(description="Crypto Trading Bot - Soak-Test Engine")
    parser.add_argument("--cycles", type=int, default=None, help="Run a specific number of cycles then cleanly exit.")
    parser.add_argument("--sleep", type=int, default=config.SLEEP_SECONDS, help="Sleep interval in seconds between cycles.")
    parser.add_argument("--sanity", action="store_true", help="Run 3 cycles with fast sleep interval and cleanly exit.")
    parser.add_argument("--test-report", action="store_true", help="Send a test daily report on startup to verify Telegram delivery.")
    args = parser.parse_args()

    # Determine execution parameters
    if args.sanity:
        target_cycles = 3
        cycle_sleep = 2
    else:
        target_cycles = args.cycles
        cycle_sleep = args.sleep

    # Register OS signal handlers for clean Ctrl+C / SIGINT / SIGTERM shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Start input listener thread
    input_thread = threading.Thread(target=listen_for_input, daemon=True)
    input_thread.start()

    # 1. Startup initialization
    print_startup_banner()
    log_event("Trading bot initializing...")

    # Connect to exchange via data.py (retry loop: 10 attempts, 30s apart)
    MAX_STARTUP_ATTEMPTS = 10
    RETRY_DELAY_SECONDS = 30
    exchange = None

    for attempt in range(1, MAX_STARTUP_ATTEMPTS + 1):
        try:
            log_event(f"Connecting to Binance exchange via data.py (attempt {attempt}/{MAX_STARTUP_ATTEMPTS})...")
            exchange = data.get_exchange()
            log_event("Connected successfully to exchange.")
            break
        except Exception as e:
            if attempt < MAX_STARTUP_ATTEMPTS:
                log_event(f"[Startup] Connection attempt {attempt}/{MAX_STARTUP_ATTEMPTS} failed, retrying in {RETRY_DELAY_SECONDS}s...")
                interruptible_sleep(RETRY_DELAY_SECONDS, stop_requested)
                if stop_requested.is_set():
                    sys.exit(0)
            else:
                err_msg = f"Fatal connection failure on startup after {MAX_STARTUP_ATTEMPTS} attempts: {e}"
                log_event(f"[FATAL] {err_msg}")
                telegram_bot.send_error_alert(err_msg)
                sys.exit(1)

    # Deliver Telegram startup notification
    log_event("Delivering Telegram startup notification...")
    telegram_bot.send_startup_alert()

    # Deliver optional test report if requested
    if args.test_report:
        log_event("Sending test daily report to Telegram...")
        send_daily_report_summary(exchange)

    # Crash recovery: Check if a position was already open
    existing_position = trader.load_position()
    if existing_position:
        log_event(
            f"Recovered open position from previous session: "
            f"{existing_position.get('qty_filled')} BTC @ ${float(existing_position.get('entry_price', 0)):,.2f} "
            f"(Order ID: {existing_position.get('order_id')})"
        )
    else:
        log_event("No prior position found. Monitoring for trade setups...")

    cycle_info = f"Target Cycles: {target_cycles}" if target_cycles else "Continuous"
    log_event(f"Entering main trading loop (Interval: {cycle_sleep}s, Mode: {cycle_info}). Press Ctrl+C to stop.\n")

    completed_cycles = 0

    # 2. Main loop: NEVER crashes, wraps each cycle in try/except
    while not stop_requested.is_set():
        try:
            run_cycle(exchange)
            completed_cycles += 1
            if target_cycles and completed_cycles >= target_cycles:
                log_event(f"Reached targeted cycle count ({completed_cycles}/{target_cycles}). Initiating clean shutdown...")
                handle_shutdown()
                break
        except KeyboardInterrupt:
            handle_shutdown()
            break
        except Exception as cycle_err:
            global errors_count
            errors_count += 1
            err_msg = f"Error during trading cycle: {cycle_err}"
            log_event(f"[CYCLE ERROR] {err_msg}")
            try:
                telegram_bot.send_error_alert(err_msg)
            except Exception:
                pass

        interruptible_sleep(cycle_sleep, stop_requested)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        handle_shutdown()
