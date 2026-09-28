import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Trading Configuration
SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"
USE_TESTNET = True

# Risk and Execution Parameters
RISK_PER_TRADE_PCT = 1.0
STOP_LOSS_PCT = 2.0
TAKE_PROFIT_PCT = 4.0
SLEEP_SECONDS = 300
DAILY_REPORT_HOUR_UTC = 0

# API Keys & Secrets
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def mask_secret(value: str | None) -> str:
    """Masks secret strings, showing only the first 4 characters."""
    if not value or not value.strip():
        return "[NOT SET]"
    val = value.strip()
    if len(val) <= 4:
        return val[:4] + "****"
    return val[:4] + "*" * min(len(val) - 4, 16)


def print_banner():
    banner = "=" * 50 + "\n"
    banner += "        CRYPTO TRADING BOT CONFIGURATION        \n"
    banner += "=" * 50 + "\n"
    banner += f"Symbol              : {SYMBOL}\n"
    banner += f"Timeframe           : {TIMEFRAME}\n"
    banner += f"Use Testnet         : {USE_TESTNET}\n"
    banner += f"Risk Per Trade (%)  : {RISK_PER_TRADE_PCT}%\n"
    banner += f"Stop Loss (%)       : {STOP_LOSS_PCT}%\n"
    banner += f"Take Profit (%)     : {TAKE_PROFIT_PCT}%\n"
    banner += f"Sleep Seconds       : {SLEEP_SECONDS}s\n"
    banner += f"Daily Report (UTC)  : {DAILY_REPORT_HOUR_UTC:02d}:00 UTC\n"
    banner += "-" * 50 + "\n"
    banner += f"Binance API Key     : {mask_secret(BINANCE_API_KEY)}\n"
    banner += f"Binance API Secret  : {mask_secret(BINANCE_API_SECRET)}\n"
    banner += f"Telegram Bot Token  : {mask_secret(TELEGRAM_BOT_TOKEN)}\n"
    banner += f"Telegram Chat ID    : {mask_secret(TELEGRAM_CHAT_ID)}\n"
    banner += "=" * 50
    print(banner)


if __name__ == "__main__":
    print_banner()
