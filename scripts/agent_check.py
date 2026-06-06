#!/usr/bin/env python
"""Fast, non-mutating checks for AI coding agents.

This script catches repo consistency issues that slow down agents before heavier
lint/type/test gates run.

Run directly:
    python scripts/agent_check.py        # works without any extra deps where possible
    make agent-check                     # full gate (lint + typecheck + unit tests)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ModuleNotFoundError:
    _yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False


def _failures() -> list[str]:
    failures: list[str] = []
    failures.extend(_check_openapi())
    failures.extend(_check_scaffold_names())
    failures.extend(_check_seeder_test_alignment())
    return failures


def _check_openapi() -> list[str]:
    path = ROOT / "contracts" / "openapi.yaml"
    if not _YAML_AVAILABLE:
        print("warning: pyyaml not installed — skipping OpenAPI check (install with: pip install pyyaml)")
        return []
    try:
        spec = _yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path}: failed to parse OpenAPI YAML: {exc}"]

    if not isinstance(spec, dict):
        return [f"{path}: OpenAPI document must be a mapping"]

    failures: list[str] = []
    if spec.get("openapi") != "3.1.0":
        failures.append(f"{path}: expected openapi: 3.1.0")
    if not spec.get("paths"):
        failures.append(f"{path}: expected at least one path")

    for ref in sorted(_collect_refs(spec)):
        if not ref.startswith("#/"):
            continue
        target: Any = spec
        for part in ref.removeprefix("#/").split("/"):
            if isinstance(target, dict):
                target = target.get(part)
            else:
                target = None
            if target is None:
                failures.append(f"{path}: unresolved local $ref {ref}")
                break

    return failures


def _collect_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            refs.add(ref)
        for child in value.values():
            refs.update(_collect_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_collect_refs(child))
    return refs


def _check_scaffold_names() -> list[str]:
    failures: list[str] = []
    pattern = re.compile(r"^class u[a-z]+(?:Service|Repository)\b", re.MULTILINE)
    for path in (ROOT / "src" / "modules").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            rel = path.relative_to(ROOT)
            failures.append(f"{rel}: invalid scaffold class name `{match.group(0)[6:]}`")
    return failures


def _check_seeder_test_alignment() -> list[str]:
    failures: list[str] = []
    plans_path = ROOT / "src" / "infrastructure" / "database" / "seeders" / "plans.py"
    tests_path = ROOT / "tests" / "integration" / "test_seeders.py"

    if not plans_path.exists():
        return []
    if not tests_path.exists():
        print("warning: tests/integration/test_seeders.py not found — skipping seeder alignment check")
        return []

    plans_text = plans_path.read_text(encoding="utf-8")
    tests_text = tests_path.read_text(encoding="utf-8")

    plan_slugs = set(re.findall(r'slug="([^"]+)"', plans_text))
    if not plan_slugs:
        failures.append(f"{plans_path.relative_to(ROOT)}: no seeded plan slugs found")
        return failures

    expected_match = re.search(r"assert slugs == \{([^}]+)\}", tests_text)
    if expected_match:
        expected = set(re.findall(r'"([^"]+)"', expected_match.group(1)))
        if expected != plan_slugs:
            failures.append(
                "tests/integration/test_seeders.py: expected plan slugs "
                f"{sorted(expected)} do not match seeder slugs {sorted(plan_slugs)}"
            )

    return failures


def main() -> int:
    failures = _failures()
    if failures:
        print("agent-check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("agent-check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
