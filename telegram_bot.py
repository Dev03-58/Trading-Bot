import logging
import requests
from typing import Optional
import config

logger = logging.getLogger("TelegramNotifier")


def is_configured() -> bool:
    """Checks if Telegram bot token and chat ID are configured."""
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_BOT_TOKEN.strip() and 
                config.TELEGRAM_CHAT_ID and config.TELEGRAM_CHAT_ID.strip())


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """
    Sends a message to the configured Telegram chat.
    Returns True if sent successfully, False otherwise.
    """
    if not is_configured():
        print("[Telegram Alert Skipped] Bot token or Chat ID not configured in .env.")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN.strip()}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID.strip(),
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()

        if response.status_code == 200 and data.get("ok"):
            print("[Telegram] Message delivered successfully.")
            return True
        else:
            error_desc = data.get("description", response.text)
            print(f"[Telegram Error] HTTP {response.status_code}: {error_desc}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"[Telegram Network Error] {e}")
        return False


def send_startup_alert() -> bool:
    """Sends a notification that the trading bot has started."""
    mode = "TESTNET (Paper Trading)" if config.USE_TESTNET else "LIVE TRADING"
    message = (
        f"🚀 <b>Trading Bot Started</b>\n\n"
        f"• <b>Symbol:</b> {config.SYMBOL}\n"
        f"• <b>Timeframe:</b> {config.TIMEFRAME}\n"
        f"• <b>Mode:</b> {mode}\n"
        f"• <b>Risk/Trade:</b> {config.RISK_PER_TRADE_PCT}%\n"
        f"• <b>SL / TP:</b> {config.STOP_LOSS_PCT}% / {config.TAKE_PROFIT_PCT}%\n"
    )
    return send_message(message)


def send_trade_alert(
    symbol: str,
    action: str,
    price: float,
    quantity: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    reason: Optional[str] = None,
) -> bool:
    """Formats and sends a trade execution alert."""
    emoji = "🟢" if action.upper() in ("BUY", "LONG") else "🔴"
    message = (
        f"{emoji} <b>Trade Alert: {action.upper()}</b>\n\n"
        f"• <b>Symbol:</b> {symbol}\n"
        f"• <b>Price:</b> ${price:,.4f}\n"
        f"• <b>Quantity:</b> {quantity}\n"
    )
    if stop_loss is not None:
        message += f"• <b>Stop Loss:</b> ${stop_loss:,.4f}\n"
    if take_profit is not None:
        message += f"• <b>Take Profit:</b> ${take_profit:,.4f}\n"
    if reason:
        message += f"• <b>Reason:</b> {reason}\n"

    return send_message(message)


def send_error_alert(error_msg: str) -> bool:
    """Formats and sends an error alert."""
    message = f"⚠️ <b>Trading Bot Warning/Error</b>\n\n<code>{error_msg}</code>"
    return send_message(message)


def send_daily_report(
    balance_str: str,
    position_str: str,
    trades_count: int,
    uptime_str: str,
    errors_count: int,
) -> bool:
    """Formats and sends a 24-hour daily summary report."""
    message = (
        f"📊 <b>Daily Bot Report</b>\n"
        f"<i>Soak-Test Status Update</i>\n\n"
        f"• <b>Current Balance:</b> {balance_str}\n"
        f"• <b>Open Position:</b> {position_str}\n"
        f"• <b>Trades Since Start:</b> {trades_count}\n"
        f"• <b>Bot Uptime:</b> {uptime_str}\n"
        f"• <b>Errors (Since Last Report):</b> {errors_count}\n"
    )
    return send_message(message)


if __name__ == "__main__":
    print("Testing Telegram Notifier Module...")
    if not is_configured():
        print("\n" + "=" * 50)
        print("TELEGRAM CONFIGURATION REQUIRED")
        print("=" * 50)
        print("Telegram keys are currently empty in .env.")
        print("\nTo enable Telegram alerts:")
        print("1. Open Telegram and search for '@BotFather'")
        print("2. Send /newbot and follow instructions to get your BOT TOKEN")
        print("3. Start a chat with your bot or send it a message")
        print("4. Search for '@userinfobot' to get your numeric CHAT ID")
        print("5. Paste values into .env:")
        print("   TELEGRAM_BOT_TOKEN=your_token_here")
        print("   TELEGRAM_CHAT_ID=your_chat_id_here")
        print("=" * 50)
    else:
        print("Credentials detected. Sending test message to Telegram...")
        test_success = send_message("🧪 <b>Test Notification</b>\n\nYour trading bot Telegram alerts are working properly!")
        if test_success:
            print("Test message sent successfully!")
        else:
            print("Failed to send test message. Check your token and chat ID.")
