#!/bin/bash
# ReliabilityGate — Démarrage rapide
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🧠 ReliabilityGate — Démarrage..."

# Venv
if [ ! -d ".venv" ]; then
  echo "📦 Création de l'environnement virtuel..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Dépendances
pip install -q -r requirements.txt

# Lancement
echo "🚀 API disponible sur http://localhost:8001"
echo "📖 Documentation : http://localhost:8001/docs"
echo ""

PYTHONPATH="$SCRIPT_DIR" uvicorn api.main:app \
  --host 0.0.0.0 \
  --port 8001 \
  --reload \
  --log-level info
