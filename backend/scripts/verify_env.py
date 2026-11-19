"""Pre-flight check: validates config, keys, paths, and optional deps."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_settings


REQUIRED_PACKAGES = [
    "fastapi", "uvicorn", "pydantic", "pydantic_settings",
    "groq", "tavily", "httpx", "trafilatura",
]

OPTIONAL_PACKAGES = [
    "faster_whisper", "edge_tts", "hybriddb", "pyautogui",
]


def _check(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def main() -> int:
    settings = get_settings()
    ok = True

    print("=== NOT Phase 1 verification ===\n")

    print("[Paths]")
    for label, path in [
        ("data_dir", settings.data_dir),
        ("db_path", settings.db_path),
        ("memory_dir", settings.memory_dir),
        ("whisper_cache", settings.whisper_cache),
    ]:
        status = "OK" if path.parent.exists() or path.exists() else "MISSING"
        print(f"  {label:14s} {status:8s} {path}")
        if status == "MISSING":
            ok = False

    print("\n[AI keys]")
    if settings.groq_api_key:
        print("  groq            SET")
    else:
        print("  groq            MISSING  (Phase 2 will need this)")
        ok = False

    print("\n[Search keys]")
    if settings.tavily_api_key:
        print("  tavily          SET")
    else:
        print("  tavily          MISSING  (Phase 3 will need this)")
        ok = False
    if settings.brave_api_key:
        print("  brave           SET (fallback)")
    else:
        print("  brave           not set (optional fallback)")

    print("\n[Required packages]")
    for pkg in REQUIRED_PACKAGES:
        installed = _check(pkg)
        print(f"  {pkg:20s} {'OK' if installed else 'MISSING'}")
        if not installed:
            ok = False

    print("\n[Optional packages]")
    for pkg in OPTIONAL_PACKAGES:
        print(f"  {pkg:20s} {'OK' if _check(pkg) else 'not installed'}")

    print("\n[Automation safety]")
    roots = settings.allowed_roots_list()
    if roots:
        for root in roots:
            print(f"  allowed root    {root}")
    else:
        print("  allowed root    NONE — file tools will be disabled")
        ok = False
    print(f"  confirmation    {'ON' if settings.require_confirmation else 'OFF'}")
    print(f"  terminal        {'ALLOWED' if settings.allow_terminal else 'BLOCKED'}")

    print("\n" + ("=== PASS ===" if ok else "=== FAIL: fix items above ==="))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())