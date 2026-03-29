# Saibyl

**Swarm Intelligence Prediction Platform** by Saido Labs LLC

Saibyl is a multi-agent swarm intelligence SaaS platform. It ingests documents, extracts entities, generates synthetic digital personas, and simulates how those personas behave across social media platforms — producing predictive intelligence reports before real-world events occur.

## Local Development

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Quick Start

```bash
# Clone the repo
git clone https://github.com/saido-labs/saibyl.git
cd saibyl

# Copy environment variables
cp .env.example .env
# Fill in required values (ANTHROPIC_API_KEY, SUPABASE_*, etc.)

# Start all services
make up

# Or run backend/frontend separately:
cd backend && uv sync && uv run uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

### Services

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

## Architecture

See [PRD](../05_PRD/saibyl-prd/README.md) for full architecture documentation.

## License

Apache 2.0 — See [LICENSE](LICENSE)
