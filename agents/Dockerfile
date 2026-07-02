# syntax=docker/dockerfile:1
# Production image for the SAI Agents KafCa suite.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY sai_agents ./sai_agents

# Install with the kafka + metrics extras so production has the real transports.
RUN pip install ".[kafka,metrics]"

# Drop privileges.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# Structured JSON logs to stdout by default (12-factor).
ENV SAI_LOG_JSON=true \
    SAI_ENV=production

# Default: run the ServiceTester feedback loop once. Override CMD for the full
# team (python -m sai_agents.run_team) or a long-running scheduler.
CMD ["python", "-m", "sai_agents.service_testers.service_tester_agent"]
