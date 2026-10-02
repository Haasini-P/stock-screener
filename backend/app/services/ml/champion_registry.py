"""
StockMind AI — Champion Model Registry
A tiny on-disk manifest (champion.json) mapping horizon -> trained model
artifact paths. Written by training_pipeline.promote_model, read by
EnsemblePredictionEngine — this indirection means the prediction engine
(constructed fresh per request, per app/api/routes/signals.py) never needs a
DB session just to find out which model is live.
"""

import json
import os
from typing import Any


def manifest_path(model_registry_path: str) -> str:
    return os.path.join(model_registry_path, "champion.json")


def write_manifest(model_registry_path: str, manifest: dict[str, Any]) -> None:
    os.makedirs(model_registry_path, exist_ok=True)
    with open(manifest_path(model_registry_path), "w") as f:
        json.dump(manifest, f, indent=2)


def read_manifest(model_registry_path: str) -> dict[str, Any]:
    path = manifest_path(model_registry_path)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)
