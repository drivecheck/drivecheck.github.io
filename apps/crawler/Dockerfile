FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
  && rm -rf /var/lib/apt/lists/*
COPY apps/crawler/pyproject.toml apps/crawler/README.md ./
COPY apps/crawler/src ./src
RUN pip install --no-cache-dir -e .
# Fair loop: omit global --max-pages so per-source budgets apply
# (CZ = MAX_PAGES_PER_RUN, import = MAX_PAGES_IMPORT_PER_RUN).
# CZ sources run first when --source all (see sources.resolve_sources).
CMD ["python", "-m", "drivecheck_crawler", "seed", "--source", "all", "--loop", "--sleep-between-batches", "30"]
