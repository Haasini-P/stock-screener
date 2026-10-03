# StockMind AI — Institutional-Grade Stock Intelligence Platform

> Real-time stock analytics platform with ML-powered predictions, explainability, and continuous learning for Indian equities (NSE/BSE). Built on Upstox V3 APIs.

**⚠️ This is an analytical decision-support system, NOT an autonomous trading system.**  
Predictions are probabilistic estimates, not certainties. No trades are executed automatically.

**Using the app:** see [USAGE.md](USAGE.md) for a page-by-page guide — setup, the scanner, predictions, stock reports, portfolio recommendations, alerts, AI commentary (Claude/Gemini), model training, and troubleshooting.

---

## Quick Start (Development)

### Prerequisites

- **Python 3.10+** — Backend
- **Node.js 18+** — Frontend
- **Git**

No PostgreSQL or Redis required for dev — SQLite is used by default.

### 1. Clone & Setup Backend

```bash
cd "Stock screener"

# Install backend dependencies (lightweight dev set)
cd backend
pip install -r requirements-dev.txt

# Create .env file (optional — defaults work out of the box)
copy ..\.env.example .env
```

### 2. Start Backend

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend starts at **http://localhost:8000**

- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Readiness: http://localhost:8000/ready

### 3. Start Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend starts at **http://localhost:3000**

### 4. Verify

Open http://localhost:3000 — the dashboard should show "Backend: Online" ✅

---

## Connecting Upstox (Required for Live Data)

Without Upstox, the platform shows placeholder data. To get live market data:

### Option A: Analytics Token (Simpler)

1. Get an analytics token from [Upstox Developer Portal](https://developer.upstox.com)
2. Add to your `.env`:
   ```
   UPSTOX_ANALYTICS_TOKEN=your_token_here
   ```
3. Restart the backend

### Option B: Full OAuth (For Portfolio Access)

1. Register an app at [Upstox Developer Portal](https://developer.upstox.com)
2. Add to your `.env`:
   ```
   UPSTOX_CLIENT_ID=your_client_id
   UPSTOX_CLIENT_SECRET=your_client_secret
   UPSTOX_REDIRECT_URI=http://localhost:8000/api/auth/callback
   ```
3. Restart the backend
4. In the UI: Settings → Connect Upstox → Authorize

---

## Project Structure

```
Stock screener/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── api/                # REST API routes
│   │   │   ├── routes/
│   │   │   │   ├── auth.py     # Registration, login, OAuth
│   │   │   │   ├── market.py   # Quotes, candles, fundamentals, predictions
│   │   │   │   ├── portfolio.py # Holdings, positions, P&L
│   │   │   │   ├── signals.py  # Daily stock list, regime, analysis
│   │   │   │   └── websocket.py # Real-time data streaming
│   │   │   └── dependencies.py # JWT auth middleware
│   │   ├── core/
│   │   │   ├── security.py     # JWT, bcrypt, Fernet encryption
│   │   │   └── logging.py      # Structured JSON logging
│   │   ├── models/             # SQLAlchemy database models
│   │   │   ├── compat.py       # Cross-DB type compatibility
│   │   │   ├── user.py         # Users, OAuth, alerts
│   │   │   ├── market.py       # Instruments, candles, features
│   │   │   ├── prediction.py   # Predictions, explanations, audit
│   │   │   └── portfolio.py    # Holdings, positions, P&L
│   │   ├── services/
│   │   │   ├── upstox/         # Upstox API integration
│   │   │   │   ├── client.py   # HTTP client (circuit breaker, rate limit)
│   │   │   │   ├── provider.py # 40+ data provider methods
│   │   │   │   ├── auth.py     # OAuth 2.0 lifecycle
│   │   │   │   └── streamer.py # WebSocket V3 (Protobuf)
│   │   │   ├── analytics/      # Analysis engines
│   │   │   │   ├── features.py # 60+ technical indicators
│   │   │   │   ├── signals.py  # Signal engine (8 discovery buckets)
│   │   │   │   ├── regime.py   # Market regime analyzer
│   │   │   │   └── daily_list.py # Daily stock list orchestrator
│   │   │   └── ml/
│   │   │       └── prediction_engine.py # ML prediction (ensemble)
│   │   ├── tasks/
│   │   │   └── worker.py       # Celery background tasks
│   │   ├── config.py           # Pydantic settings
│   │   ├── database.py         # Async SQLAlchemy
│   │   └── main.py             # FastAPI application
│   ├── tests/                  # Unit tests
│   ├── migrations/             # Alembic DB migrations
│   ├── requirements.txt        # Full dependencies
│   ├── requirements-dev.txt    # Dev dependencies (lightweight)
│   └── Dockerfile
├── frontend/                   # Next.js TypeScript frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css     # Premium dark theme design system
│   │   │   ├── layout.tsx      # Root layout with SEO
│   │   │   ├── page.tsx        # Dashboard (glassmorphism UI)
│   │   │   ├── login/page.tsx  # Auth page
│   │   │   └── stock/[symbol]/ # Stock analysis page
│   │   └── lib/
│   │       ├── api.ts          # Axios API client
│   │       └── store.ts        # Zustand state management
│   └── Dockerfile
├── nginx/
│   └── nginx.conf              # Reverse proxy config
├── docker-compose.yml          # Full stack deployment
├── .env.example                # Environment variables template
└── .gitignore
```

---

## API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login |
| GET | `/api/auth/me` | Current user profile |
| GET | `/api/auth/upstox/connect` | Start Upstox OAuth |
| GET | `/api/auth/callback` | OAuth callback |
| GET | `/api/auth/upstox/status` | Connection status |

### Market Data
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/market/overview` | Market overview (indices, FII/DII) |
| GET | `/api/stocks/{symbol}/quote` | Full market quote |
| GET | `/api/stocks/{symbol}/candles` | Historical OHLCV data |
| GET | `/api/stocks/{symbol}/fundamentals` | Company fundamentals |
| GET | `/api/stocks/{symbol}/news` | Stock news |
| GET | `/api/stocks/{symbol}/prediction` | ML prediction with probabilities |
| GET | `/api/instruments/search` | Instrument search |

### Signals & Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/signals/daily-list` | Daily stock list |
| GET | `/api/signals/regime` | Market regime analysis |
| GET | `/api/signals/analyze/{symbol}` | Complete stock analysis |
| GET | `/api/signals/entry/{symbol}` | Entry/SL/target calculation |

### Portfolio (Requires Upstox OAuth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/portfolio` | Portfolio overview with risk |
| GET | `/api/portfolio/holdings` | Holdings list |
| GET | `/api/portfolio/positions` | Day positions |
| GET | `/api/portfolio/pnl` | Profit & loss report |
| GET | `/api/portfolio/funds` | Fund balances |

### WebSocket
| Endpoint | Description |
|----------|-------------|
| `ws://localhost:8000/ws/market` | Real-time market data stream |

---

## Production Deployment (Docker)

For production with PostgreSQL, Redis, and Celery:

```bash
# Create .env with production values
cp .env.example .env
# Edit .env with your credentials

# Start all services
docker-compose up -d

# Access at http://localhost (nginx proxy)
```

**Production .env requirements:**
```env
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/stockmind
REDIS_URL=redis://redis:6379/0
JWT_SECRET=<random-64-char-string>
ENCRYPTION_KEY=<fernet-key>
UPSTOX_CLIENT_ID=<your-client-id>
UPSTOX_CLIENT_SECRET=<your-secret>
```

Generate a Fernet key:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

### Kubernetes

Same backend/frontend code and Dockerfiles, deployed as a Postgres + backend +
frontend + Ingress stack (Redis/Celery are left out — nothing in the app
actually uses them yet). Full build/push/deploy steps, required secrets, and
a one-time database-init step that production mode needs, are all in
[`k8s/README.md`](k8s/README.md).

```bash
cd k8s
# then follow k8s/README.md — building images, creating secrets,
# and applying the manifests in order
```

---

## Data Integrity Rules

Every data point in the system is classified:

| Label | Meaning |
|-------|---------|
| 🔵 **FACT** | Verified data from Upstox API with timestamp |
| 🟡 **MODEL_PREDICTION** | ML-generated estimate with uncertainty range |
| 🟠 **ANALYST_INTERPRETATION** | Rule-based analysis (entry/exit/classification) |
| 🔴 **DATA_NOT_VERIFIED** | Source unavailable — clearly flagged |

The system **NEVER fabricates** CMP, RSI, MACD, volume, fundamentals, or any market data.

---

## Portfolio Configuration

| Parameter | Value |
|-----------|-------|
| Total Capital | ₹2,00,000 |
| Default Risk/Trade | 0.75% (₹1,500) |
| Max Risk/Trade | 1% (₹2,000) |
| Position Sizing | ATR-based stop-loss driven |
| Max Positions | 6 |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.10+, SQLAlchemy (async) |
| Frontend | Next.js 16, TypeScript, Tailwind CSS |
| Database | SQLite (dev) / PostgreSQL + TimescaleDB (prod) |
| Cache | Redis (prod) |
| Task Queue | Celery + Redis (prod) |
| ML | NumPy, Pandas, scikit-learn, LightGBM, XGBoost |
| Market Data | Upstox V3 API (REST + WebSocket/Protobuf) |
| Auth | JWT + bcrypt + Fernet encryption |
| Reverse Proxy | Nginx |
| Container | Docker + Docker Compose |

---

## License

Private — Not for redistribution.
