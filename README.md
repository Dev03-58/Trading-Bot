Crypto Trading Bot - BTC/USDT
A modular, backtested cryptocurrency trading bot built in Python. It runs onBinance Spot (testnet first, live-ready), enforces strict risk management, andreports every action to Telegram.

Status: 14-day paper-trading soak test in progress. Deployed strategy:EMA crossover on the 1h timeframe, selected through systematic research(results below).

Features
Live market data from Binance via CCXT (testnet and live modes)
Strategy engine: EMA(9/21) crossover with RSI(14) filter, signals computedon closed candles only to prevent flickering
Risk management: 1% risk per trade, 2% stop-loss, 4% take-profit (2:1reward-to-risk), position sizing derived from account balance
Telegram alerts: trade entries and exits with P&L, error alerts, daily reports
Crash-safe design: open positions persisted to disk (position.json) andrecovered automatically after restarts
Self-healing loop: transient network errors are logged and skipped, startupconnection retries (10 attempts, 30s apart), never-crash architecture
Built-in backtester: 90+ days of historical data, 0.1% fee per side, zerolook-ahead bias, conservative stop-loss priority
Architecture
data.py         Binance connection, OHLCV candles, balances (CCXT)strategy.py     EMA/RSI indicators, BUY / SELL / HOLD signalsrisk.py         Position sizing, stop-loss / take-profit logictrader.py       Market orders, position persistence, P&L trackingmain.py         Main loop: evaluate, decide, execute, alerttelegram_bot.py Alerts to your phonebacktest.py     Strategy research lab (variants, timeframes, regimes)
Research: Why This Strategy
Three strategy families were tested across multiple timeframes and threenon-overlapping 90-day market regimes (bull, chop, correction), with realisticfees and no look-ahead bias:

Setup	Trades	Win Rate	Profit Factor	90d Return	Verdict
EMA cross + RSI, 15m	209	19.1%	0.53	-16.6%	Rejected: fee and whipsaw losses
EMA cross + RSI, 1h	45	33.3%	1.33	+3.8%	Deployed
RSI mean-reversion, 15m	43	48.8%	0.68	-3.9%	Rejected: falling knives
RSI mean-reversion, 1h	14	78.6%	3.42*	+6.3%	Rejected: failed out-of-sample
*High profit factor on 14 trades is statistically meaningless. Rejected honestly.

Key findings:

Timeframe dominates: identical logic went from -16.6% (15m) to +3.8% (1h).Noise and fees killed 209 micro-trades, consuming about $1,900 in fees.
Trend-following is armor: over 270 days it returned +1.7% while Buy and Holdlost -7.3%. It lags in bull markets but avoids the worst of bear markets.
Mean reversion without a trend filter repeatedly buys falling knives indowntrends and multiplies stop-loss events.
Deployment gates were pre-registered: profitable in all 3 regimes, profitfactor >= 1.5, at least 10 trades, max drawdown <= 15%. The 1h trend setupwas the best structural survivor and was deployed for live validation.
Setup
git clone https://github.com/Dev03-58/Trading-Bot.gitcd Trading-Botpython -m venv venvvenv\Scripts\activatepip install -r requirements.txt
Create a .env file (never committed, protected by .gitignore):

BINANCE_API_KEY=your_testnet_keyBINANCE_API_SECRET=your_testnet_secretTELEGRAM_BOT_TOKEN=your_botfather_tokenTELEGRAM_CHAT_ID=your_chat_id
Free testnet keys: testnet.binance.vision (login with GitHub)
Telegram: create a bot via @BotFather, get your chat ID via @userinfobot
Run:

python backtest.pypython main.py
Configuration (config.py)
Setting	Value	Meaning
SYMBOL	BTC/USDT	Trading pair
TIMEFRAME	1h	Candle timeframe
USE_TESTNET	True	Sandbox mode
RISK_PER_TRADE_PCT	1.0	Max percent of balance risked per trade
STOP_LOSS_PCT / TAKE_PROFIT_PCT	2.0 / 4.0	2:1 reward-to-risk
Roadmap
 Modular bot: data, strategy, risk, execution, alerts
 Backtest framework with fee modeling and regime testing
 Strategy research cycle 1: trend vs mean-reversion, 3 timeframes
 14-day soak test (in progress)
 Research cycle 2: multi-pair portfolio, regime filters
 Small-capital live trading ($10-50) after soak gate review
Disclaimer
This project is for educational purposes only. Most trading bots lose money,and backtest results do not guarantee future performance. Trade only withmoney you can afford to lose. Nothing here is financial advice.
