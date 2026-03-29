# Render Deployment Guide

## Quick Start

1. Push this repo to GitHub (`Jcapathy/Saibyl`)
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click **New** > **Blueprint** > Connect your `Jcapathy/Saibyl` repo
4. Render reads `render.yaml` and creates all 4 services automatically
5. Set the secret env vars (see below)

## Environment Variables to Set Manually

These are marked `sync: false` in render.yaml — you must set them in the Render dashboard for **both** `saibyl-backend` and `saibyl-worker`:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `ZEP_API_KEY` | [cloud.getzep.com](https://cloud.getzep.com) |
| `SUPABASE_URL` | Supabase project Settings > API |
| `SUPABASE_ANON_KEY` | Supabase project Settings > API |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase project Settings > API |
| `DATABASE_URL` | Supabase project Settings > Database > Connection string (use pooler/transaction mode) |
| `SECRET_KEY` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `STRIPE_SECRET_KEY` | [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook endpoint signing secret |
| `STRIPE_PRICE_ID_STARTER` | Stripe product price IDs |
| `STRIPE_PRICE_ID_PRO` | Stripe product price IDs |
| `STRIPE_PRICE_ID_ENTERPRISE` | Stripe product price IDs |
| `RESEND_API_KEY` | [resend.com/api-keys](https://resend.com/api-keys) |
| `SENTRY_DSN` | [sentry.io](https://sentry.io) project settings |

> `REDIS_URL` is auto-injected by Render from the `saibyl-redis` service. Do NOT set it manually.

## Architecture on Render

```
saibyl-frontend (Static)    saibyl-backend (Docker)    saibyl-worker (Docker)
     React SPA        --->    FastAPI + Uvicorn    <-->   Celery Workers
                                     |                        |
                                     v                        v
                              saibyl-redis (Managed)    Supabase (External)
```

## After First Deploy

1. **Run DB migrations**: Execute the SQL files in `backend/scripts/migrations/` against your Supabase project (in order)
2. **Verify health**: Hit `https://saibyl-backend.onrender.com/health` — all checks should return `"ok"`
3. **Set up Stripe webhook**: Point it to `https://saibyl-backend.onrender.com/api/webhooks/stripe`
4. **Custom domain** (optional): Add in Render dashboard for both frontend and backend

## Troubleshooting

- **Health check fails**: Check Render logs. Most common: missing env vars or Supabase not reachable
- **Worker not processing tasks**: Ensure `saibyl-worker` has the same env vars as backend (especially `REDIS_URL`)
- **CORS errors**: Verify `CORS_ORIGINS` matches your frontend URL exactly (no trailing slash)
- **WebSocket not connecting**: Frontend uses `wss://` — Render handles TLS termination automatically
