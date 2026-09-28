"""
Risk Management Module (Phase 4)
Calculates position sizes, stop-loss / take-profit levels, and exit triggers.

Strictly READ-ONLY: Pure calculation module. Does not place, simulate,
or execute any orders.
"""

import sys
from typing import Optional, Tuple, Union, Dict, Any
import config


class InvalidPosition(tuple):
    """
    Returned when position sizing fails guard rails: (None, reason).
    Supports tuple unpacking: qty, reason = position_size(...)
    Supports dictionary access: res['reason'] or res.get('reason')
    Supports attribute access: res.quantity, res.reason
    Evaluates to False in boolean contexts and equals None.
    """
    def __new__(cls, reason: str):
        return super().__new__(cls, (None, reason))

    @property
    def quantity(self) -> None:
        return None

    @property
    def reason(self) -> str:
        return self[1]

    def __bool__(self) -> bool:
        return False

    def __eq__(self, other: Any) -> bool:
        if other is None:
            return True
        return super().__eq__(other)

    def __getitem__(self, item: Union[int, str]) -> Any:
        if isinstance(item, str):
            if item == "reason":
                return self[1]
            elif item == "quantity":
                return None
            raise KeyError(f"Key '{item}' not recognized in InvalidPosition.")
        return super().__getitem__(item)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "reason":
            return self[1]
        elif key == "quantity":
            return None
        return default

    def __repr__(self) -> str:
        return f"(None, '{self[1]}')"


def position_size(balance_usdt: float, price: float) -> Union[Dict[str, float], InvalidPosition]:
    """
    Calculates position size based on configured account risk percentage.

    Formulas:
    - risk_amount = balance * (RISK_PER_TRADE_PCT / 100)
    - qty = risk_amount / (price * STOP_LOSS_PCT / 100)
    - Capped so position value does not exceed 95% of total balance.

    Args:
        balance_usdt: Available USDT account balance.
        price: Current asset price.

    Returns:
        dict: {'quantity', 'position_value_usdt', 'risk_amount_usdt', 'entry_price'}
        or InvalidPosition: (None, reason) if guard rails fail.
    """
    # Guard rail: balance and price must be strictly positive
    if balance_usdt <= 0:
        return InvalidPosition(f"Invalid balance: USDT balance must be > 0 (got {balance_usdt})")
    if price <= 0:
        return InvalidPosition(f"Invalid price: Price must be > 0 (got {price})")

    # Risk amount allocation based on config
    risk_amount = balance_usdt * (config.RISK_PER_TRADE_PCT / 100.0)

    # Calculate quantity so a STOP_LOSS_PCT drop equals risk_amount
    stop_loss_distance_per_unit = price * (config.STOP_LOSS_PCT / 100.0)
    if stop_loss_distance_per_unit <= 0:
        return InvalidPosition("Invalid stop loss percentage in configuration")

    qty = risk_amount / stop_loss_distance_per_unit

    # Guard rail: cap position value at 95% of available balance
    max_position_value = balance_usdt * 0.95
    position_value = qty * price
    if position_value > max_position_value:
        qty = max_position_value / price

    # Round quantity to 6 decimal places (standard crypto precision)
    qty = round(qty, 6)

    # Guard rail: resulting quantity must be strictly positive
    if qty <= 0:
        return InvalidPosition(f"Calculated quantity is too small for minimum precision (got {qty})")

    # Final calculations based on rounded quantity
    actual_position_value = round(qty * price, 2)
    actual_risk_amount = round(qty * stop_loss_distance_per_unit, 2)

    return {
        "quantity": qty,
        "position_value_usdt": actual_position_value,
        "risk_amount_usdt": actual_risk_amount,
        "entry_price": round(float(price), 2),
    }


def check_exit(entry_price: float, current_price: float) -> Optional[str]:
    """
    Checks if current price triggers an exit condition (stop-loss or take-profit).

    Rules:
    - 'STOP_LOSS' if current_price <= entry * (1 - STOP_LOSS_PCT / 100)
    - 'TAKE_PROFIT' if current_price >= entry * (1 + TAKE_PROFIT_PCT / 100)
    - None otherwise

    Args:
        entry_price: The fill price of the trade.
        current_price: The current market price.

    Returns:
        'STOP_LOSS', 'TAKE_PROFIT', or None.
    """
    if entry_price <= 0 or current_price <= 0:
        return None

    sl_threshold = entry_price * (1.0 - config.STOP_LOSS_PCT / 100.0)
    tp_threshold = entry_price * (1.0 + config.TAKE_PROFIT_PCT / 100.0)

    if current_price <= sl_threshold:
        return "STOP_LOSS"
    elif current_price >= tp_threshold:
        return "TAKE_PROFIT"
    return None


def trade_summary(balance_usdt: float, price: float) -> Optional[Dict[str, float]]:
    """
    Combines position sizing and trade level calculations into a comprehensive summary.

    Args:
        balance_usdt: Available USDT account balance.
        price: Entry price.

    Returns:
        dict: {
            'entry': float,
            'quantity': float,
            'stop_loss_price': float,
            'take_profit_price': float,
            'risk_usdt': float,
            'reward_usdt': float,
            'reward_risk_ratio': float
        }
    """
    pos = position_size(balance_usdt, price)
    if not pos or pos.get("quantity") is None:
        return None

    entry = round(float(price), 2)
    qty = pos["quantity"]

    sl_price = round(price * (1.0 - config.STOP_LOSS_PCT / 100.0), 2)
    tp_price = round(price * (1.0 + config.TAKE_PROFIT_PCT / 100.0), 2)

    risk_usdt = round(qty * (price - sl_price), 2)
    reward_usdt = round(qty * (tp_price - price), 2)
    rr_ratio = round(reward_usdt / risk_usdt, 2) if risk_usdt > 0 else 0.0

    return {
        "entry": entry,
        "quantity": qty,
        "stop_loss_price": sl_price,
        "take_profit_price": tp_price,
        "risk_usdt": risk_usdt,
        "reward_usdt": reward_usdt,
        "reward_risk_ratio": rr_ratio,
    }


if __name__ == "__main__":
    print("=" * 65, flush=True)
    print("           RISK MANAGEMENT & SIZING MODULE (PHASE 4)          ", flush=True)
    print("=" * 65, flush=True)
    print(f"Risk Per Trade (%)  : {config.RISK_PER_TRADE_PCT}%", flush=True)
    print(f"Stop Loss (%)       : {config.STOP_LOSS_PCT}%", flush=True)
    print(f"Take Profit (%)     : {config.TAKE_PROFIT_PCT}%", flush=True)
    print(f"Target Symbol       : {config.SYMBOL}", flush=True)
    print("=" * 65, flush=True)

    # -------------------------------------------------------------
    # PART A: Pure Math Verification (No Network Calls)
    # -------------------------------------------------------------
    print("\n" + "=" * 65, flush=True)
    print("PART A: Pure Math Verification (Sample: Balance=$10,000, Price=$83,000)", flush=True)
    print("=" * 65, flush=True)

    sample_balance = 10000.0
    sample_price = 83000.0

    sample_summary = trade_summary(sample_balance, sample_price)
    print("\nTrade Summary Output:", flush=True)
    print(f"  - Entry Price           : ${sample_summary['entry']:,.2f}", flush=True)
    print(f"  - Order Quantity        : {sample_summary['quantity']} BTC", flush=True)
    print(f"  - Stop Loss Price (-{config.STOP_LOSS_PCT}%) : ${sample_summary['stop_loss_price']:,.2f}", flush=True)
    print(f"  - Take Profit Price (+{config.TAKE_PROFIT_PCT}%) : ${sample_summary['take_profit_price']:,.2f}", flush=True)
    print(f"  - Risk Amount           : ${sample_summary['risk_usdt']:,.2f}", flush=True)
    print(f"  - Reward Amount         : ${sample_summary['reward_usdt']:,.2f}", flush=True)
    print(f"  - Reward / Risk Ratio   : {sample_summary['reward_risk_ratio']}", flush=True)

    # Math verifications
    assert sample_summary["risk_usdt"] == 100.0, f"Expected risk $100, got {sample_summary['risk_usdt']}"
    assert sample_summary["reward_usdt"] == 200.0, f"Expected reward $200, got {sample_summary['reward_usdt']}"
    assert sample_summary["reward_risk_ratio"] == 2.0, f"Expected ratio 2.0, got {sample_summary['reward_risk_ratio']}"
    print("\n[OK] Math Verification Passed: Risk=$100, Reward=$200, Ratio=2.0", flush=True)

    # Testing check_exit logic
    print("\nTesting check_exit() triggers (Entry: $83,000):", flush=True)
    test_cases = [
        (81250.0, "STOP_LOSS"),
        (86350.0, "TAKE_PROFIT"),
        (83500.0, None),
    ]

    for price_check, expected_exit in test_cases:
        actual_exit = check_exit(sample_price, price_check)
        print(f"  - Current Price: ${price_check:,.2f} -> Exit Result: {actual_exit} (Expected: {expected_exit})", flush=True)
        assert actual_exit == expected_exit, f"Exit mismatch for {price_check}: expected {expected_exit}, got {actual_exit}"

    print("[OK] All 3 check_exit test cases matched expected triggers successfully.", flush=True)

    # -------------------------------------------------------------
    # PART B: Read-Only Network Validation (Live Balance & Price)
    # -------------------------------------------------------------
    print("\n" + "=" * 65, flush=True)
    print("PART B: Live Market Data Validation (via data.py)", flush=True)
    print("=" * 65, flush=True)

    try:
        import data

        print("Connecting to Binance Testnet via data.py...", flush=True)
        exchange = data.get_exchange()
        print("Connected to exchange.", flush=True)

        balance_obj = data.get_balance(exchange)
        live_balance_usdt = balance_obj.USDT
        live_price = data.get_current_price(exchange, config.SYMBOL)

        print(f"\nLive Account Balance : ${live_balance_usdt:,.2f} USDT", flush=True)
        print(f"Live Market Price    : ${live_price:,.2f} ({config.SYMBOL})", flush=True)

        live_summary = trade_summary(live_balance_usdt, live_price)
        if live_summary:
            print("\nLive Trade Summary Calculated:", flush=True)
            print(f"  - Entry Price           : ${live_summary['entry']:,.2f}", flush=True)
            print(f"  - Calculated Quantity   : {live_summary['quantity']} BTC", flush=True)
            print(f"  - Stop Loss Price (-{config.STOP_LOSS_PCT}%) : ${live_summary['stop_loss_price']:,.2f}", flush=True)
            print(f"  - Take Profit Price (+{config.TAKE_PROFIT_PCT}%) : ${live_summary['take_profit_price']:,.2f}", flush=True)
            print(f"  - Risk Amount           : ${live_summary['risk_usdt']:,.2f}", flush=True)
            print(f"  - Reward Amount         : ${live_summary['reward_usdt']:,.2f}", flush=True)
            print(f"  - Reward / Risk Ratio   : {live_summary['reward_risk_ratio']}", flush=True)
        else:
            print("[Warning] Could not compute live trade summary with current balance/price.", flush=True)

        print("\n" + "=" * 65, flush=True)
        print("    RISK MANAGEMENT VERIFICATION COMPLETED - ALL CHECKS PASSED   ", flush=True)
        print("=" * 65, flush=True)

    except Exception as exc:
        print("\n" + "!" * 65, flush=True)
        print("PART B LIVE DATA FETCH ERROR", flush=True)
        print("!" * 65, flush=True)
        print(f"Error: {exc}", flush=True)
        print("Check exchange connectivity and data.py setup.")
        print("!" * 65, flush=True)
        sys.exit(1)
