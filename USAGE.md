# StockMind AI — Usage Guide

How to use the app day to day. For installing and running it, see
[README.md](README.md); for Kubernetes, see [k8s/README.md](k8s/README.md).

> StockMind is an analysis tool, not an auto-trader. Nothing is bought or sold
> unless you click Buy/Sell and confirm the order ticket yourself.

---

## 1. First-time setup

Do these once, in **Settings**:

| Step | Where | Why |
|---|---|---|
| Create an account and sign in | Top-right menu → Create account | Alerts, orders, portfolio, AI settings and model training all require login. Market data, the scanner and predictions work as a guest. |
| Upstox analytics token | `UPSTOX_ANALYTICS_TOKEN` in `backend/.env` | Powers all market data. Settings → Market data shows **Valid** when it works. |
| Upstox / Kite app credentials | Settings → Broker API Credentials | Needed only to connect a personal broker account (portfolio + live orders). |
| Connect your broker account | Settings → Linked Accounts, or the Portfolio page | Required for Portfolio, Buy/Sell, and "Add or remove?" recommendations. |
| AI provider key(s) | Settings → AI Commentary | Add an Anthropic (Claude) key, a Google (Gemini) key, or both, then pick the **Active model**. Gemini keys from [aistudio.google.com/apikey](https://aistudio.google.com/apikey) include a free, rate-limited tier. |
| Capital and risk per trade | Settings → Portfolio & risk | Drives position sizes everywhere (default ₹2,00,000 at 0.75% risk). |

**Two different Upstox tokens — don't mix them up:**
- The **analytics token** (in `.env`) is long-lived and used for market data.
- Your **personal connection** (OAuth, from "Connect Upstox") is short-lived by
  Upstox's design — expect to reconnect roughly daily. Error messages now say
  which of the two failed.

---

## 2. Pages

### Dashboard
Market regime, index moves, FII/DII flows and sector breadth at a glance.

### Market Scanner
Live technical scan of the approved sector universe (69 stocks).
- **Presets** (top chips) for common setups; **filters** for sector, setup, signal, RSI, volume and day change. Click a column header to sort.
- **Term chips** (All / Short / Mid / Long) segregate the list by holding period. Stocks get a term automatically when the scanner first flags them, based on the setup type (momentum breakout & retest → short, early-stage breakout → mid, quality pullback → long).
- **Added** column shows the date a stock was first flagged — it never resets on later scans.
- **Term dropdown** on any row tracks or reclassifies a stock; **+ Add to watchlist** tracks any stock even if it isn't in the scan.
- **Buy / Sell** open an order ticket pre-filled with the entry zone, stop and target. The **bell** creates a "notify me on BUY signal" alert.
- **Why** expands the reasoning and an **AI take** for that stock. **Batch AI take** analyzes the top 8 currently-shown stocks in one cheaper call.
- Rows you already hold are tagged with ADD / HOLD / REDUCE instead of a generic signal.

### Daily Signals
The daily stock list grouped by horizon (short / mid / long) or by action (Buy now / Watch & retest / Wait / Avoid), with position sizing from your risk settings. Existing holdings appear in these groups too, tagged with ADD / HOLD / REDUCE.

### Predictions
Search a stock to see up / flat / down probabilities, expected return and a range for 1D, 3D, 5D, 10D and 20D. The **Model** column shows **Trained model** (your promoted LightGBM champion) or **Baseline only** (rule-based fallback — click it to go train one). Probabilities are estimates, not promises.

### Stock Report
A full research document for one stock: verdict, **Chart Analysis**, thesis with AI commentary, trade plan, multi-horizon outlook, fundamentals and news. **Export** downloads it as Markdown.

**Chart Analysis** (also on each stock's live page):
- Real candlesticks with volume and 20/50/200-day moving averages, from Upstox data.
- **Hover any candle** for its pattern (Doji, Hammer, Engulfing, Morning/Evening Star…) and what would confirm it.
- On **1D**, choose **1m / 5m / 15m / 30m / 1h** candles. The chart live-updates on your refresh interval without losing zoom.
- **Drag the handle** under the chart to resize; the **expand icon** opens full screen (Esc to exit).

### Portfolio
Live holdings, positions, P&L, funds and allocation from your connected broker. The **Add or remove?** column runs a full analysis on every holding:
- **ADD** — the setup supports buying more (the + button opens a pre-filled buy).
- **HOLD** — no clear action either way.
- **REDUCE** — technicals have turned negative (the ↓ button opens a pre-filled sell).

### Alerts
Price, day-change and **BUY-signal** alerts, checked against live data every minute while the app is open. A triggered BUY-signal alert shows the entry zone and stop loss at the moment it fired. Create them here or from the bell icon on Scanner, Daily Signals and Stock Report.

### AI Prompt
The system prompt every AI commentary call uses (single-stock and batch, Claude and Gemini). Edit and **Save prompt** (requires sign-in), or **Suggest** a draft based on the current market regime. A saved change applies to the very next AI call — previously cached commentary is automatically invalidated.

### Settings
Account, broker and AI credentials, model training, risk, display/notification preferences, system status, and dev-only service restart buttons.

---

## 3. Recurring workflows

### Retraining the prediction model
1. Settings → Model Training → **Train new model** (a minute or two).
2. Review the new challenger's accuracy per horizon in the list.
3. Click **Promote** to make it live. Nothing changes until you promote — training never swaps the live model on its own.

The promoted model is used immediately by Predictions, the Scanner's P(up) column, and the Stock Report outlook. Retrain whenever you want fresher data behind it.

### Changing the AI's analysis style
Edit the **AI Prompt** page and save. To switch between Claude and Gemini, change the **Active model** in Settings → AI Commentary — both keys can stay saved.

### Placing an order
Buy/Sell (Scanner, Stock Report or Portfolio) → review the pre-filled order ticket → confirm. Target and stop-loss brackets show up under Portfolio → Active Brackets, where you can cancel them.

---

## 4. Costs

- **AI commentary** bills your Claude or Gemini account per uncached request. Results are cached per stock until its data or the prompt changes, so revisiting a stock doesn't re-bill. Batch AI take is one call for up to 8 stocks. Prices per model are shown in Settings.
- **Model training** runs locally — no API cost.

---

## 5. Troubleshooting

| Message | Meaning | Fix |
|---|---|---|
| "Your personal Upstox connection was rejected…" | Your broker OAuth token expired (normal, roughly daily). | Reconnect Upstox in Settings or Portfolio. |
| "The shared analytics token … was rejected" | `UPSTOX_ANALYTICS_TOKEN` is invalid, even if its listed expiry is far off (e.g. a newer one was generated). | Generate a fresh token and update `backend/.env`, then restart the backend. |
| "Your session expired. Please sign in again." | Your app login expired while you were using it (24-hour lifetime). | Sign in again. A token that expired while the app was closed is now cleared quietly on load. |
| "… API key not configured" on an AI take | The active model's provider has no key saved. | Add the key, or switch the active model, in Settings → AI Commentary. |
| "Baseline only" in Predictions | No trained model is promoted for that horizon. | Train and promote one (section 3). |
| Backend log shows `insecure_default_secrets` | `JWT_SECRET` / `ENCRYPTION_KEY` are unset, so publicly-known defaults are in use. | Set real values in `backend/.env`. The backend refuses to start in production without them. Note: changing `JWT_SECRET` while `ENCRYPTION_KEY` is unset changes the derived encryption key, so re-enter saved broker/AI keys afterwards. |
