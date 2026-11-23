"""CLI: print the lead-conversion funnel from the NDJSON lead store.

    python -m sai_agents.analytics.report [LEAD_STORE]

Defaults to the ``SAI_LEAD_STORE`` env var. Also queryable live at the ingest
endpoint's ``GET /analytics``.
"""

from __future__ import annotations

import json
import os
import sys

from sai_agents.analytics.funnel import compute_funnel, load_leads


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SAI_LEAD_STORE")
    funnel = compute_funnel(load_leads(path))
    funnel["lead_store"] = path
    print(json.dumps(funnel, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
