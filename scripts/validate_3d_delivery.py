#!/usr/bin/env python3
"""CLI: проверка 3D-файлов перед отправкой в Telegram."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from remote_agent.quality_gate import validate_delivery


def main() -> None:
    paths = [str(Path(p).expanduser()) for p in sys.argv[1:]]
    if not paths:
        print("Usage: validate_3d_delivery.py file1.png file2.stl ...")
        sys.exit(2)
    report = validate_delivery(paths, prompt="3d", strict=True)
    print(report.summary_ru().replace("<b>", "").replace("</b>", ""))
    for p in report.ok_files:
        print(f"  OK  {p}")
    for p in report.blocked_files:
        print(f"  FAIL {p}")
    for i in report.issues:
        print(f"  ! {i}")
    sys.exit(0 if report.passed and not report.blocked_files else 1)


if __name__ == "__main__":
    main()
