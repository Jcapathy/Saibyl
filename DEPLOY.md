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
| `RESEND_API_KEY` | Bitwarden Secrets Manager |
| `SENTRY_DSN` | Bitwarden Secrets Manager |

> `REDIS_URL` is auto-injected by Render from the `saibyl-redis` service. Do NOT set it manually.

### Taking credit payments (the only Stripe setup there is)

There is **no Stripe product or price to create**. A top-up is any amount from
$10 to $500, so `create_topup_checkout` builds the price inline with
`price_data`; a product id has nowhere to go. `STRIPE_PRICE_ID_STARTER/_PRO/
_ENTERPRISE` were removed on 2026-08-27 — leftovers from the subscription tiers
deleted on 2026-08-25, never read by any Python.

To go from "cannot take money" to "can", in Stripe **live mode**:

1. **Live secret key.** `STRIPE_SECRET_KEY` on `saibyl-backend` must start
   `sk_live_`. A `sk_test_` key produces a working-looking Checkout page that
   only accepts test cards, so no real customer can ever pay.
2. **Register the webhook.** Stripe → Developers → Webhooks → add endpoint
   `https://saibyl-backend.onrender.com/api/billing/webhook`, event
   `checkout.session.completed`. Without it Stripe takes the money and the
   balance never moves — the worst failure mode here, because the customer is
   charged.
3. **Matching webhook secret.** Copy that endpoint's signing secret to
   `STRIPE_WEBHOOK_SECRET`. **It must be from the same mode as the key.** A
   live key with a test signing secret means every real payment is rejected at
   signature verification and silently credited to nobody.

Verify with a real card for $10, then check the org's `credits_balance`
moved and `credit_topups.status` is `paid`. A green Checkout page is not proof:
the money and the credit are two separate events, and only the second one is
the product working.

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
