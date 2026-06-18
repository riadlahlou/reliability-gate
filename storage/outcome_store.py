"""
ReliabilityGate — Outcome Store local
===================================
Remplace wayne.strategic.cell_store pour fonctionner de manière autonome.
Persiste les outcomes par tenant_id dans data/{tenant_id}/outcomes.jsonl
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

EVENT_OUTCOME_OBSERVED = "cell.outcome_observed"

_DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


class OutcomeStore:
    """Store d'outcomes multi-tenant, thread-safe, JSONL."""

    def __init__(self, tenant_id: str = "default") -> None:
        self.tenant_id = tenant_id
        self._dir = _DATA_ROOT / tenant_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "outcomes.jsonl"
        self._lock = threading.Lock()

    def persist_outcome(
        self,
        extra: dict[str, Any] | None = None,
        *,
        event: str = EVENT_OUTCOME_OBSERVED,
    ) -> dict[str, Any]:
        """Persiste un outcome réel. Retourne l'entrée créée."""
        entry = {
            "event": event,
            "tenant_id": self.tenant_id,
            "ts": datetime.now(UTC).isoformat(),
            **(extra or {}),
        }
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def load_outcomes(self, last_n: int = 200) -> list[dict[str, Any]]:
        """Charge les N derniers outcomes du tenant."""
        if not self._path.exists():
            return []
        with self._lock:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        rows = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return rows[-last_n:]

    def count(self) -> int:
        """Nombre total d'outcomes persistés."""
        if not self._path.exists():
            return 0
        with self._lock:
            return sum(1 for l in self._path.open(encoding="utf-8") if l.strip())


# ── Registre par tenant ──
_stores: dict[str, OutcomeStore] = {}
_stores_lock = threading.Lock()


def get_outcome_store(tenant_id: str = "default") -> OutcomeStore:
    """Retourne le store du tenant (singleton par tenant_id)."""
    with _stores_lock:
        if tenant_id not in _stores:
            _stores[tenant_id] = OutcomeStore(tenant_id)
        return _stores[tenant_id]
