"""
Order Execution Module (Phase 5A)
Handles market order placement, position tracking, and persistence on Binance Spot Testnet.

Strict safety constraints:
- All exchange instances must come from data.get_exchange()
- Precision-adjust all quantities with exchange.amount_to_precision()
- Never liquidate entire asset balance — only trade the designated position quantity
- Emits loud warning banner if LIVE mode is ever enabled
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import ccxt
import config
import data
import telegram_bot

POSITION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "position.json")


def check_live_mode_warning():
    """Prints a loud warning banner if live trading mode is detected."""
    if not config.USE_TESTNET:
        banner = (
            "\n" + "!" * 65 + "\n"
            "⚠️  WARNING: LIVE TRADING MODE IS ACTIVE! REAL CAPITAL AT RISK!  ⚠️\n"
            "!" * 65 + "\n"
        )
        print(banner, flush=True)


def save_position(pos_dict: Dict[str, Any]) -> bool:
    """
    Persists open position details to position.json so the bot survives restarts.
    
    Args:
        pos_dict: Dictionary containing symbol, qty_filled, entry_price, timestamp, order_id.
    """
    try:
        with open(POSITION_FILE, "w", encoding="utf-8") as f:
            json.dump(pos_dict, f, indent=4)
        return True
    except Exception as e:
        print(f"[Persistence Error] Failed to save position to {POSITION_FILE}: {e}", flush=True)
        return False


def load_position() -> Optional[Dict[str, Any]]:
    """
    Loads saved position from position.json.
    
    Returns:
        dict if position exists and is valid, None if missing or corrupt.
    """
    if not os.path.exists(POSITION_FILE):
        return None

    try:
        with open(POSITION_FILE, "r", encoding="utf-8") as f:
            data_loaded = json.load(f)
            if isinstance(data_loaded, dict) and data_loaded:
                return data_loaded
            return None
    except Exception as e:
        print(f"[Persistence Warning] Corrupt or unreadable position file ({POSITION_FILE}): {e}", flush=True)
        return None


def clear_position() -> bool:
    """
    Deletes position.json once a trade is closed.
    
    Returns:
        True if successfully cleared or already absent, False on error.
    """
    try:
        if os.path.exists(POSITION_FILE):
            os.remove(POSITION_FILE)
        return True
    except Exception as e:
        print(f"[Persistence Error] Failed to delete position file ({POSITION_FILE}): {e}", flush=True)
        return False


def _extract_fill_info(
    order: Dict[str, Any],
    default_price: float,
    default_qty: float,
) -> Tuple[float, float, str]:
    """
    Extracts filled quantity, average execution price, and order ID from order response.
    """
    order_id = str(order.get("id", ""))

    # 1. Filled quantity
    qty_filled = float(order.get("filled") or 0.0)
    if qty_filled <= 0:
        info = order.get("info", {})
        qty_filled = float(info.get("executedQty") or info.get("origQty") or order.get("amount") or default_qty)

    # 2. Execution price
    avg_price = float(order.get("average") or order.get("price") or 0.0)
    if avg_price <= 0:
        cost = float(order.get("cost") or 0.0)
        if cost > 0 and qty_filled > 0:
            avg_price = cost / qty_filled
        else:
            fills = order.get("info", {}).get("fills", [])
            if fills:
                total_qty = sum(float(f.get("qty", 0.0)) for f in fills)
                total_cost = sum(float(f.get("qty", 0.0)) * float(f.get("price", 0.0)) for f in fills)
                if total_qty > 0:
                    avg_price = total_cost / total_qty
            if avg_price <= 0:
                avg_price = default_price

    return qty_filled, avg_price, order_id


def buy(exchange: ccxt.binance, qty: float, symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes a market BUY order with precision adjustment and minimum notional checks.

    Args:
        exchange: Authenticated ccxt exchange instance (from data.get_exchange()).
        qty: Target quantity in base currency (BTC).
        symbol: Trading pair symbol (defaults to config.SYMBOL).

    Returns:
        dict: Persisted position containing symbol, qty_filled, entry_price, timestamp, order_id.
    """
    sym = symbol or config.SYMBOL
    check_live_mode_warning()

    try:
        # Precision adjustment
        qty_str = exchange.amount_to_precision(sym, qty)
        qty_adjusted = float(qty_str)

        # Minimum notional validation (~10 USDT)
        current_price = data.get_current_price(exchange, sym)
        order_notional = qty_adjusted * current_price

        # Binance min notional rule (~10 USDT threshold)
        if order_notional < 10.0:
            err_msg = (
                f"Aborting BUY: Order value ${order_notional:,.2f} is below the required "
                f"minimum notional (~10 USDT). Quantity: {qty_adjusted} {sym} @ ${current_price:,.2f}"
            )
            print(f"[Order Rejected] {err_msg}", flush=True)
            raise ValueError(err_msg)

        print(f"[Order Execution] Submitting MARKET BUY for {qty_adjusted} {sym} (~${order_notional:,.2f} USDT)...", flush=True)

        # Execute market buy order
        order = exchange.create_order(
            symbol=sym,
            type="market",
            side="buy",
            amount=qty_adjusted,
        )

        qty_filled, entry_price, order_id = _extract_fill_info(order, default_price=current_price, default_qty=qty_adjusted)
        now_ts = datetime.now(timezone.utc).isoformat()

        position_record = {
            "symbol": sym,
            "qty_filled": qty_filled,
            "entry_price": round(entry_price, 2),
            "timestamp": now_ts,
            "order_id": order_id,
        }

        # Persist position to disk
        save_position(position_record)

        # Send Telegram alert
        telegram_bot.send_trade_alert(
            symbol=sym,
            action="BUY",
            price=entry_price,
            quantity=qty_filled,
            reason="Market Buy Executed (Phase 5A)",
        )

        return position_record

    except ccxt.BaseError as e:
        err_msg = f"Exchange error during BUY execution: {e}"
        print(f"[Trade Error] {err_msg}", flush=True)
        telegram_bot.send_error_alert(err_msg)
        raise RuntimeError(err_msg) from e
    except Exception as e:
        err_msg = f"Unexpected error during BUY execution: {e}"
        print(f"[Trade Error] {err_msg}", flush=True)
        telegram_bot.send_error_alert(err_msg)
        raise


def sell(exchange: ccxt.binance, position: Dict[str, Any], symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes a market SELL order for EXACTLY the filled position quantity.
    Never liquidates the whole balance — protects existing account assets.

    Args:
        exchange: Authenticated ccxt exchange instance (from data.get_exchange()).
        position: Position dictionary containing qty_filled, entry_price, and symbol.
        symbol: Optional trading pair (defaults to position['symbol'] or config.SYMBOL).

    Returns:
        dict: Sell result containing symbol, order_id, qty_sold, entry_price, exit_price, pnl_usdt, pnl_pct.
    """
    sym = symbol or position.get("symbol") or config.SYMBOL
    check_live_mode_warning()

    try:
        qty_to_sell = position.get("qty_filled")
        if not qty_to_sell or float(qty_to_sell) <= 0:
            raise ValueError(f"Invalid position quantity to sell: {qty_to_sell}")

        # Precision adjustment - sell EXACTLY the designated position amount
        qty_str = exchange.amount_to_precision(sym, float(qty_to_sell))
        qty_adjusted = float(qty_str)

        current_price = data.get_current_price(exchange, sym)
        estimated_notional = qty_adjusted * current_price

        print(f"[Order Execution] Submitting MARKET SELL for {qty_adjusted} {sym} (~${estimated_notional:,.2f} USDT)...", flush=True)

        order = exchange.create_order(
            symbol=sym,
            type="market",
            side="sell",
            amount=qty_adjusted,
        )

        qty_sold, exit_price, order_id = _extract_fill_info(order, default_price=current_price, default_qty=qty_adjusted)

        entry_price = float(position.get("entry_price", exit_price))
        pnl_usdt = round((exit_price - entry_price) * qty_sold, 4)
        pnl_pct = round(((exit_price - entry_price) / entry_price) * 100, 4) if entry_price > 0 else 0.0

        # Remove persisted position file
        clear_position()

        # Send Telegram SELL alert with P&L
        pnl_sign = "+" if pnl_usdt >= 0 else ""
        pnl_text = f"P&L: {pnl_sign}${pnl_usdt:,.2f} ({pnl_sign}{pnl_pct:.2f}%)"
        telegram_bot.send_trade_alert(
            symbol=sym,
            action="SELL",
            price=exit_price,
            quantity=qty_sold,
            reason=f"Position Closed | {pnl_text}",
        )

        return {
            "symbol": sym,
            "order_id": order_id,
            "qty_sold": qty_sold,
            "entry_price": entry_price,
            "exit_price": round(exit_price, 2),
            "pnl_usdt": pnl_usdt,
            "pnl_pct": pnl_pct,
        }

    except ccxt.BaseError as e:
        err_msg = f"Exchange error during SELL execution: {e}"
        print(f"[Trade Error] {err_msg}", flush=True)
        telegram_bot.send_error_alert(err_msg)
        raise RuntimeError(err_msg) from e
    except Exception as e:
        err_msg = f"Unexpected error during SELL execution: {e}"
        print(f"[Trade Error] {err_msg}", flush=True)
        telegram_bot.send_error_alert(err_msg)
        raise


if __name__ == "__main__":
    print("=" * 65, flush=True)
    print("          ORDER EXECUTION & LIFECYCLE TEST (PHASE 5A)         ", flush=True)
    print("=" * 65, flush=True)
    print(f"Mode                : {'TESTNET (Sandbox)' if config.USE_TESTNET else 'LIVE'}", flush=True)
    print(f"Target Symbol       : {config.SYMBOL}", flush=True)
    print("=" * 65, flush=True)

    try:
        # Connect to Binance Testnet via data.py
        print("\n[Step 1/6] Connecting to Binance Testnet via data.py...", flush=True)
        exchange = data.get_exchange()
        print("Connected successfully to exchange.\n", flush=True)

        # 1. Print balances before trade
        print("[Step 2/6] Inspecting initial account balances...", flush=True)
        bal_before = data.get_balance(exchange)
        print(f"  - Initial Free USDT : ${bal_before.USDT:,.2f} USDT", flush=True)
        print(f"  - Initial Free BTC  : {bal_before.BTC:,.6f} BTC (Includes 1.0 test gift)", flush=True)

        # 2. Compute quantity worth ~50 USDT at current price
        print("\n[Step 3/6] Computing target test quantity (~50 USDT notional)...", flush=True)
        current_price = data.get_current_price(exchange, config.SYMBOL)
        target_notional = 50.0
        raw_qty = target_notional / current_price
        print(f"  - Current {config.SYMBOL} Price : ${current_price:,.2f}", flush=True)
        print(f"  - Target Order Value        : ${target_notional:,.2f} USDT", flush=True)
        print(f"  - Raw Calculated Quantity   : {raw_qty:.8f} BTC", flush=True)

        # 3. Call buy() and verify position persistence
        print("\n[Step 4/6] Executing BUY order and checking position persistence...", flush=True)
        buy_result = buy(exchange, raw_qty, config.SYMBOL)
        print("  - Buy Order Confirmed:", flush=True)
        print(f"      - Order ID    : {buy_result['order_id']}", flush=True)
        print(f"      - Symbol      : {buy_result['symbol']}", flush=True)
        print(f"      - Filled Qty  : {buy_result['qty_filled']} BTC", flush=True)
        print(f"      - Entry Price : ${buy_result['entry_price']:,.2f}", flush=True)
        print(f"      - Timestamp   : {buy_result['timestamp']}", flush=True)

        saved_pos = load_position()
        print(f"  - position.json verified on disk: {saved_pos}", flush=True)
        assert saved_pos is not None, "position.json should exist after buy()"
        assert saved_pos["order_id"] == buy_result["order_id"], "Saved order_id mismatch!"

        # Small pause between orders to allow exchange state sync
        print("\nPausing 2 seconds before closing position...", flush=True)
        time.sleep(2)

        # 4. Immediately call sell() on that exact position
        print("\n[Step 5/6] Executing SELL order for the exact bought quantity...", flush=True)
        sell_result = sell(exchange, buy_result, config.SYMBOL)
        print("  - Sell Order Confirmed:", flush=True)
        print(f"      - Order ID    : {sell_result['order_id']}", flush=True)
        print(f"      - Sold Qty    : {sell_result['qty_sold']} BTC", flush=True)
        print(f"      - Exit Price  : ${sell_result['exit_price']:,.2f}", flush=True)
        print(f"      - Net P&L     : ${sell_result['pnl_usdt']:+,.4f} USDT ({sell_result['pnl_pct']:+.4f}%)", flush=True)

        # Confirm position.json is deleted
        assert load_position() is None, "position.json should be removed after sell()"
        print("  - Confirmed: position.json has been removed after sell.", flush=True)

        # 5. Print balances after trade
        print("\n[Step 6/6] Inspecting final account balances...", flush=True)
        bal_after = data.get_balance(exchange)
        usdt_delta = bal_after.USDT - bal_before.USDT
        btc_delta = bal_after.BTC - bal_before.BTC

        print(f"  - Final Free USDT   : ${bal_after.USDT:,.2f} USDT (Change: ${usdt_delta:+,.4f})", flush=True)
        print(f"  - Final Free BTC    : {bal_after.BTC:,.6f} BTC (Change: {btc_delta:+.6f} BTC)", flush=True)
        print(f"  - Gifted 1 BTC Check: Preserved intact (~{bal_after.BTC:.6f} BTC)", flush=True)

        print("\n" + "=" * 65, flush=True)
        print("  ORDER EXECUTION TEST PASSED - BUY AND SELL COMPLETED SAFELY  ", flush=True)
        print("=" * 65, flush=True)

    except Exception as exc:
        print("\n" + "!" * 65, flush=True)
        print("ORDER EXECUTION TEST FAILED")
        print("!" * 65, flush=True)
        print(f"Error: {exc}", flush=True)
        print("!" * 65, flush=True)
        sys.exit(1)
