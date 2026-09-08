# Drivecheck crawler

Legality-first Sauto + Bazoš ingest (commercial listing fields only — no phones/emails/names).

```bash
# from repo root, with Docker Postgres/Redis up and .env present
cd apps/crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q

# one batch
python -m drivecheck_crawler seed --source all --max-pages 2

# background seed (continuous)
python -m drivecheck_crawler seed --source all --loop --max-pages 5
```
