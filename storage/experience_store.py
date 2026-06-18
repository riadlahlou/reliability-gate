"""
ReliabilityGate — Experience Store local
=======================================
Remplace wayne.core.experience_store.
Persiste les croyances/beliefs par tenant en JSON.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

_DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


class ExperienceStore:
    """Store de croyances épistémiques par tenant."""

    def __init__(self, tenant_id: str = "default") -> None:
        self.tenant_id = tenant_id
        self._dir = _DATA_ROOT / tenant_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "beliefs.jsonl"
        self._lock = threading.Lock()

    def record_belief(
        self,
        domain: str,
        statement: str,
        confidence_before: float = 0.5,
        trigger: str = "autonomous",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Enregistre une croyance falsifiable."""
        entry = {
            "tenant_id": self.tenant_id,
            "domain": domain,
            "statement": statement,
            "confidence_before": confidence_before,
            "trigger": trigger,
            "status": "open",
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def load_beliefs(self, domain: str | None = None) -> list[dict[str, Any]]:
        """Charge les croyances, optionnellement filtrées par domaine."""
        if not self._path.exists():
            return []
        results = []
        with self._lock:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if domain is None or row.get("domain") == domain:
                        results.append(row)
                except json.JSONDecodeError:
                    pass
        return results


# ── Singleton par tenant ──
_stores: dict[str, ExperienceStore] = {}
_lock = threading.Lock()


def get_experience_store(tenant_id: str = "default") -> ExperienceStore:
    with _lock:
        if tenant_id not in _stores:
            _stores[tenant_id] = ExperienceStore(tenant_id)
        return _stores[tenant_id]


# Compatibilité : instance globale pour imports directs
experience_store = get_experience_store("default")
