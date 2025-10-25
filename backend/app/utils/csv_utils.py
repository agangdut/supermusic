from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Tuple, Iterable, Any


def enrich_csv(
    csv_path: str,
    strategy: str = "youtube+acousticbrainz",
    options: Dict[str, Any] | None = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """
    Minimal CSV "enrichment": reads a CSV (if present) and appends an 'enriched' column.
    If the file isn't found, creates a 1-row demo CSV.
    Returns (csv_bytes, metrics).
    """
    options = options or {}
    rows: list[dict] = []
    input_exists = Path(csv_path).exists()
    if input_exists:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                r = dict(r)
                r["enriched"] = "true"
                rows.append(r)
        fieldnames: Iterable[str] = rows[0].keys() if rows else ["title", "artist", "enriched"]
    else:
        fieldnames = ["title", "artist", "enriched"]
        rows = [{"title": "example", "artist": "artist", "enriched": "true"}]

    out_lines: list[str] = []
    out_lines.append(",".join(fieldnames))
    for r in rows:
        out_lines.append(",".join(str(r.get(k, "")) for k in fieldnames))
    csv_bytes = ("\n".join(out_lines) + "\n").encode("utf-8")

    metrics = {
        "rows_processed": len(rows),
        "strategy": strategy,
        "input_exists": input_exists,
        "options": options,
    }
    return csv_bytes, metrics
