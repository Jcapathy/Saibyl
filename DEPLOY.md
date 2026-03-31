# Render Deployment Guide

## Quick Start

1. Push this repo to GitHub (`Jcapathy/Saibyl`)
2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click **New** > **Blueprint** > Connect your `Jcapathy/Saibyl` repo
4. Render reads `render.yaml` and creates all 3 services automatically
5. Set the secret env vars (see below)

## Environment Variables to Set Manually

These are marked `sync: false` in render.yaml — you must set them in the Render dashboard for `saibyl-backend`:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | Bitwarden Secrets Manager |
| `SUPABASE_URL` | Bitwarden Secrets Manager |
| `SUPABASE_ANON_KEY` | Bitwarden Secrets Manager |
| `SUPABASE_SERVICE_ROLE_KEY` | Bitwarden Secrets Manager |
| `DATABASE_URL` | Bitwarden Secrets Manager |
| `SECRET_KEY` | Bitwarden Secrets Manager (min 32 chars, required in production) |
| `STRIPE_SECRET_KEY` | Bitwarden Secrets Manager |
| `STRIPE_WEBHOOK_SECRET` | Bitwarden Secrets Manager |
| `STRIPE_PRICE_ID_STARTER` | Bitwarden Secrets Manager |
| `STRIPE_PRICE_ID_PRO` | Bitwarden Secrets Manager |
| `STRIPE_PRICE_ID_ENTERPRISE` | Bitwarden Secrets Manager |
| `RESEND_API_KEY` | Bitwarden Secrets Manager |
| `SENTRY_DSN` | Bitwarden Secrets Manager |

> `REDIS_URL` is auto-injected by Render from the `saibyl-redis` service. Do NOT set it manually.

## Architecture on Render

```
saibyl-frontend (Static)    saibyl-backend (Docker)
     React SPA        --->    FastAPI + Uvicorn
                                     |
                                     v
                              saibyl-redis (Managed)    Supabase (External)
```

Background tasks run as `asyncio.create_task()` within the FastAPI process — no separate worker needed.

## After First Deploy

1. **Run DB migrations**: Execute the SQL files in `backend/scripts/migrations/` against your Supabase project (in order)
2. **Verify health**: Hit `https://saibyl-backend.onrender.com/health` — all checks should return `"ok"`
3. **Set up Stripe webhook**: Point it to `https://saibyl-backend.onrender.com/api/webhooks/stripe`
4. **Custom domain** (optional): Add in Render dashboard for both frontend and backend

## Troubleshooting

- **Health check fails**: Check Render logs. Most common: missing env vars or Supabase not reachable
- **CORS errors**: Verify `CORS_ORIGINS` matches your frontend URL exactly (no trailing slash)
- **WebSocket not connecting**: Frontend uses `wss://` — Render handles TLS termination automatically
