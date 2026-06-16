#!/usr/bin/env python3
"""Money Hub в облаке: PWA + webhook + Mini App (Render)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONEY_CLOUD", "1")


def main() -> None:
    port = int(os.getenv("PORT", "8765"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Money Hub cloud: http://{host}:{port}/")
    uvicorn.run("business_dashboard.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
