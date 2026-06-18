# ══════════════════════════════════════════════════════════════════════════════
# ReliabilityGate — Dockerfile de production
# Multi-stage build pour image minimale.
# ══════════════════════════════════════════════════════════════════════════════

# ── Stage 1 : Builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Copie uniquement les fichiers de dépendances en premier (cache Docker)
COPY pyproject.toml requirements.txt ./

# Installe les dépendances serveur dans un prefix isolé
RUN pip install --no-cache-dir --prefix=/install \
    fastapi>=0.111.0 \
    "uvicorn[standard]>=0.29.0" \
    httpx>=0.27.0 \
    pydantic>=2.0.0 \
    structlog>=24.0.0


# ── Stage 2 : Runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Labels OCI standard
LABEL maintainer="Riad Lahlou"
LABEL org.opencontainers.image.title="ReliabilityGate"
LABEL org.opencontainers.image.description="An anti-gameable permission-to-act layer for autonomous agents. Measure real reliability, abstain when unreliable."
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.vendor="Riad Lahlou"
LABEL org.opencontainers.image.source="https://github.com/riadlahlou/reliability-gate"

# Variables d'environnement pour un runtime Python propre
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Copie les dépendances pré-installées depuis le builder
COPY --from=builder /install /usr/local

# Copie le code applicatif (uniquement ce qui est nécessaire au runtime)
COPY api/         ./api/
COPY sdk/         ./sdk/
COPY core/        ./core/
COPY storage/     ./storage/
COPY adapters/    ./adapters/

# Crée le répertoire data avec les bonnes permissions
RUN mkdir -p /app/data

# Utilisateur non-root pour la sécurité
RUN groupadd --system wayne && \
    useradd --system --gid wayne --home-dir /app --no-create-home wayne && \
    chown -R wayne:wayne /app/data
USER wayne

# Port exposé
EXPOSE 8001

# Healthcheck — vérifie que l'API répond toutes les 30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Démarrage du serveur
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
