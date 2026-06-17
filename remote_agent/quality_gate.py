"""Проверка 3D/технических файлов перед отправкой в Telegram."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_3D_KEYWORDS = (
    "3d",
    "stl",
    "3mf",
    "модел",
    "козл",
    "козёл",
    "сборк",
    "assembly",
    "render",
    "рендер",
    "mesh",
    "trimesh",
    "bambu",
    "печат",
    "print",
    "детал",
    "фото",
    "png",
    "черт",
    "cad",
)

_3D_EXTS = {".stl", ".3mf", ".obj", ".step", ".stp", ".png", ".jpg", ".jpeg", ".webp", ".zip"}


@dataclass
class QualityReport:
    ok_files: list[str] = field(default_factory=list)
    blocked_files: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    passed: bool = True

    def summary_ru(self) -> str:
        if not self.issues:
            return "✅ QA 3D: все файлы прошли проверку."
        lines = ["⚠️ <b>QA 3D — замечания:</b>"]
        lines.extend(f"• {html_escape(i)}" for i in self.issues[:12])
        if self.blocked_files:
            lines.append(f"Не отправлено: {', '.join(Path(p).name for p in self.blocked_files[:5])}")
        return "\n".join(lines)


def html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def is_3d_task(prompt: str, file_paths: list[str] | None = None) -> bool:
    low = (prompt or "").lower()
    if any(k in low for k in _3D_KEYWORDS):
        return True
    for p in file_paths or []:
        if Path(p).suffix.lower() in _3D_EXTS:
            return True
    return False


def _check_png(path: Path) -> list[str]:
    issues: list[str] = []
    if path.stat().st_size < 800:
        issues.append(f"{path.name}: PNG слишком маленький/пустой")
        return issues
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(path).convert("L")
        w, h = img.size
        if w < 120 or h < 120:
            issues.append(f"{path.name}: разрешение {w}×{h} слишком низкое")
        arr = np.asarray(img, dtype=float)
        if float(arr.std()) < 4.0:
            issues.append(f"{path.name}: почти однотонный (битый/пустой рендер)")
    except ImportError:
        pass
    except Exception as e:
        issues.append(f"{path.name}: не открывается как PNG ({e})")
    return issues


def _check_stl(path: Path) -> list[str]:
    issues: list[str] = []
    if path.stat().st_size < 84:
        issues.append(f"{path.name}: STL слишком маленький")
        return issues
    try:
        import trimesh

        mesh = trimesh.load(str(path), force="mesh")
        if mesh is None or len(getattr(mesh, "vertices", [])) < 8:
            issues.append(f"{path.name}: STL без геометрии")
            return issues
        ext = mesh.extents
        if float(max(ext)) < 0.5:
            issues.append(f"{path.name}: модель слишком мала (<0.5 мм)")
        if not mesh.is_watertight and len(mesh.faces) > 20:
            issues.append(f"{path.name}: меш не watertight (возможны дыры для печати)")
    except ImportError:
        pass
    except Exception as e:
        issues.append(f"{path.name}: STL битый ({e})")
    return issues


def _check_zip(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if not names:
                issues.append(f"{path.name}: ZIP пустой")
            bad = [n for n in names if n.endswith("/")]
            if len(names) - len(bad) < 1:
                issues.append(f"{path.name}: ZIP без файлов")
    except zipfile.BadZipFile:
        issues.append(f"{path.name}: битый ZIP")
    return issues


def _check_kozel_assembly(path: Path) -> list[str]:
    """Доп. проверка рендера козла — scene dump без развала."""
    if "assembly" not in path.name.lower():
        return []
    kozel = Path.home() / "Projects" / "morozov-workspace" / "kozel-kit"
    if not (kozel / "render_views.py").is_file():
        return []
    try:
        import sys

        if str(kozel) not in sys.path:
            sys.path.insert(0, str(kozel))
        from render_views import build_assembly_scene, validate_assembly_geometry

        geom_issues = validate_assembly_geometry()
        if geom_issues:
            return [f"{path.name}: {i}" for i in geom_issues[:4]]
    except Exception as e:
        return [f"QA козла: {e}"]
    return []


def validate_file(path: str | Path) -> list[str]:
    p = Path(path).expanduser()
    if not p.is_file():
        return [f"{p.name}: файл не найден"]
    ext = p.suffix.lower()
    issues: list[str] = []
    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        issues.extend(_check_png(p))
        issues.extend(_check_kozel_assembly(p))
    elif ext == ".stl":
        issues.extend(_check_stl(p))
    elif ext == ".zip":
        issues.extend(_check_zip(p))
    elif ext == ".3mf":
        if p.stat().st_size < 200:
            issues.append(f"{p.name}: 3MF подозрительно маленький")
    return issues


def validate_delivery(
    file_paths: list[str],
    *,
    prompt: str = "",
    strict: bool = True,
) -> QualityReport:
    """Фильтрует битые файлы. strict=True блокирует отправку при ошибках QA на 3D-задачах."""
    report = QualityReport()
    if not file_paths:
        return report

    is_3d = is_3d_task(prompt, file_paths)
    for raw in file_paths:
        p = str(Path(raw).expanduser())
        issues = validate_file(p)
        if issues:
            report.issues.extend(issues)
            report.blocked_files.append(p)
            if is_3d and strict:
                continue
        report.ok_files.append(p)

    if is_3d and strict and report.blocked_files and not report.ok_files:
        report.passed = False
    elif is_3d and strict and report.issues:
        report.passed = len(report.ok_files) > 0
    return report
