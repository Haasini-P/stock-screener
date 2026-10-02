# StockMind AI — Kubernetes Deployment

Deploys the same backend/frontend code as `docker-compose.yml` at the repo
root, using the same two Dockerfiles. **Scope note**: this does not include
Redis or a Celery worker — `docker-compose.yml` has them, but every task in
`backend/app/tasks/worker.py` is an empty stub (`logger.info(...)` then
`return {"status": "completed"}`) and nothing else in the app calls Redis for
anything (caching, pub/sub, sessions). Deploying them here would mean running
real infrastructure for code that does nothing. Add them back the same way
`postgres.yaml`/`backend.yaml` are structured if real background jobs get
built later.

## What's here

| File | What it is |
|---|---|
| `namespace.yaml` | The `stockmind` namespace everything else lives in |
| `configmap.yaml` | Non-secret app config |
| `secret.example.yaml` | **Template only** — shows the required keys; create the real one with `kubectl create secret` (command inside the file) |
| `postgres.yaml` | Postgres (TimescaleDB image, same as compose) — StatefulSet + PVC + headless Service |
| `db-init-job.yaml` | One-time schema creation — see "Why the init Job" below, this isn't optional |
| `backend.yaml` | FastAPI backend — Deployment + Service + a PVC for `model_registry` (trained ML models) |
| `frontend.yaml` | Next.js frontend — Deployment + Service |
| `ingress.yaml` | Routes one public hostname to both (same split as `nginx/nginx.conf`) |

## Before you apply anything

Three things that only work with real values, not what's checked in:

1. **Your domain.** Replace `stockmind.example.com` in `configmap.yaml` and
   `ingress.yaml` with your real domain. No domain yet? Point an ingress-nginx
   LoadBalancer's IP at `<ip>.nip.io` for a quick working hostname with no DNS
   setup.
2. **Secrets.** `JWT_SECRET` and `ENCRYPTION_KEY` both have hardcoded,
   publicly-known fallback values in `app/config.py` if left unset — anyone
   who knows those defaults could forge login tokens and decrypt stored
   broker/API credentials. Generate real ones (command in
   `secret.example.yaml`). This matters even more than usual here: an earlier
   audit this session found the project's own `.env` was still running on
   that default, so double check this isn't being carried over by habit.
3. **Upstox/Kite redirect URIs.** Whatever you set `UPSTOX_REDIRECT_URI`
   to in `configmap.yaml` must be registered byte-for-byte in the Upstox
   developer console, and the same for Kite.

## Why the init Job (don't skip it)

`app/main.py`'s startup only calls `init_db()` when `APP_ENV=development` —
deliberately, so it's not silently re-run against a live database on every
pod restart. This deployment sets `APP_ENV=production` (correctly), which
means nothing creates the schema. There's also no real Alembic migration
wired up — `backend/migrations/` in the repo is unused scaffolding. Without
`db-init-job.yaml`, a fresh Postgres has zero tables and every single API
call fails. It's safe to re-run (SQLAlchemy's `create_all()` only creates
tables that don't already exist), but it only needs to run once per database.

## Build and push the images

Images aren't pulled from a public registry — build them from this repo and
push to whatever registry your cluster can pull from (replace `your-registry`
below; for a local cluster like kind/minikube, load them directly instead of
pushing — see the note after).

```bash
# From the repo root:
docker build -t your-registry/stockmind-backend:latest -f backend/Dockerfile backend
docker push your-registry/stockmind-backend:latest

# NEXT_PUBLIC_API_URL is baked into the browser bundle at BUILD time, not read
# from the running container (see frontend/Dockerfile's comment) — it must be
# your real public hostname from the step above, reachable from users' browsers.
docker build \
  --build-arg NEXT_PUBLIC_API_URL=https://stockmind.example.com \
  -t your-registry/stockmind-frontend:latest \
  -f frontend/Dockerfile frontend
docker push your-registry/stockmind-frontend:latest
```

Then update the `image:` line in `backend.yaml`, `frontend.yaml`, and
`db-init-job.yaml` (it reuses the backend image) to `your-registry/...`
instead of the local `stockmind-backend:latest` placeholder.

**Local cluster (kind/minikube), no registry needed:**
```bash
kind load docker-image stockmind-backend:latest stockmind-frontend:latest
# or: minikube image load stockmind-backend:latest && minikube image load stockmind-frontend:latest
```
and leave the `image:` fields as-is.

## Deploy

```bash
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl create secret generic stockmind-secrets -n stockmind \
  --from-literal=POSTGRES_USER=stockmind \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -base64 32)" \
  --from-literal=POSTGRES_DB=stockmind \
  --from-literal=JWT_SECRET="$(openssl rand -base64 48)" \
  --from-literal=ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  --from-literal=DATABASE_URL="postgresql+asyncpg://stockmind:PASTE_SAME_PASSWORD@postgres:5432/stockmind" \
  --from-literal=DATABASE_URL_SYNC="postgresql://stockmind:PASTE_SAME_PASSWORD@postgres:5432/stockmind" \
  --from-literal=UPSTOX_CLIENT_ID=... \
  --from-literal=UPSTOX_CLIENT_SECRET=... \
  --from-literal=UPSTOX_ANALYTICS_TOKEN=... \
  --from-literal=KITE_API_KEY=... \
  --from-literal=KITE_API_SECRET=...

kubectl apply -f postgres.yaml
kubectl wait --for=condition=ready pod -l app=postgres -n stockmind --timeout=120s

kubectl apply -f db-init-job.yaml
kubectl wait --for=condition=complete job/stockmind-db-init -n stockmind --timeout=120s

kubectl apply -f backend.yaml
kubectl apply -f frontend.yaml
kubectl apply -f ingress.yaml
```

## Verify

```bash
kubectl get pods -n stockmind
kubectl logs -n stockmind job/stockmind-db-init        # should show no errors
kubectl port-forward -n stockmind svc/backend 8000:8000 &
curl localhost:8000/health
curl localhost:8000/ready   # "database": "connected" confirms the init Job worked
```

Then open your domain in a browser once the Ingress has an external IP
(`kubectl get ingress -n stockmind`) and DNS/`.nip.io` points at it.

## Known limits of this setup (by design, not oversights)

- **Backend runs as a single replica.** The market-scanner cache and the
  trailing-stop-loss monitor (`app/services/trading/trailing_monitor.py`) are
  in-process state, and `model_registry` is a `ReadWriteOnce` volume — neither
  survives being spread across multiple pods without further changes. Scale
  the frontend freely; scaling the backend needs that state moved out first.
- **No TLS by default.** `ingress.yaml` has a commented-out `tls:` block for
  cert-manager; wire that up (or your own TLS termination) before handling
  real credentials over the public internet.
- **No automated backups for the Postgres PVC.** Set up volume snapshots or
  `pg_dump` on a schedule appropriate to your cluster before trusting this
  with real portfolio data.
