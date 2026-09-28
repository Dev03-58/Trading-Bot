"""
Market Data & Exchange Connection Module (Phase 2)
Provides read-only access to Binance market data and account balances via ccxt.

Strictly READ-ONLY: Does not place, simulate, or prepare any orders.
"""

import sys
from typing import Optional, Tuple
import ccxt
import pandas as pd
import config


class Balance(tuple):
    """
    Account balance container that supports:
    - Tuple unpacking: usdt, btc = get_balance(exchange)
    - Dict key indexing: balance['USDT'], balance['BTC']
    - Attribute access: balance.usdt, balance.btc, balance.USDT, balance.BTC
    - Index access: balance[0], balance[1]
    - Dict-like .get(): balance.get('USDT')
    - Conversion to dict: balance.to_dict()
    """
    def __new__(cls, usdt: float, btc: float):
        return super().__new__(cls, (float(usdt), float(btc)))

    @property
    def usdt(self) -> float:
        return self[0]

    @property
    def btc(self) -> float:
        return self[1]

    @property
    def USDT(self) -> float:
        return self[0]

    @property
    def BTC(self) -> float:
        return self[1]

    def __getitem__(self, item):
        if isinstance(item, str):
            key = item.upper()
            if key == "USDT":
                return self[0]
            elif key == "BTC":
                return self[1]
            raise KeyError(f"Asset '{item}' not found in Balance. Available keys: 'USDT', 'BTC'")
        return super().__getitem__(item)

    def get(self, key: str, default: Optional[float] = None) -> Optional[float]:
        key_str = str(key).upper()
        if key_str == "USDT":
            return self[0]
        elif key_str == "BTC":
            return self[1]
        return default

    def to_dict(self) -> dict[str, float]:
        return {"USDT": self[0], "BTC": self[1]}

    def __repr__(self) -> str:
        return f"Balance(USDT={self[0]:,.2f}, BTC={self[1]:,.6f})"


def get_exchange() -> ccxt.binance:
    """
    Initializes and returns an authenticated ccxt Binance exchange instance.
    Uses credentials and testnet settings from config.py.
    Verifies connection by loading markets.
    """
    try:
        exchange_params = {
            "apiKey": config.BINANCE_API_KEY,
            "secret": config.BINANCE_API_SECRET,
            "enableRateLimit": True,
        }
        exchange = ccxt.binance(exchange_params)

        if config.USE_TESTNET:
            exchange.set_sandbox_mode(True)

        exchange.load_markets()
        return exchange

    except ccxt.AuthenticationError as e:
        hint = (
            "Authentication failed. Please verify BINANCE_API_KEY and BINANCE_API_SECRET in your .env file.\n"
            "Note: Binance Testnet API keys are generated at https://testnet.binance.vision and are distinct from live Binance keys."
        )
        raise RuntimeError(f"[Exchange Auth Error] {e}\nHint: {hint}") from e
    except ccxt.NetworkError as e:
        hint = "Network error connecting to Binance. Check your internet connection or proxy settings."
        raise RuntimeError(f"[Exchange Network Error] {e}\nHint: {hint}") from e
    except ccxt.BaseError as e:
        hint = "Binance exchange error. Please check your configuration settings in config.py / .env."
        raise RuntimeError(f"[Exchange Error] {e}\nHint: {hint}") from e
    except Exception as e:
        hint = "Unexpected error while initializing exchange connection."
        raise RuntimeError(f"[Connection Error] {e}\nHint: {hint}") from e


def get_candles(
    exchange: ccxt.binance,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """
    Fetches OHLCV historical candlestick data.
    
    Args:
        exchange: Initialized ccxt exchange instance.
        symbol: Trading pair (defaults to config.SYMBOL).
        timeframe: Candle interval (defaults to config.TIMEFRAME).
        limit: Number of candles to fetch (default: 200).
        
    Returns:
        pd.DataFrame with columns: timestamp (readable datetime), open, high, low, close, volume.
    """
    sym = symbol or config.SYMBOL
    tf = timeframe or config.TIMEFRAME

    try:
        ohlcv = exchange.fetch_ohlcv(symbol=sym, timeframe=tf, limit=limit)
        if not ohlcv:
            raise ValueError(f"No candlestick data returned for symbol {sym} and timeframe {tf}.")

        columns = ["timestamp", "open", "high", "low", "close", "volume"]
        df = pd.DataFrame(ohlcv, columns=columns)

        # Convert timestamp (epoch ms) to readable datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        # Ensure numeric types for price and volume columns
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        return df

    except ccxt.BaseError as e:
        raise RuntimeError(f"[Market Data Error] Failed to fetch candles for {sym} ({tf}): {e}") from e
    except Exception as e:
        raise RuntimeError(f"[Candle Error] Unexpected error while fetching candles: {e}") from e


def get_balance(exchange: ccxt.binance) -> Balance:
    """
    Fetches account balances and returns free USDT and free BTC.
    
    Args:
        exchange: Initialized ccxt exchange instance.
        
    Returns:
        Balance: Object containing free USDT and free BTC balances,
                 supporting tuple unpacking (usdt, btc), dict indexing ['USDT'],
                 and attribute access (.usdt / .USDT).
    """
    try:
        balance_data = exchange.fetch_balance()
        free_balances = balance_data.get("free", {})
        
        usdt_free = float(free_balances.get("USDT", 0.0) or 0.0)
        btc_free = float(free_balances.get("BTC", 0.0) or 0.0)
        
        return Balance(usdt=usdt_free, btc=btc_free)

    except ccxt.AuthenticationError as e:
        hint = "Authentication failed fetching balance. Check API keys and ensure they have read permissions enabled."
        raise RuntimeError(f"[Balance Auth Error] {e}\nHint: {hint}") from e
    except ccxt.BaseError as e:
        raise RuntimeError(f"[Balance Error] Failed to fetch account balance: {e}") from e
    except Exception as e:
        raise RuntimeError(f"[Balance Error] Unexpected error fetching balance: {e}") from e


def get_current_price(exchange: ccxt.binance, symbol: Optional[str] = None) -> float:
    """
    Fetches the latest market price for a symbol.
    """
    sym = symbol or config.SYMBOL
    try:
        ticker = exchange.fetch_ticker(sym)
        last_price = ticker.get("last")
        if last_price is None:
            raise ValueError(f"Ticker for {sym} did not contain a 'last' price.")
        return float(last_price)
    except ccxt.BaseError as e:
        raise RuntimeError(f"[Ticker Error] Failed to fetch ticker for {sym}: {e}") from e
    except Exception as e:
        raise RuntimeError(f"[Ticker Error] Unexpected error fetching ticker: {e}") from e


if __name__ == "__main__":
    print("=" * 65)
    print("        BINANCE EXCHANGE CONNECTION & MARKET DATA TEST        ")
    print("=" * 65)

    try:
        # 1. Connect to exchange
        print("[1/4] Connecting to Binance exchange...")
        exchange = get_exchange()
        mode_str = "TESTNET" if config.USE_TESTNET else "LIVE"
        print(f"      Connection Status : Connected successfully")
        print(f"      Connection Mode   : {mode_str}")
        print(f"      Configured Symbol : {config.SYMBOL}")
        print(f"      Timeframe         : {config.TIMEFRAME}")

        # 2. Fetch current price
        print(f"\n[2/4] Fetching current {config.SYMBOL} price...")
        current_price = get_current_price(exchange, config.SYMBOL)
        print(f"      Current Price     : ${current_price:,.2f}")

        # 3. Fetch candles and display last 5 as a table
        print(f"\n[3/4] Fetching {config.TIMEFRAME} OHLCV candles for {config.SYMBOL}...")
        df_candles = get_candles(exchange, config.SYMBOL, config.TIMEFRAME, limit=200)
        print(f"      Retrieved {len(df_candles)} candles. Last 5 candles:")
        print("-" * 65)
        print(df_candles.tail(5).to_string(index=False))
        print("-" * 65)

        # 4. Fetch account balance
        print("\n[4/4] Fetching account balance...")
        balance = get_balance(exchange)
        print(f"      Free USDT Balance : ${balance.USDT:,.2f} USDT")
        print(f"      Free BTC Balance  : {balance.BTC:,.6f} BTC")

        print("\n" + "=" * 65)
        print("          ALL MARKET DATA AND BALANCE CHECKS PASSED           ")
        print("=" * 65)

    except Exception as exc:
        print("\n" + "!" * 65)
        print("EXCHANGE CONNECTION / DATA FETCH FAILED")
        print("!" * 65)
        print(f"Error: {exc}")
        print("\nHelpful Hints:")
        print("1. If using TESTNET (USE_TESTNET=True in config.py):")
        print("   - API keys MUST be created at https://testnet.binance.vision (NOT live binance.com)")
        print("   - Ensure testnet funds are requested from the testnet faucet if balance is 0")
        print("2. If using LIVE (USE_TESTNET=False in config.py):")
        print("   - Ensure your API key has 'Enable Reading' permission enabled in Binance")
        print("   - Ensure your IP access restrictions permit requests from your current IP")
        print("3. Check your network or firewall connection to Binance API endpoints")
        print("!" * 65)
        sys.exit(1)
