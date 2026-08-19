#!/usr/bin/env python3
"""Deterministic file routing for the spk-github PR review pipeline.

Reads the changed-file list (one "status<TAB>path" line per file, as produced
by the `gh api .../files` step) from stdin or a file argument, applies the
routing map, and prints a JSON manifest assigning every file to specialist
review agents.

This script is the single source of truth for path-based routing. Semantic
routing corrections (substantive UI changes, data-bearing migrations) are made
afterwards by the orchestrator and the spk-reviewer-dispatch agent.

Usage:
    route-files.py [FILE] [--no-checkout]

    --no-checkout   Mode B (PR URL, no local clone): drops
                    spk-reviewer-python-quality, which needs to run local
                    tooling (Ruff, type checker) to be useful.
"""

import argparse
import json
import sys
from fnmatch import fnmatch
from pathlib import PurePosixPath

FRONTEND = "spk-reviewer-frontend"
UI = "spk-reviewer-ui"
BACKEND = "spk-reviewer-backend-python"
PY_QUALITY = "spk-reviewer-python-quality"
TESTS = "spk-reviewer-tests"
DEVOPS = "spk-reviewer-devops"
SECURITY = "spk-reviewer-security"
DATABASE = "spk-reviewer-database"
DOCS = "spk-reviewer-docs"
GENERAL = "spk-reviewer-general-purpose"

# spk-reviewer-security is risk-routed: only patterns with security surface
# include it. The deterministic secrets scan covers every file's diff anyway.
# spk-reviewer-ui/-ux are specialists: UI routes here only for inherently
# visual files (assets, theme); both are otherwise added by the orchestrator
# for substantive UI/interaction changes.
ROUTING = [
    # Frontend — single default pass (includes baseline UI/a11y checks)
    ("*.ts", [FRONTEND, SECURITY]),
    ("*.tsx", [FRONTEND, SECURITY]),
    ("*.css", [FRONTEND]),
    ("vite.config.*", [FRONTEND]),
    ("eslint.*", [FRONTEND]),
    # UI assets and theme files — inherently visual
    ("*.svg", [UI]),
    ("*.png", [UI]),
    ("*.jpg", [UI]),
    ("theme/**", [UI]),
    # Backend
    ("*.py", [BACKEND, PY_QUALITY, SECURITY]),
    ("pyproject.toml", [BACKEND, DEVOPS, SECURITY]),
    ("uv.lock", [BACKEND, SECURITY]),
    # Database (backend-python is added by the orchestrator only for
    # migrations with data operations or deployment coupling)
    ("alembic/**", [DATABASE]),
    ("*.sql", [DATABASE, SECURITY]),
    # Testing
    ("*test*", [TESTS]),
    ("*spec*", [TESTS]),
    ("playwright.*", [TESTS]),
    ("conftest.py", [TESTS, BACKEND]),
    ("vitest.config.*", [TESTS, FRONTEND]),
    # Infrastructure
    ("*.tf", [DEVOPS, SECURITY]),
    ("Dockerfile", [DEVOPS, SECURITY]),
    ("docker-compose.*", [DEVOPS, SECURITY]),
    (".github/workflows/**", [DEVOPS, SECURITY]),
    ("Makefile", [DEVOPS]),
    # Documentation
    ("*.md", [DOCS]),
    ("mkdocs.yml", [DOCS]),
    ("openapi.*", [DOCS, BACKEND]),
    # Configuration (general)
    ("*.json", [FRONTEND]),
    ("*.yaml", [DEVOPS]),
    ("*.yml", [DEVOPS]),
    ("*.toml", [DEVOPS]),
    ("*.sh", [DEVOPS, SECURITY]),
    (".env*", [SECURITY]),
]

AGENT_ORDER = [
    FRONTEND, UI, BACKEND, PY_QUALITY, TESTS,
    DEVOPS, SECURITY, DATABASE, DOCS, GENERAL,
]


def matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        return path == prefix or path.startswith(prefix + "/") or f"/{prefix}/" in path
    # fnmatch's * crosses "/" so bare patterns match anywhere in the path;
    # also try the basename so exact names like conftest.py match in subdirs.
    return fnmatch(path, pattern) or fnmatch(PurePosixPath(path).name, pattern)


def route(path: str) -> list[str]:
    agents: list[str] = []
    for pattern, assigned in ROUTING:
        if matches(path, pattern):
            for agent in assigned:
                if agent not in agents:
                    agents.append(agent)
    # Fallback applies only when nothing matched — nothing goes unreviewed.
    return agents or [GENERAL]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="changed-file list (default: stdin)")
    parser.add_argument("--no-checkout", action="store_true",
                        help="Mode B: drop agents that need a local clone")
    args = parser.parse_args()

    source = open(args.file, encoding="utf-8") if args.file else sys.stdin
    with source:
        lines = [ln.rstrip("\n") for ln in source if ln.strip()]

    files = []
    by_agent: dict[str, list[str]] = {}
    for line in lines:
        status, _, path = line.partition("\t")
        if not path:  # bare path with no status column
            status, path = "", status
        agents = route(path)
        if args.no_checkout and PY_QUALITY in agents:
            agents.remove(PY_QUALITY)
            if not agents:
                agents = [GENERAL]
        files.append({
            "file": path,
            "status": status,
            "agents": agents,
            "fallback": agents == [GENERAL],
        })
        for agent in agents:
            by_agent.setdefault(agent, []).append(path)

    manifest = {
        "files": files,
        "agents": {a: by_agent[a] for a in AGENT_ORDER if a in by_agent},
        "unreviewed_files": [],
    }
    json.dump(manifest, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
