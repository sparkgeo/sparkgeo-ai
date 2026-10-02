#!/usr/bin/env python3
"""Deterministic steps for the spk-github pull request review pipeline.

The model does the review. This tool does everything that should not depend
on a model: collecting PR data, pinning a snapshot, routing files, validating
agent output, computing counts, applying the publication budget, rendering the
GitHub review, and posting it.

Standard library only. Run with: python3 spk_review.py <command> ...

Commands
  collect      Fetch PR metadata, files, diff, and review threads into a run dir.
  snapshot     Check out the PR head SHA into an isolated directory.
  fetch-file   Fetch one file at the PR head SHA through the GitHub API.
  route        Build the review plan: manifest, exclusions, agent assignments.
  ingest       Validate specialist output, dedupe by key, number candidates.
  verify-plan  List the candidates that need independent verification.
  finalize     Apply verification, compute counts and blocking, select findings.
  render       Build the review body and the GitHub payload.
  post         Recheck the head SHA, post the review, supersede the old one.
  cleanup      Remove the snapshot.
  usage        Sum token usage and elapsed time for the run from the session transcripts.
  validate     Validate one JSON file against the specialist or aggregate contract.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION = "2.0"
REVIEW_MARKER = "<!-- ai-review-team -->"
FINDING_MARKER_RE = re.compile(r"<!-- spk-finding: ([^>]+?) -->")
RUN_MARKER_RE = re.compile(r"<!-- spk-review run=(\S+) head=([0-9a-f]+) -->")
CR_ID_RE = re.compile(r"\bCR-\d{3,}\b")
LEGACY_LEVEL_RE = re.compile(r"\*\*(severe|warning|question)\*\*\s*·", re.I)
SUB_LEVEL_RE = re.compile(r"<sub>(severe|warning|question)\b", re.I)

LEVELS = ("severe", "warning", "question")
LEVEL_RANK = {"severe": 0, "warning": 1, "question": 2}
CONFIDENCES = ("high", "medium", "low")
CONF_RANK = {"high": 0, "medium": 1, "low": 2}
CATEGORIES = (
    "correctness", "security", "performance", "maintainability", "readability",
    "style", "test_gap", "docs", "dependency", "api_contract", "concurrency",
    "error_handling",
)
TOOL_DETECTABLE = ("style",)
AGENT_ROLES = {
    "spk-reviewer-primary": "primary",
    "spk-reviewer-security": "security",
    "spk-reviewer-frontend": "frontend",
    "spk-reviewer-ui": "ui_design",
    "spk-reviewer-ux": "ux_accessibility",
    "spk-reviewer-backend-python": "backend",
    "spk-reviewer-python-quality": "code_quality",
    "spk-reviewer-tests": "testing",
    "spk-reviewer-devops": "infrastructure",
    "spk-reviewer-database": "database",
    "spk-reviewer-docs": "documentation",
    "spk-reviewer-aggregator": "aggregator",
    "spk-reviewer-verifier": "verifier",
}
PRIMARY = "spk-reviewer-primary"
SECURITY = "spk-reviewer-security"

FINDING_FIELDS = {
    "id", "type", "level", "category", "confidence", "title", "problem",
    "consequence", "fix", "fix_caveat", "evidence", "introduced_by_pr",
    "cross_cutting", "references", "related_ids", "dedupe_key", "location",
    "applies_to",
}
AGGREGATE_EXTRA_FIELDS = {
    "found_by", "prior_thread_id", "verification", "publication", "prior_state",
    "fingerprint",
}
LOCATION_FIELDS = {"file_path", "side", "start_line", "end_line", "symbol", "hunk_header"}
WORD_TARGET_MAX = 70
WORD_HARD_MAX = 110
TITLE_MAX = 80
BODY_LIMIT = 65000
DEFAULT_CONFIG = {
    "request_changes": False,
    "max_published": 5,
    "max_inline": 20,
    "exclude": [],
    "optional_reviewers": [],
    "conventions": [],
    "allow_style_findings": False,
}
CONVENTION_FILES = (
    "CLAUDE.md", "AGENTS.md", "REVIEW.md", "CONTRIBUTING.md",
    ".github/copilot-instructions.md", ".github/spk-review.json",
)

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


class ToolError(Exception):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def run(cmd: list[str], *, cwd: str | None = None, input_text: str | None = None,
        check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, input=input_text, text=True,
                          capture_output=True)
    if check and proc.returncode != 0:
        raise ToolError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc


def gh_json(args: list[str], *, input_text: str | None = None):
    proc = run(["gh", *args], input_text=input_text)
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def word_count(*parts: str | None) -> int:
    return sum(len(re.findall(r"\S+", p or "")) for p in parts)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def fingerprint_for(finding: dict) -> str:
    """Stable identity for a finding: category|slug|primary_file. No line numbers."""
    key = (finding.get("dedupe_key") or "").strip().lower()
    segments = [s.strip() for s in key.split("|") if s.strip()]
    primary_file = primary_path(finding) or ""
    if len(segments) >= 2:
        slug = slugify(segments[1])
        category = segments[0]
    else:
        slug = slugify(finding.get("title", ""))
        category = finding.get("category", "")
    return f"{category}|{slug}|{primary_file}"


def primary_path(finding: dict) -> str | None:
    loc = finding.get("location") or {}
    if loc.get("file_path"):
        return loc["file_path"]
    paths = (finding.get("applies_to") or {}).get("file_paths") or []
    return paths[0] if paths else None


def all_paths(finding: dict) -> list[str]:
    paths = []
    loc = finding.get("location") or {}
    if loc.get("file_path"):
        paths.append(loc["file_path"])
    for p in (finding.get("applies_to") or {}).get("file_paths") or []:
        if p not in paths:
            paths.append(p)
    return paths


def short_sha(sha: str | None) -> str:
    return (sha or "")[:7]


# ---------------------------------------------------------------------------
# Unified diff parsing
# ---------------------------------------------------------------------------

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(text: str) -> dict[str, dict]:
    """Return per-path anchors: which old/new lines appear in hunks.

    Each entry: {old_path, new_path, binary, new_lines: set, old_lines: set,
    added_text: [str], removed_text: [str]}
    Keyed by the new path (or old path for deletions).
    """
    files: dict[str, dict] = {}
    current: dict | None = None
    old_line = new_line = 0
    pending_old: str | None = None
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            current = {"old_path": None, "new_path": None, "binary": False,
                       "new_lines": set(), "old_lines": set(),
                       "added_text": [], "removed_text": []}
            pending_old = None
            continue
        if current is None:
            continue
        if raw.startswith("--- "):
            p = raw[4:].strip()
            pending_old = None if p == "/dev/null" else _strip_prefix(p, "a/")
            current["old_path"] = pending_old
            continue
        if raw.startswith("+++ "):
            p = raw[4:].strip()
            new_path = None if p == "/dev/null" else _strip_prefix(p, "b/")
            current["new_path"] = new_path
            key = new_path or current["old_path"]
            if key:
                files[key] = current
            continue
        if raw.startswith("Binary files") or raw.startswith("GIT binary patch"):
            current["binary"] = True
            # binary files have no ---/+++ lines; register by the diff header
            if current["new_path"] is None and current["old_path"] is None:
                m = re.search(r"Binary files (?:a/)?(.+?) and (?:b/)?(.+?) differ", raw)
                if m:
                    key = m.group(2) if m.group(2) != "/dev/null" else m.group(1)
                    current["new_path"] = key
                    files[key] = current
            continue
        if raw.startswith("rename to "):
            # mode-only or rename-only diffs may have no ---/+++ lines
            key = raw[len("rename to "):].strip()
            current["new_path"] = key
            files.setdefault(key, current)
            continue
        if raw.startswith("rename from "):
            current["old_path"] = raw[len("rename from "):].strip()
            continue
        m = HUNK_RE.match(raw)
        if m:
            old_line = int(m.group(1))
            new_line = int(m.group(3))
            continue
        if not raw:
            continue
        tag = raw[0]
        if tag == "+":
            current["new_lines"].add(new_line)
            current["added_text"].append(raw[1:])
            new_line += 1
        elif tag == "-":
            current["old_lines"].add(old_line)
            current["removed_text"].append(raw[1:])
            old_line += 1
        elif tag == " ":
            current["new_lines"].add(new_line)
            current["old_lines"].add(old_line)
            new_line += 1
            old_line += 1
        elif tag == "\\":
            continue
    return files


def _strip_prefix(path: str, prefix: str) -> str:
    return path[len(prefix):] if path.startswith(prefix) else path


def build_diff_from_patches(files: list[dict]) -> str:
    """Rebuild a unified diff from the files API `patch` fields (fallback)."""
    chunks = []
    for f in files:
        old = f.get("previous_filename") or f["filename"]
        new = f["filename"]
        status = f.get("status")
        chunks.append(f"diff --git a/{old} b/{new}")
        if status == "renamed":
            chunks.append(f"rename from {old}")
            chunks.append(f"rename to {new}")
        patch = f.get("patch")
        if patch is None:
            chunks.append(f"Binary files a/{old} and b/{new} differ")
            continue
        chunks.append(f"--- {'/dev/null' if status == 'added' else 'a/' + old}")
        chunks.append(f"+++ {'/dev/null' if status == 'removed' else 'b/' + new}")
        chunks.append(patch)
    return "\n".join(chunks) + "\n"


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------

STATUS_MAP = {"added": "A", "modified": "M", "removed": "D", "renamed": "R",
              "copied": "C", "changed": "M", "unchanged": "M"}

THREADS_QUERY = """
query($owner: String!, $repo: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line startLine diffSide
          comments(first: 100) {
            pageInfo { hasNextPage }
            nodes { databaseId body createdAt author { login } }
          }
        }
      }
    }
  }
}
"""


def fetch_pr(owner: str, repo: str, number: int) -> dict:
    return gh_json(["api", f"repos/{owner}/{repo}/pulls/{number}"])


def fetch_files(owner: str, repo: str, number: int) -> tuple[list[dict], list[str]]:
    files: list[dict] = []
    warnings: list[str] = []
    page = 1
    while True:
        batch = gh_json(["api", f"repos/{owner}/{repo}/pulls/{number}/files?per_page=100&page={page}"])
        if not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        if page > 30:
            warnings.append("files API stopped at 3000 files, the endpoint maximum")
            break
    return files, warnings


def fetch_threads(owner: str, repo: str, number: int) -> tuple[list[dict], list[str]]:
    nodes: list[dict] = []
    warnings: list[str] = []
    after = None
    while True:
        args = ["api", "graphql", "-f", f"query={THREADS_QUERY}", "-F", f"owner={owner}",
                "-F", f"repo={repo}", "-F", f"number={number}"]
        if after:
            args += ["-F", f"after={after}"]
        data = gh_json(args)
        conn = data["data"]["repository"]["pullRequest"]["reviewThreads"]
        nodes.extend(conn["nodes"])
        if not conn["pageInfo"]["hasNextPage"]:
            break
        after = conn["pageInfo"]["endCursor"]
    for n in nodes:
        if n["comments"]["pageInfo"]["hasNextPage"]:
            warnings.append(f"thread on {n.get('path')} has more than 100 comments; only the first 100 were read")
    return nodes, warnings


def normalize_thread(node: dict, pr_author: str | None, pr_url: str) -> dict:
    comments = node.get("comments", {}).get("nodes", [])
    first = comments[0] if comments else {}
    body = first.get("body") or ""
    fp = FINDING_MARKER_RE.search(body)
    legacy = bool(LEGACY_LEVEL_RE.search(body) or "Found by:" in body)
    is_ai = bool(fp) or legacy
    cr = CR_ID_RE.search(body)
    level_match = SUB_LEVEL_RE.search(body) or LEGACY_LEVEL_RE.search(body)
    replies = []
    for c in comments[1:]:
        login = (c.get("author") or {}).get("login")
        replies.append({"author": login, "body": c.get("body") or "",
                        "created_at": c.get("createdAt"),
                        "by_pr_author": bool(pr_author) and login == pr_author})
    author_replied = any(r["by_pr_author"] for r in replies)
    if node.get("isResolved"):
        status = "resolved"
    elif author_replied:
        status = "discussed"
    else:
        status = "open"
    database_id = first.get("databaseId")
    return {
        "id": node.get("id"),
        "path": node.get("path"),
        "line": node.get("line"),
        "start_line": node.get("startLine"),
        "side": node.get("diffSide"),
        "is_resolved": bool(node.get("isResolved")),
        "is_outdated": bool(node.get("isOutdated")),
        "is_ai_review": is_ai,
        "fingerprint": fp.group(1).strip() if fp else None,
        "cr_id": cr.group(0) if cr else None,
        "level": level_match.group(1).lower() if level_match else None,
        "first_comment": {"author": (first.get("author") or {}).get("login"),
                          "body": body, "created_at": first.get("createdAt"),
                          "database_id": database_id},
        "replies": replies,
        "author_replied": author_replied,
        "status": status,
        "url": f"{pr_url}#discussion_r{database_id}" if database_id else None,
    }


def find_prior_review(owner: str, repo: str, number: int) -> dict | None:
    reviews = gh_json(["api", "--paginate", f"repos/{owner}/{repo}/pulls/{number}/reviews?per_page=100"])
    if isinstance(reviews, dict):
        reviews = [reviews]
    prior = None
    for r in reviews or []:
        body = r.get("body") or ""
        if REVIEW_MARKER in body:
            prior = r
    if not prior:
        return None
    m = RUN_MARKER_RE.search(prior.get("body") or "")
    return {
        "id": prior["id"],
        "state": prior.get("state"),
        "commit_id": prior.get("commit_id"),
        "submitted_at": prior.get("submitted_at"),
        "run_id": m.group(1) if m else None,
        "head_sha": m.group(2) if m else None,
        "body": prior.get("body") or "",
    }


def cmd_collect(a: argparse.Namespace) -> int:
    owner, repo = a.repo.split("/", 1)
    number = int(a.pr)
    warnings: list[str] = []
    raw = fetch_pr(owner, repo, number)
    head_sha = raw["head"]["sha"]
    pr = {
        "number": number, "owner": owner, "repo": repo, "url": raw["html_url"],
        "title": raw.get("title") or "", "body": raw.get("body") or "",
        "author": (raw.get("user") or {}).get("login"),
        "base_ref": raw["base"]["ref"], "base_sha": raw["base"]["sha"],
        "head_ref": raw["head"]["ref"], "head_sha": head_sha,
        "head_repo": ((raw.get("head") or {}).get("repo") or {}).get("full_name"),
        "changed_files_count": raw.get("changed_files"),
        "is_draft": bool(raw.get("draft")), "state": raw.get("state"),
        "labels": [l["name"] for l in raw.get("labels") or []],
        "collected_at": now_iso(),
    }
    files_raw, w = fetch_files(owner, repo, number)
    warnings += w
    files = []
    for f in files_raw:
        files.append({
            "path": f["filename"],
            "previous_path": f.get("previous_filename"),
            "status": STATUS_MAP.get(f.get("status"), "M"),
            "additions": f.get("additions", 0), "deletions": f.get("deletions", 0),
            "patch_available": f.get("patch") is not None,
        })
    diff_source = "gh pr diff"
    proc = run(["gh", "pr", "diff", str(number), "--repo", a.repo], check=False)
    if proc.returncode == 0 and proc.stdout.strip():
        diff_text = proc.stdout
    else:
        diff_text = build_diff_from_patches(files_raw)
        diff_source = "files API patches"
        warnings.append("gh pr diff failed; the diff was rebuilt from the files API patches")
    after = fetch_pr(owner, repo, number)
    head_consistent = after["head"]["sha"] == head_sha
    if not head_consistent:
        warnings.append(f"head moved during collection: {short_sha(head_sha)} -> {short_sha(after['head']['sha'])}. Rerun collect.")
    thread_nodes, w = fetch_threads(owner, repo, number)
    warnings += w
    threads = [normalize_thread(n, pr["author"], pr["url"]) for n in thread_nodes]
    prior = find_prior_review(owner, repo, number)

    parsed = parse_unified_diff(diff_text)
    manifest_paths = {f["path"] for f in files}
    diff_only = sorted(set(parsed) - manifest_paths)
    manifest_only = sorted(manifest_paths - set(parsed))
    count_match = pr["changed_files_count"] is None or pr["changed_files_count"] == len(files)
    if not count_match:
        warnings.append(f"files API returned {len(files)} files but the PR reports {pr['changed_files_count']}")
    if diff_only:
        warnings.append(f"{len(diff_only)} path(s) in the diff are missing from the files list: {', '.join(diff_only[:5])}")
    if manifest_only:
        warnings.append(f"{len(manifest_only)} path(s) in the files list have no diff hunks (binary, mode change, or too large): {', '.join(manifest_only[:5])}")

    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + short_sha(head_sha)
    run_dir = Path(a.out) / f"pr{number}" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "pr.json", pr)
    write_json(run_dir / "files.json", files)
    write_text(run_dir / "diff.patch", diff_text)
    write_json(run_dir / "threads.json", threads)
    write_json(run_dir / "prior_review.json", prior)
    collect = {
        "run_id": run_id, "collected_at": pr["collected_at"], "head_sha": head_sha,
        "diff_source": diff_source, "head_consistent": head_consistent,
        "files_count_match": count_match, "files_total": len(files),
        "threads_total": len(threads),
        "ai_threads": sum(1 for t in threads if t["is_ai_review"]),
        "prior_review_id": prior["id"] if prior else None,
        "warnings": warnings,
    }
    write_json(run_dir / "collect.json", collect)
    print(json.dumps({"run_dir": str(run_dir), **collect}, indent=2))
    return 0 if head_consistent else 4


# ---------------------------------------------------------------------------
# snapshot / fetch-file
# ---------------------------------------------------------------------------


def snapshot_root(pr: dict) -> Path:
    return Path(tempfile.gettempdir()) / "spk-review" / f"{pr['owner']}__{pr['repo']}__{short_sha(pr['head_sha'])}"


def local_repo_matches(pr: dict) -> str | None:
    """Return the local repo root if the cwd is a clone of owner/repo."""
    proc = run(["git", "rev-parse", "--show-toplevel"], check=False)
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    remotes = run(["git", "remote", "-v"], check=False, cwd=root).stdout.lower()
    needle = f"{pr['owner']}/{pr['repo']}".lower()
    return root if needle in remotes else None


def cmd_snapshot(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    pr = read_json(run_dir / "pr.json")
    target = snapshot_root(pr)
    result = {"path": str(target), "method": "none", "head_sha": pr["head_sha"],
              "verified": False, "note": ""}
    if target.exists() and (target / ".git").exists():
        actual = run(["git", "rev-parse", "HEAD"], cwd=str(target), check=False).stdout.strip()
        if actual == pr["head_sha"]:
            result.update(method="existing", verified=True, note="reused existing snapshot")
            write_json(run_dir / "snapshot.json", result)
            print(json.dumps(result, indent=2))
            return 0
        shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    local_root = local_repo_matches(pr)
    try:
        if local_root:
            fetch = run(["git", "fetch", "--quiet", "origin", pr["head_sha"]], cwd=local_root, check=False)
            if fetch.returncode != 0:
                run(["git", "fetch", "--quiet", "origin", f"pull/{pr['number']}/head"], cwd=local_root)
            run(["git", "worktree", "add", "--detach", "--quiet", str(target), pr["head_sha"]], cwd=local_root)
            result.update(method="worktree", local_root=local_root)
        else:
            run(["gh", "repo", "clone", f"{pr['owner']}/{pr['repo']}", str(target), "--", "--depth", "1", "--no-checkout", "--quiet"])
            fetch = run(["git", "fetch", "--quiet", "--depth", "1", "origin", pr["head_sha"]], cwd=str(target), check=False)
            if fetch.returncode != 0:
                run(["git", "fetch", "--quiet", "--depth", "1", "origin", f"pull/{pr['number']}/head"], cwd=str(target))
            run(["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], cwd=str(target))
            result.update(method="shallow_clone")
        actual = run(["git", "rev-parse", "HEAD"], cwd=str(target)).stdout.strip()
        result["verified"] = actual == pr["head_sha"]
        if not result["verified"]:
            result["note"] = f"snapshot is at {short_sha(actual)}, not the recorded head {short_sha(pr['head_sha'])}. The PR may have moved."
            result["actual_sha"] = actual
    except ToolError as exc:
        result.update(method="none", path=None, note=f"snapshot unavailable: {exc}. Use fetch-file for pinned reads.")
    write_json(run_dir / "snapshot.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["verified"] else 5


def cmd_fetch_file(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    pr = read_json(run_dir / "pr.json")
    data = gh_json(["api", f"repos/{pr['owner']}/{pr['repo']}/contents/{a.path}?ref={pr['head_sha']}"])
    if not data or data.get("encoding") != "base64":
        raise ToolError(f"could not fetch {a.path} at {short_sha(pr['head_sha'])}")
    out = run_dir / "files" / a.path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(data["content"]))
    print(str(out))
    return 0


def cmd_cleanup(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    snap_path = run_dir / "snapshot.json"
    if not snap_path.exists():
        print("no snapshot recorded")
        return 0
    snap = read_json(snap_path)
    path = snap.get("path")
    if not path or not Path(path).exists():
        print("snapshot already removed")
        return 0
    if snap.get("method") in ("worktree", "existing") and snap.get("local_root"):
        run(["git", "worktree", "remove", "--force", path], cwd=snap["local_root"], check=False)
    shutil.rmtree(path, ignore_errors=True)
    print(f"removed {path}")
    return 0


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------

LOCKFILES = ("uv.lock", "poetry.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
             "Cargo.lock", "Pipfile.lock", "composer.lock", "Gemfile.lock", "*.lock")
GENERATED = ("*.min.js", "*.min.css", "*.map", "**/__snapshots__/**", "**/snapshots/**",
             "*.snap", "**/dist/**", "**/build/**", "**/node_modules/**", "**/vendor/**",
             "*.generated.*", "*_pb2.py", "*_pb2_grpc.py", "*.pb.go")
BINARY_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
              ".tar", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".mp3", ".bin",
              ".so", ".dylib", ".dll", ".pyc", ".whl", ".jar", ".parquet", ".gpkg", ".shp")
TEST_PATTERNS = ("test_*.py", "*_test.py", "tests/**", "test/**", "**/tests/**", "**/test/**",
                 "**/__tests__/**", "*.test.*", "*.spec.*", "conftest.py", "playwright.*",
                 "vitest.config.*", "locustfile*", "e2e/**", "**/e2e/**")
FRONTEND_PATTERNS = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs", "*.css", "*.scss",
                     "vite.config.*", "eslint.*", "tsconfig*.json", "package.json", "index.html")
UI_PATTERNS = ("*.css", "*.scss", "*.svg", "theme/**", "**/theme/**", "**/theme.*", "**/tokens.*",
               "**/*.theme.*")
BACKEND_PATTERNS = ("*.py", "pyproject.toml", "setup.cfg", "setup.py")
DATABASE_PATTERNS = ("alembic/**", "**/alembic/**", "**/migrations/**", "*.sql", "**/models/**", "**/models.py")
DEVOPS_PATTERNS = ("*.tf", "*.tfvars", "Dockerfile*", "**/Dockerfile*", "docker-compose*", "compose.y*ml",
                   ".github/workflows/**", ".github/actions/**", "Makefile", "*.mk", "*.sh", ".dockerignore",
                   "**/helm/**", "**/k8s/**", "**/deploy/**", "**/infra/**", "**/terraform/**",
                   ".pre-commit-config.yaml", "Procfile", "serverless.y*ml")
DOCS_PATTERNS = ("*.md", "*.mdx", "*.rst", "mkdocs.yml", "openapi.*", "docs/**", "**/docs/**", "*.txt")

INTERACTIVE_RE = re.compile(r"onClick|onSubmit|onChange|onKey|<form|<input|<button|<select|<textarea|Modal|Drawer|Menu|Dialog|aria-|role=|tabIndex|useNavigate|<Link|<NavLink|<a |href=")
STYLE_RE = re.compile(r"style=\{\{|#[0-9a-fA-F]{3,8}\b|theme\.|createTheme|MantineProvider|className=")
MODEL_RE = re.compile(r"Column\(|mapped_column\(|__tablename__|relationship\(|declarative_base|DeclarativeBase|class .*\(Base\)|ForeignKey\(")
ROUTE_RE = re.compile(r"@(router|app|api)\.(get|post|put|patch|delete|websocket)\(|APIRouter\(|include_router\(|export (async )?function|export const .*=.*=>")
SOURCE_EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".cs", ".sql")


def glob_match(pattern: str, path: str) -> bool:
    if "/" not in pattern:
        return fnmatch.fnmatchcase(Path(path).name, pattern)
    regex = _glob_to_regex(pattern)
    return re.match(regex, path) is not None


def _glob_to_regex(pattern: str) -> str:
    out = "^"
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return out + "$"


def matches_any(path: str, patterns) -> bool:
    return any(glob_match(p, path) for p in patterns)


def load_config(snapshot_path: str | None) -> tuple[dict, str]:
    config = dict(DEFAULT_CONFIG)
    source = "defaults"
    candidates = []
    if snapshot_path:
        candidates.append(Path(snapshot_path) / ".github" / "spk-review.json")
    for cand in candidates:
        if cand.exists():
            try:
                config.update(read_json(cand))
                source = str(cand)
            except json.JSONDecodeError as exc:
                source = f"{cand} (invalid JSON, defaults used: {exc})"
            break
    return config, source


def classify_file(entry: dict, diff_info: dict | None, config: dict) -> tuple[str, str | None]:
    """Return (kind, exclude_reason). kind in source|test|docs|lockfile|generated|binary|config."""
    path = entry["path"]
    for pat in config.get("exclude") or []:
        if glob_match(pat, path):
            return "excluded", f"repository policy: matches `{pat}` in .github/spk-review.json"
    if matches_any(path, LOCKFILES):
        return "lockfile", "lockfile: dependency check only, no line review"
    if path.lower().endswith(BINARY_EXT) or (diff_info and diff_info.get("binary")):
        return "binary", "binary: not readable as text, security check only"
    if matches_any(path, GENERATED):
        return "generated", "generated or vendored: security check only"
    if matches_any(path, TEST_PATTERNS):
        return "test", None
    if matches_any(path, DOCS_PATTERNS):
        return "docs", None
    return "source", None


def route_files(files: list[dict], parsed_diff: dict[str, dict], config: dict) -> dict:
    manifest = []
    agents: dict[str, dict] = {}
    triggers: list[dict] = []

    def assign(agent: str, path: str, reason: str) -> None:
        a = agents.setdefault(agent, {"name": agent, "files": [], "reasons": {}})
        if path not in a["files"]:
            a["files"].append(path)
        a["reasons"].setdefault(reason, 0)
        a["reasons"][reason] += 1

    test_files, source_files, model_files, migration_files, docs_files, api_files = [], [], [], [], [], []
    for entry in files:
        path = entry["path"]
        info = parsed_diff.get(path)
        kind, reason = classify_file(entry, info, config)
        added = "\n".join(info["added_text"]) if info else ""
        removed = "\n".join(info["removed_text"]) if info else ""
        changed_text = added + "\n" + removed
        reviewers: list[str] = []
        item = {"path": path, "status": entry["status"], "kind": kind,
                "review": reason is None, "exclude_reason": reason, "reviewers": reviewers}
        if kind == "excluded":
            manifest.append(item)
            continue
        if kind in ("lockfile", "binary", "generated"):
            assign(SECURITY, path, kind)
            reviewers.append(SECURITY)
            manifest.append(item)
            continue
        assign(PRIMARY, path, "primary reviewer covers every reviewable file")
        assign(SECURITY, path, "security runs on every reviewable file")
        reviewers += [PRIMARY, SECURITY]
        if kind == "test":
            test_files.append(path)
            assign("spk-reviewer-tests", path, "test file")
            reviewers.append("spk-reviewer-tests")
        if kind == "docs":
            docs_files.append(path)
            assign("spk-reviewer-docs", path, "documentation file")
            reviewers.append("spk-reviewer-docs")
        if kind in ("source", "test"):
            if path.endswith(SOURCE_EXT) and kind == "source":
                source_files.append(path)
            if matches_any(path, FRONTEND_PATTERNS):
                assign("spk-reviewer-frontend", path, "frontend file")
                reviewers.append("spk-reviewer-frontend")
                if path.endswith((".tsx", ".jsx")) and INTERACTIVE_RE.search(added):
                    assign("spk-reviewer-ux", path, "interactive UI change")
                    reviewers.append("spk-reviewer-ux")
                if matches_any(path, UI_PATTERNS) or (path.endswith((".tsx", ".jsx")) and STYLE_RE.search(added)):
                    assign("spk-reviewer-ui", path, "styling or theme change")
                    reviewers.append("spk-reviewer-ui")
            elif matches_any(path, UI_PATTERNS):
                assign("spk-reviewer-ui", path, "theme or asset file")
                reviewers.append("spk-reviewer-ui")
            if matches_any(path, BACKEND_PATTERNS) and kind == "source":
                assign("spk-reviewer-backend-python", path, "backend Python file")
                reviewers.append("spk-reviewer-backend-python")
                if "spk-reviewer-python-quality" in (config.get("optional_reviewers") or []) and path.endswith(".py"):
                    assign("spk-reviewer-python-quality", path, "opt-in style review")
                    reviewers.append("spk-reviewer-python-quality")
                if ROUTE_RE.search(changed_text):
                    api_files.append(path)
            if path.endswith((".ts", ".tsx", ".js", ".jsx")) and ROUTE_RE.search(changed_text):
                api_files.append(path)
            if matches_any(path, DATABASE_PATTERNS):
                assign("spk-reviewer-database", path, "database file")
                reviewers.append("spk-reviewer-database")
                if "alembic" in path or "migrations" in path:
                    migration_files.append(path)
            elif path.endswith(".py") and MODEL_RE.search(changed_text):
                model_files.append(path)
                assign("spk-reviewer-database", path, "ORM model change")
                reviewers.append("spk-reviewer-database")
            if matches_any(path, DEVOPS_PATTERNS) or (
                    path.endswith((".yml", ".yaml")) and (path.startswith(".github/") or "/infra/" in path or "/deploy/" in path)):
                assign("spk-reviewer-devops", path, "infrastructure or CI file")
                reviewers.append("spk-reviewer-devops")
        manifest.append(item)

    # Behaviour triggers: absences cannot be found by watching one file type.
    if model_files and not migration_files:
        triggers.append({"agent": "spk-reviewer-database", "trigger": "model_change_without_migration",
                         "files": model_files,
                         "instruction": "ORM models changed but no migration file changed. Confirm whether a migration is required and missing."})
        for p in model_files:
            assign("spk-reviewer-database", p, "model change without migration")
    added_source_lines = sum(len(parsed_diff.get(p, {}).get("added_text", [])) for p in source_files)
    if source_files and not test_files and added_source_lines >= 20:
        triggers.append({"agent": "spk-reviewer-tests", "trigger": "behaviour_change_without_tests",
                         "files": source_files,
                         "instruction": "Source behaviour changed but no test file changed. Inspect existing tests at the snapshot. Raise one finding only if a specific changed behaviour has a material risk and no test guards it."})
        for p in source_files:
            assign("spk-reviewer-tests", p, "behaviour change without tests")
    if api_files and not docs_files:
        triggers.append({"agent": "spk-reviewer-docs", "trigger": "api_change_without_docs",
                         "files": api_files,
                         "instruction": "Public API surface changed but no documentation changed. Check whether existing docs now give wrong instructions or make the changed API unusable. Do not ask for docs merely because none changed."})
        for p in api_files:
            assign("spk-reviewer-docs", p, "API change without docs")

    # Reflect trigger-based assignments in the per-file reviewer lists.
    by_path = {m["path"]: m for m in manifest}
    for t in triggers:
        for p in t["files"]:
            item = by_path.get(p)
            if item and t["agent"] not in item["reviewers"]:
                item["reviewers"].append(t["agent"])

    order = [PRIMARY, SECURITY, "spk-reviewer-backend-python", "spk-reviewer-database", "spk-reviewer-frontend",
             "spk-reviewer-ux", "spk-reviewer-ui", "spk-reviewer-tests", "spk-reviewer-devops", "spk-reviewer-docs",
             "spk-reviewer-python-quality"]
    agent_list = []
    for name in order:
        if name in agents:
            a = agents[name]
            a["triggers"] = [t for t in triggers if t["agent"] == name]
            agent_list.append(a)
    return {"manifest": manifest, "agents": agent_list, "triggers": triggers}


def cmd_route(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    files = read_json(run_dir / "files.json")
    pr = read_json(run_dir / "pr.json")
    diff_text = (run_dir / "diff.patch").read_text(encoding="utf-8")
    parsed = parse_unified_diff(diff_text)
    snap = read_json(run_dir / "snapshot.json") if (run_dir / "snapshot.json").exists() else {}
    snapshot_path = snap.get("path") if snap.get("verified") or snap.get("method") in ("worktree", "shallow_clone", "existing") else None
    config, config_source = load_config(snapshot_path)
    plan = route_files(files, parsed, config)
    context_files = []
    for rel in list(CONVENTION_FILES) + list(config.get("conventions") or []):
        exists = bool(snapshot_path) and (Path(snapshot_path) / rel).exists()
        context_files.append({"path": rel, "available": exists})
    plan.update({
        "run_id": run_dir.name, "head_sha": pr["head_sha"], "base_sha": pr["base_sha"],
        "pr_intent": {"title": pr["title"], "body": pr["body"], "labels": pr["labels"], "author": pr["author"]},
        "snapshot": {"path": snapshot_path, "method": snap.get("method", "none"), "verified": bool(snap.get("verified"))},
        "config": config, "config_source": config_source,
        "context_files": context_files,
        "excluded": [{"path": m["path"], "reason": m["exclude_reason"]} for m in plan["manifest"] if not m["review"]],
        "files_total": len(files),
        "files_reviewable": sum(1 for m in plan["manifest"] if m["review"]),
    })
    write_json(run_dir / "plan.json", plan)
    lines = [f"plan: {plan['files_reviewable']} of {plan['files_total']} files reviewable, {len(plan['excluded'])} excluded ({config_source})"]
    for ag in plan["agents"]:
        trig = f" triggers={[t['trigger'] for t in ag['triggers']]}" if ag["triggers"] else ""
        lines.append(f"  {ag['name']}: {len(ag['files'])} files{trig}")
    for ex in plan["excluded"]:
        lines.append(f"  excluded {ex['path']}: {ex['reason']}")
    unavailable = [c["path"] for c in context_files if not c["available"]]
    if snapshot_path is None:
        lines.append("  snapshot: none. Agents must use fetch-file for pinned reads; record unavailable context.")
    print("\n".join(lines))
    return 0


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def validate_finding(f: dict, idx: int, *, aggregate: bool, config: dict | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    label = f.get("id") or f"#{idx}"
    allowed = FINDING_FIELDS | (AGGREGATE_EXTRA_FIELDS if aggregate else set())
    unknown = set(f) - allowed
    if unknown:
        errors.append(f"{label}: unknown fields {sorted(unknown)}")
    if not re.match(r"^CR-\d{3,}$", str(f.get("id", ""))):
        errors.append(f"{label}: id must match CR-NNN")
    if f.get("type") not in ("inline_comment", "diff_comment"):
        errors.append(f"{label}: type must be inline_comment or diff_comment")
    if f.get("level") not in LEVELS:
        errors.append(f"{label}: level must be one of {LEVELS}")
    if f.get("category") not in CATEGORIES:
        errors.append(f"{label}: category `{f.get('category')}` is not in the shared list")
    if f.get("confidence") not in CONFIDENCES:
        errors.append(f"{label}: confidence must be one of {CONFIDENCES}")
    title = f.get("title") or ""
    if not title.strip():
        errors.append(f"{label}: title is required")
    elif len(title) > TITLE_MAX:
        errors.append(f"{label}: title is {len(title)} chars, max {TITLE_MAX}")
    for field in ("problem", "consequence"):
        if not (f.get(field) or "").strip():
            errors.append(f"{label}: {field} is required")
    if f.get("level") in ("warning", "severe"):
        if not (f.get("fix") or "").strip():
            errors.append(f"{label}: fix is required for {f.get('level')} findings")
        if not f.get("evidence"):
            errors.append(f"{label}: evidence is required for {f.get('level')} findings")
    if "introduced_by_pr" not in f or not isinstance(f.get("introduced_by_pr"), bool):
        errors.append(f"{label}: introduced_by_pr (boolean) is required")
    if not isinstance(f.get("dedupe_key"), str) or f["dedupe_key"].count("|") < 2:
        errors.append(f"{label}: dedupe_key must be `category|issue_slug|file_path[|symbol|lines]`")
    words = word_count(f.get("problem"), f.get("consequence"), f.get("fix"))
    if words > WORD_HARD_MAX:
        errors.append(f"{label}: problem+consequence+fix is {words} words, hard max {WORD_HARD_MAX}")
    elif words > WORD_TARGET_MAX:
        warns.append(f"{label}: {words} words, target is 40 to {WORD_TARGET_MAX}")
    if f.get("type") == "inline_comment":
        loc = f.get("location")
        if not isinstance(loc, dict):
            errors.append(f"{label}: inline_comment requires location")
        else:
            unknown_loc = set(loc) - LOCATION_FIELDS
            if unknown_loc:
                errors.append(f"{label}: unknown location fields {sorted(unknown_loc)}")
            if not loc.get("file_path"):
                errors.append(f"{label}: location.file_path is required")
            if loc.get("side") not in ("old", "new"):
                errors.append(f"{label}: location.side must be `old` or `new`")
            s, e = loc.get("start_line"), loc.get("end_line")
            if not (isinstance(s, int) and isinstance(e, int) and 1 <= s <= e):
                errors.append(f"{label}: location lines must be integers with 1 <= start_line <= end_line")
    else:
        paths = (f.get("applies_to") or {}).get("file_paths")
        if not paths:
            errors.append(f"{label}: diff_comment requires applies_to.file_paths")
    if aggregate:
        if not isinstance(f.get("found_by"), list) or not f["found_by"]:
            errors.append(f"{label}: found_by must list at least one agent")
    return errors, warns


def validate_specialist(doc: dict, agent_name: str | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    if not isinstance(doc, dict):
        return ["output is not a JSON object"], []
    unknown = set(doc) - {"version", "agent", "files", "findings", "context_unavailable", "notes"}
    if unknown:
        errors.append(f"unknown top-level fields {sorted(unknown)}")
    if doc.get("version") != VERSION:
        errors.append(f"version must be \"{VERSION}\"")
    agent = doc.get("agent") or {}
    name = agent.get("name")
    if name not in AGENT_ROLES:
        errors.append(f"agent.name `{name}` is unknown")
    elif agent.get("role") != AGENT_ROLES[name]:
        errors.append(f"agent.role must be `{AGENT_ROLES[name]}` for {name}")
    if agent_name and name != agent_name:
        errors.append(f"agent.name is `{name}` but the file is for `{agent_name}`")
    files = doc.get("files")
    if not isinstance(files, list):
        errors.append("files must be a list of {path, status}")
    else:
        for i, fs in enumerate(files):
            if not isinstance(fs, dict) or not fs.get("path") or fs.get("status") not in ("reviewed", "partial", "skipped"):
                errors.append(f"files[{i}] needs path and status in reviewed|partial|skipped")
    findings = doc.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
    else:
        for i, f in enumerate(findings):
            e, w = validate_finding(f, i, aggregate=False)
            errors += e
            warns += w
    return errors, warns


def validate_aggregate(doc: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    if not isinstance(doc, dict):
        return ["output is not a JSON object"], []
    if doc.get("version") != VERSION:
        errors.append(f"version must be \"{VERSION}\"")
    findings = doc.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
    else:
        ids = [f.get("id") for f in findings]
        if len(ids) != len(set(ids)):
            errors.append("finding ids are not unique")
        for i, f in enumerate(findings):
            e, w = validate_finding(f, i, aggregate=True)
            errors += e
            warns += w
    return errors, warns


def cmd_validate(a: argparse.Namespace) -> int:
    doc = read_json(Path(a.file))
    if a.schema == "specialist":
        errors, warns = validate_specialist(doc)
    else:
        errors, warns = validate_aggregate(doc)
    for w in warns:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print("valid" if not errors else f"{len(errors)} error(s)")
    return 0 if not errors else 2


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


def merge_candidates(findings: list[dict]) -> list[dict]:
    """Exact-key dedupe. Later semantic dedupe is the aggregator's job."""
    groups: dict[str, dict] = {}
    order: list[str] = []
    for f in findings:
        key = "|".join(s.strip().lower() for s in f["dedupe_key"].split("|")[:3])
        if key not in groups:
            merged = {k: v for k, v in f.items() if k not in ("id",)}
            merged["found_by"] = [f["_agent"]]
            merged["source_ids"] = [f"{f['_agent']}:{f['id']}"]
            merged.pop("_agent", None)
            groups[key] = merged
            order.append(key)
            continue
        g = groups[key]
        if f["_agent"] not in g["found_by"]:
            g["found_by"].append(f["_agent"])
        g["source_ids"].append(f"{f['_agent']}:{f['id']}")
        if LEVEL_RANK[f["level"]] < LEVEL_RANK[g["level"]]:
            g["level"] = f["level"]
            g["fix"] = f.get("fix") or g.get("fix")
        if CONF_RANK[f["confidence"]] < CONF_RANK[g["confidence"]]:
            g["confidence"] = f["confidence"]
        for ev in f.get("evidence") or []:
            g.setdefault("evidence", [])
            if ev not in g["evidence"]:
                g["evidence"].append(ev)
        for ref in f.get("references") or []:
            g.setdefault("references", [])
            if ref not in g["references"]:
                g["references"].append(ref)
        g["introduced_by_pr"] = bool(g.get("introduced_by_pr")) or bool(f.get("introduced_by_pr"))
        g["cross_cutting"] = bool(g.get("cross_cutting")) or bool(f.get("cross_cutting"))
    out = [groups[k] for k in order]
    out.sort(key=lambda f: (LEVEL_RANK[f["level"]], CONF_RANK[f["confidence"]], -len(all_paths(f))))
    for i, f in enumerate(out, 1):
        f["id"] = f"CR-{i:03d}"
        f["fingerprint"] = fingerprint_for(f)
    return out


def cmd_ingest(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    plan = read_json(run_dir / "plan.json")
    agents_dir = run_dir / "agents"
    pool: list[dict] = []
    agent_status: dict[str, dict] = {}
    report: list[str] = []
    for ag in plan["agents"]:
        name = ag["name"]
        assigned = set(ag["files"])
        status = {"status": "missing", "assigned": sorted(assigned), "reviewed": [], "partial": [],
                  "skipped": [], "not_reported": [], "findings": 0, "errors": [], "warnings": [],
                  "context_unavailable": []}
        path = agents_dir / f"{name}.json"
        if path.exists():
            try:
                doc = read_json(path)
            except json.JSONDecodeError as exc:
                status["status"] = "failed"
                status["errors"].append(f"invalid JSON: {exc}")
                agent_status[name] = status
                continue
            errors, warns = validate_specialist(doc, name)
            status["warnings"] = warns
            if errors:
                status["status"] = "failed"
                status["errors"] = errors
                agent_status[name] = status
                continue
            reported = {}
            for fs in doc["files"]:
                reported[fs["path"]] = fs["status"]
            for p in sorted(assigned):
                st = reported.get(p)
                if st == "reviewed":
                    status["reviewed"].append(p)
                elif st == "partial":
                    status["partial"].append(p)
                elif st == "skipped":
                    status["skipped"].append(p)
                else:
                    status["not_reported"].append(p)
            status["context_unavailable"] = doc.get("context_unavailable") or []
            status["findings"] = len(doc["findings"])
            status["status"] = "ok" if not (status["not_reported"] or status["partial"] or status["skipped"]) else "partial"
            for f in doc["findings"]:
                f = dict(f)
                f["_agent"] = name
                pool.append(f)
        agent_status[name] = status
    candidates = merge_candidates(pool)
    merged = {"version": VERSION, "run_id": plan["run_id"], "head_sha": plan["head_sha"],
              "candidates": candidates, "agents": agent_status,
              "raw_findings": len(pool), "merged_findings": len(candidates)}
    write_json(run_dir / "merged.json", merged)
    for name, st in agent_status.items():
        extra = ""
        if st["errors"]:
            extra = " errors: " + "; ".join(st["errors"][:3])
        elif st["not_reported"] or st["skipped"] or st["partial"]:
            extra = f" not_reported={len(st['not_reported'])} partial={len(st['partial'])} skipped={len(st['skipped'])}"
        report.append(f"  {name}: {st['status']} findings={st['findings']}{extra}")
    failed = [n for n, s in agent_status.items() if s["status"] in ("failed", "missing")]
    print(f"ingest: {len(pool)} raw findings -> {len(candidates)} candidates; failed/missing agents: {failed or 'none'}")
    print("\n".join(report))
    return 0 if not failed else 6


# ---------------------------------------------------------------------------
# verify-plan
# ---------------------------------------------------------------------------


def needs_verification(f: dict, thread_by_fp: dict[str, dict]) -> str | None:
    if f["level"] == "severe":
        return "severe findings are always verified"
    if f["level"] == "warning":
        if f.get("confidence") != "high":
            return "warning with confidence below high"
        if f.get("cross_cutting"):
            return "cross-cutting warning"
        thread = thread_by_fp.get(f.get("fingerprint") or "")
        if thread and thread["status"] in ("resolved", "discussed"):
            return "warning previously discussed or resolved; current code must be checked"
    return None


def cmd_verify_plan(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    agg = read_json(run_dir / "aggregated.json")
    threads = read_json(run_dir / "threads.json")
    thread_by_fp = {t["fingerprint"]: t for t in threads if t.get("fingerprint")}
    errors, warns = validate_aggregate(agg)
    if errors:
        for e in errors:
            print(f"error: {e}")
        return 2
    batches: list[dict] = []
    waiting: dict[str, list[dict]] = {}
    for f in agg["findings"]:
        f.setdefault("fingerprint", fingerprint_for(f))
        reason = needs_verification(f, thread_by_fp)
        if not reason:
            continue
        item = {"id": f["id"], "level": f["level"], "reason": reason, "title": f["title"],
                "paths": all_paths(f), "found_by": f["found_by"]}
        if f["level"] == "severe":
            batches.append({"batch": f"verify-{f['id']}", "findings": [item]})
        else:
            key = primary_path(f) or "general"
            waiting.setdefault(key, []).append(item)
    for key, items in waiting.items():
        for i in range(0, len(items), 4):
            chunk = items[i:i + 4]
            batches.append({"batch": f"verify-{slugify(key)}-{i // 4 + 1}", "findings": chunk})
    plan = {"run_id": agg.get("run_id") or run_dir.name, "batches": batches,
            "total": sum(len(b["findings"]) for b in batches)}
    write_json(run_dir / "verify" / "plan.json", plan)
    print(f"verify-plan: {plan['total']} finding(s) in {len(batches)} batch(es)")
    for b in batches:
        ids = ", ".join(f"{i['id']} ({i['level']})" for i in b["findings"])
        print(f"  {b['batch']}: {ids}")
    return 0


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------


def load_verifications(run_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    vdir = run_dir / "verify"
    if not vdir.exists():
        return out
    for p in sorted(vdir.glob("*.json")):
        if p.name == "plan.json":
            continue
        try:
            doc = read_json(p)
        except json.JSONDecodeError:
            continue
        results = doc.get("results") if isinstance(doc, dict) else None
        if results is None and isinstance(doc, dict) and doc.get("id"):
            results = [doc]
        for r in results or []:
            if r.get("id") and r.get("status") in ("verified", "rejected", "unverified"):
                out[r["id"]] = r
    return out


def match_prior_thread(f: dict, threads: list[dict]) -> dict | None:
    fp = f.get("fingerprint")
    for t in threads:
        if t.get("is_ai_review") and fp and t.get("fingerprint") == fp:
            return t
    if f.get("prior_thread_id"):
        for t in threads:
            if t.get("id") == f["prior_thread_id"] or (t.get("first_comment") or {}).get("database_id") == f["prior_thread_id"]:
                return t
    return None


def finalize(agg: dict, verifications: dict[str, dict], threads: list[dict], plan: dict,
             merged: dict | None, collect: dict | None, pr: dict, snapshot: dict | None) -> dict:
    config = plan.get("config") or DEFAULT_CONFIG
    findings = [dict(f) for f in agg["findings"]]
    for f in findings:
        f.setdefault("fingerprint", fingerprint_for(f))
        v = verifications.get(f["id"])
        f["verification"] = {"status": v["status"], "method": v.get("method", ""), "note": v.get("note", ""),
                             "by": v.get("by", "spk-reviewer-verifier")} if v else \
            {"status": "not_required" if f["level"] != "severe" and f.get("confidence") == "high" else "unverified",
             "method": "", "note": "", "by": ""}
        if v and v.get("level") in LEVELS and v["level"] != f["level"]:
            f["verification"]["level_before"] = f["level"]
            f["level"] = v["level"]
        if v and v.get("evidence_added"):
            f.setdefault("evidence", [])
            for ev in v["evidence_added"]:
                if ev not in f["evidence"]:
                    f["evidence"].append(ev)
        pub = {"status": "candidate", "reason": ""}
        if f["verification"]["status"] == "rejected":
            pub = {"status": "rejected", "reason": f["verification"].get("note") or "rejected by verifier"}
        elif not f.get("introduced_by_pr"):
            pub = {"status": "rejected", "reason": "pre-existing issue, not introduced by this PR"}
        elif f["category"] in TOOL_DETECTABLE and not config.get("allow_style_findings"):
            pub = {"status": "rejected", "reason": "tool-detectable style feedback is not published by default"}
        elif f["level"] in ("warning", "severe") and not f.get("evidence"):
            pub = {"status": "rejected", "reason": "no evidence at the reviewed revision"}
        f["publication"] = pub
        thread = match_prior_thread(f, threads)
        if thread:
            f["prior_thread_id"] = thread["id"]
            still_present = f["verification"]["status"] in ("verified", "not_required")
            if pub["status"] == "rejected":
                f["prior_state"] = {"state": "unknown", "thread_url": thread["url"], "thread_status": thread["status"]}
            elif thread["status"] in ("open", "discussed"):
                level_up = thread.get("level") in LEVELS and LEVEL_RANK[f["level"]] < LEVEL_RANK[thread["level"]]
                f["prior_state"] = {"state": "still_present" if still_present else "unknown",
                                    "thread_url": thread["url"], "thread_status": thread["status"],
                                    "severity_increased": bool(level_up)}
                if not level_up:
                    f["publication"] = {"status": "still_open",
                                        "reason": "already raised in an open thread; no new inline thread"}
            else:
                state = "accepted_risk" if thread["author_replied"] else "reopened"
                if not still_present:
                    state = "unknown"
                f["prior_state"] = {"state": state, "thread_url": thread["url"], "thread_status": "resolved"}
                if state == "accepted_risk" and f["level"] != "severe":
                    f["publication"] = {"status": "accepted_risk", "reason": "resolved by the author after discussion"}
                elif state == "unknown":
                    f["publication"] = {"status": "withheld", "reason": "thread was resolved and the finding was not re-verified"}
    # Budget selection
    candidates = [f for f in findings if f["publication"]["status"] == "candidate"]
    candidates.sort(key=lambda f: (LEVEL_RANK[f["level"]], -len(all_paths(f)), CONF_RANK[f["confidence"]], f["id"]))
    max_published = int(config.get("max_published") or 5)
    published = 0
    for f in candidates:
        verified_severe = f["level"] == "severe" and f["verification"]["status"] == "verified"
        if verified_severe or published < max_published:
            f["publication"] = {"status": "published", "reason": "within budget" if not verified_severe else "verified severe"}
            published += 1
        else:
            f["publication"] = {"status": "withheld", "reason": "over the publication budget"}
    reopened = [f for f in findings if (f.get("prior_state") or {}).get("state") == "reopened" and f["publication"]["status"] == "published"]
    for f in reopened:
        f["publication"]["reason"] += "; resolved earlier but still present"
    pub_findings = [f for f in findings if f["publication"]["status"] == "published"]
    blocking = any(f["level"] == "severe" and f["verification"]["status"] == "verified" for f in pub_findings)
    event = "REQUEST_CHANGES" if blocking and config.get("request_changes") else "COMMENT"
    counts = {lvl: sum(1 for f in pub_findings if f["level"] == lvl) for lvl in LEVELS}
    # Prior threads not re-detected
    current_fps = {f["fingerprint"] for f in findings if f["publication"]["status"] != "rejected"}
    prior_findings = []
    for t in threads:
        if not t.get("is_ai_review"):
            continue
        matched = t.get("fingerprint") in current_fps if t.get("fingerprint") else any(
            f.get("prior_thread_id") == t["id"] for f in findings)
        if matched:
            f = next((f for f in findings if f.get("prior_thread_id") == t["id"]), None)
            state = (f or {}).get("prior_state", {}).get("state", "still_present")
        else:
            state = "not_found"
        prior_findings.append({"thread_id": t["id"], "fingerprint": t.get("fingerprint"), "cr_id": t.get("cr_id"),
                               "path": t.get("path"), "line": t.get("line"), "thread_status": t["status"],
                               "state": state, "url": t["url"]})
    # Coverage
    agents_status = (merged or {}).get("agents") or {}
    coverage = []
    files_reviewed_by_primary = set()
    failed_agents = []
    for ag in plan["agents"]:
        st = agents_status.get(ag["name"]) or {"status": "missing", "reviewed": [], "partial": [], "skipped": [],
                                                "not_reported": ag["files"], "findings": 0}
        if st["status"] in ("failed", "missing"):
            failed_agents.append(ag["name"])
        if ag["name"] == PRIMARY:
            files_reviewed_by_primary = set(st.get("reviewed", []))
        coverage.append({"agent": ag["name"], "role": AGENT_ROLES.get(ag["name"], ""),
                         "files_assigned": len(ag["files"]), "files_reviewed": len(st.get("reviewed", [])),
                         "files_partial": len(st.get("partial", [])), "files_skipped": len(st.get("skipped", [])),
                         "files_not_reported": len(st.get("not_reported", [])),
                         "findings": st.get("findings", 0), "status": st["status"]})
    reviewable = [m["path"] for m in plan["manifest"] if m["review"]]
    not_reviewed = sorted(set(reviewable) - files_reviewed_by_primary)
    notes = list((collect or {}).get("warnings") or [])
    if failed_agents:
        notes.append(f"agent(s) failed or returned no usable output: {', '.join(failed_agents)}")
    if not_reviewed:
        notes.append(f"{len(not_reviewed)} reviewable file(s) were not confirmed reviewed by the primary reviewer: {', '.join(not_reviewed[:5])}")
    if snapshot and not snapshot.get("verified"):
        notes.append("no verified snapshot at the head SHA; reads may not reflect the reviewed revision")
    for name, st in agents_status.items():
        for cu in st.get("context_unavailable") or []:
            notes.append(f"{name}: context unavailable: {cu}")
    coverage_complete = (not failed_agents and not not_reviewed and (collect or {}).get("files_count_match", True)
                         and (collect or {}).get("head_consistent", True))
    withheld = [f for f in findings if f["publication"]["status"] == "withheld"]
    headline = headline_for(counts, pub_findings)
    final = {
        "version": VERSION,
        "pr": {"title": pr["title"], "number": pr["number"], "url": pr["url"], "author": pr["author"],
               "base_ref": pr["base_ref"], "head_ref": pr["head_ref"], "base_sha": pr["base_sha"],
               "head_sha": pr["head_sha"]},
        "run": {"id": plan["run_id"], "finalized_at": now_iso(),
                "snapshot_method": (snapshot or {}).get("method", "none"),
                "snapshot_verified": bool((snapshot or {}).get("verified")),
                "agents_invoked": [a["name"] for a in plan["agents"]], "agents_failed": failed_agents,
                "config_source": plan.get("config_source", "defaults")},
        "summary": {"headline": headline, "blocking": blocking, "event": event, "counts": counts,
                    "published": len(pub_findings), "withheld": len(withheld),
                    "still_open": sum(1 for f in findings if f["publication"]["status"] == "still_open"),
                    "rejected": sum(1 for f in findings if f["publication"]["status"] == "rejected"),
                    "files_total": plan["files_total"], "files_reviewable": len(reviewable),
                    "files_reviewed": len(reviewable) - len(not_reviewed), "files_excluded": len(plan["excluded"]),
                    "coverage_complete": coverage_complete, "coverage_notes": notes},
        "findings": findings,
        "prior_findings": prior_findings,
        "coverage": coverage,
        "excluded_files": plan["excluded"],
    }
    return final


def headline_for(counts: dict, published: list[dict]) -> str:
    n = len(published)
    if n == 0:
        return "No actionable issues found in the reviewed changes."
    if n == 1:
        return "1 issue needs attention"
    return f"{n} issues need attention"


def cmd_finalize(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    agg = read_json(run_dir / "aggregated.json")
    errors, warns = validate_aggregate(agg)
    for w in warns:
        print(f"warning: {w}")
    if errors:
        for e in errors:
            print(f"error: {e}")
        print("finalize: aggregated.json is invalid. Fix the listed findings and rerun.")
        return 2
    plan = read_json(run_dir / "plan.json")
    pr = read_json(run_dir / "pr.json")
    threads = read_json(run_dir / "threads.json") if (run_dir / "threads.json").exists() else []
    merged = read_json(run_dir / "merged.json") if (run_dir / "merged.json").exists() else None
    collect = read_json(run_dir / "collect.json") if (run_dir / "collect.json").exists() else None
    snapshot = read_json(run_dir / "snapshot.json") if (run_dir / "snapshot.json").exists() else None
    final = finalize(agg, load_verifications(run_dir), threads, plan, merged, collect, pr, snapshot)
    write_json(run_dir / "final.json", final)
    s = final["summary"]
    print(f"finalize: {s['headline']} event={s['event']} blocking={s['blocking']} counts={s['counts']} "
          f"published={s['published']} withheld={s['withheld']} still_open={s['still_open']} rejected={s['rejected']} "
          f"coverage_complete={s['coverage_complete']}")
    for f in final["findings"]:
        print(f"  {f['id']} {f['level']:8} {f['publication']['status']:13} {f['verification']['status']:12} {f['title']}")
    for n in s["coverage_notes"]:
        print(f"  note: {n}")
    return 0


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def finding_text(f: dict) -> str:
    parts = [f.get("problem", "").strip(), f.get("consequence", "").strip(), (f.get("fix") or "").strip()]
    text = " ".join(p for p in parts if p)
    if f.get("fix_caveat"):
        text += f"\n\n> {f['fix_caveat'].strip()}"
    return text


def location_label(f: dict) -> str:
    loc = f.get("location") or {}
    if loc.get("file_path"):
        if loc.get("start_line") == loc.get("end_line"):
            return f"`{loc['file_path']}:{loc['end_line']}`"
        return f"`{loc['file_path']}:{loc['start_line']}-{loc['end_line']}`"
    paths = all_paths(f)
    return ", ".join(f"`{p}`" for p in paths[:4]) + (" and more" if len(paths) > 4 else "")


def inline_body(f: dict) -> str:
    return (f"**{f['title']}**\n\n{finding_text(f)}\n\n"
            f"<sub>{f['level']} · {f['id']}</sub>\n<!-- spk-finding: {f['fingerprint']} -->")


def inline_eligible(f: dict, anchors: dict[str, dict]) -> bool:
    if f.get("type") != "inline_comment":
        return False
    loc = f["location"]
    info = anchors.get(loc["file_path"])
    if not info or info.get("binary"):
        return False
    lines = info["new_lines"] if loc.get("side", "new") == "new" else info["old_lines"]
    return loc["start_line"] in lines and loc["end_line"] in lines


def build_review(final: dict, anchors: dict[str, dict], run_dir_label: str) -> tuple[str, list[dict]]:
    config_max_inline = 20
    pub = [f for f in final["findings"] if f["publication"]["status"] == "published"]
    pub.sort(key=lambda f: (LEVEL_RANK[f["level"]], -len(all_paths(f)), f["id"]))
    inline: list[dict] = []
    body_findings: list[dict] = []
    for f in pub:
        if inline_eligible(f, anchors) and len(inline) < config_max_inline:
            loc = f["location"]
            c = {"path": loc["file_path"], "line": loc["end_line"],
                 "side": "LEFT" if loc.get("side") == "old" else "RIGHT", "body": inline_body(f)}
            if loc["start_line"] != loc["end_line"]:
                c["start_line"] = loc["start_line"]
                c["start_side"] = c["side"]
            inline.append(c)
            f["publication"]["placement"] = "inline"
        else:
            body_findings.append(f)
            f["publication"]["placement"] = "body"
    inline_ids = {c["body"].split("· ")[-1].split("<")[0].strip() for c in inline}

    s = final["summary"]
    pr = final["pr"]
    head7 = short_sha(pr["head_sha"])
    lines = [REVIEW_MARKER, f"<!-- spk-review run={final['run']['id']} head={pr['head_sha']} -->",
             "## AI Code Review", "", f"**{s['headline']}**", ""]
    for f in pub:
        level_tag = f" ({f['level']})" if f["level"] != "warning" else ""
        if f["id"] in inline_ids:
            lines.append(f"- [ ] **{f['title']}**{level_tag} · see the comment at {location_label(f)} · {f['id']}")
        else:
            lines.append(f"- [ ] **{f['title']}**{level_tag}  ")
            for para in finding_text(f).split("\n\n"):
                lines.append(f"  {para}  ")
            lines.append(f"  {location_label(f)} · {f['id']} <!-- spk-finding: {f['fingerprint']} -->")
        lines.append("")
    unverified_severe = [f for f in pub if f["level"] == "severe" and f["verification"]["status"] != "verified"]
    if unverified_severe:
        ids = ", ".join(f["id"] for f in unverified_severe)
        lines.append(f"Severe findings {ids} could not be independently verified. They do not block merge until confirmed.")
        lines.append("")
    coverage_line = f"Reviewed {s['files_reviewed']} of {s['files_reviewable']} files at {head7}."
    if s["files_excluded"]:
        coverage_line += f" {s['files_excluded']} file(s) excluded from line review."
    coverage_line += " No coverage gaps." if s["coverage_complete"] else " **Review incomplete.** See details."
    lines.append(coverage_line)
    lines.append("")
    details = build_details(final, run_dir_label)
    footer = "\n<sub>Generated by AI Review Team</sub>"
    body = "\n".join(lines) + details + footer
    if len(body) > BODY_LIMIT:
        body = "\n".join(lines) + "\n<details><summary>Review details</summary>\n\nDetails omitted: the review body reached GitHub's size limit. See the local review file.\n\n</details>\n" + footer
    if len(body) > BODY_LIMIT:
        body = body[:BODY_LIMIT - len(footer) - 40] + "\n\n(truncated)\n" + footer
    return body, inline


def build_details(final: dict, run_dir_label: str) -> str:
    s = final["summary"]
    out = ["<details>", "<summary>Review details</summary>", ""]
    still_open = [f for f in final["findings"] if f["publication"]["status"] == "still_open"]
    if still_open:
        out.append("**Still open from earlier reviews**")
        for f in still_open:
            url = (f.get("prior_state") or {}).get("thread_url")
            link = f" · [thread]({url})" if url else ""
            out.append(f"- [ ] {f['title']} · {location_label(f)} · {f['level']}{link}")
        out.append("")
    reopened = [f for f in final["findings"] if (f.get("prior_state") or {}).get("state") == "reopened"]
    if reopened:
        out.append("**Resolved earlier but still present**")
        for f in reopened:
            url = (f.get("prior_state") or {}).get("thread_url")
            out.append(f"- {f['title']} · {location_label(f)}" + (f" · [thread]({url})" if url else ""))
        out.append("")
    withheld = [f for f in final["findings"] if f["publication"]["status"] == "withheld"]
    if withheld:
        out.append(f"**Not shown ({len(withheld)} lower-priority finding(s))**")
        for f in withheld:
            out.append(f"- {f['title']} · {location_label(f)} · {f['level']}")
        out.append("")
    accepted = [f for f in final["findings"] if f["publication"]["status"] == "accepted_risk"]
    if accepted:
        out.append("**Accepted risk (resolved by the author after discussion)**")
        for f in accepted:
            out.append(f"- {f['title']} · {location_label(f)}")
        out.append("")
    fixed = [p for p in final.get("prior_findings", []) if p["state"] == "not_found"]
    if fixed:
        out.append(f"**Not found at {short_sha(final['pr']['head_sha'])}**: {len(fixed)} earlier finding(s) were not re-detected.")
        out.append("")
    if s["coverage_notes"]:
        out.append("**Coverage notes**")
        for n in s["coverage_notes"]:
            out.append(f"- {n}")
        out.append("")
    if final.get("excluded_files"):
        out.append("**Excluded from line review**")
        out.append("")
        out.append("| Path | Reason |")
        out.append("|---|---|")
        for ex in final["excluded_files"]:
            out.append(f"| `{ex['path']}` | {ex['reason']} |")
        out.append("")
    out.append("**Agent coverage**")
    out.append("")
    out.append("| Agent | Assigned | Reviewed | Findings | Status |")
    out.append("|---|---|---|---|---|")
    for c in final["coverage"]:
        out.append(f"| {c['agent']} | {c['files_assigned']} | {c['files_reviewed']} | {c['findings']} | {c['status']} |")
    out.append("")
    out.append(f"Confidence, attribution, verification notes, and rejected candidates are in the local review file `{run_dir_label}/final.json`.")
    out.append("")
    out.append("</details>")
    return "\n" + "\n".join(out) + "\n"


def cmd_render(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    final = read_json(run_dir / "final.json")
    anchors = parse_unified_diff((run_dir / "diff.patch").read_text(encoding="utf-8"))
    try:
        label = os.path.relpath(run_dir)
    except ValueError:
        label = str(run_dir)
    if label.startswith(".."):
        label = str(Path(*run_dir.resolve().parts[-3:]))
    body, inline = build_review(final, anchors, label)
    payload = {"commit_id": final["pr"]["head_sha"], "event": final["summary"]["event"],
               "body": body, "comments": inline}
    write_text(run_dir / "review-body.md", body)
    write_json(run_dir / "payload.json", payload)
    write_json(run_dir / "final.json", final)
    print(f"render: {len(inline)} inline comment(s), body {len(body)} chars, event {payload['event']}")
    return 0


# ---------------------------------------------------------------------------
# post
# ---------------------------------------------------------------------------


def cmd_post(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    pr = read_json(run_dir / "pr.json")
    payload = read_json(run_dir / "payload.json")
    prior = read_json(run_dir / "prior_review.json") if (run_dir / "prior_review.json").exists() else None
    owner, repo, number = pr["owner"], pr["repo"], pr["number"]
    current = fetch_pr(owner, repo, number)
    result = {"posted_at": now_iso(), "head_sha": pr["head_sha"], "current_head_sha": current["head"]["sha"],
              "status": "", "review_id": None, "inline_posted": 0, "inline_folded": 0, "superseded": None, "notes": []}
    if current["head"]["sha"] != pr["head_sha"]:
        result["status"] = "stale"
        result["notes"].append(f"head moved from {short_sha(pr['head_sha'])} to {short_sha(current['head']['sha'])} during the review")
        if not a.allow_stale:
            write_json(run_dir / "post.json", result)
            print(json.dumps(result, indent=2))
            print("post: head moved. Rerun the review, or pass --allow-stale to post against the reviewed commit anyway.")
            return 3
        result["notes"].append("posted anyway with --allow-stale; the review is pinned to the reviewed commit")
    if a.dry_run:
        result["status"] = "dry_run"
        write_json(run_dir / "post.json", result)
        print(json.dumps(result, indent=2))
        return 0
    attempt_payload = dict(payload)
    tmp = run_dir / "payload.submit.json"
    for attempt in (1, 2):
        write_json(tmp, attempt_payload)
        proc = run(["gh", "api", f"repos/{owner}/{repo}/pulls/{number}/reviews", "--method", "POST", "--input", str(tmp)], check=False)
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            result["review_id"] = data.get("id")
            result["inline_posted"] = len(attempt_payload["comments"])
            result["status"] = "posted"
            break
        err = proc.stderr.strip() or proc.stdout.strip()
        result["notes"].append(f"attempt {attempt} failed: {err[:500]}")
        if attempt == 1 and attempt_payload["comments"]:
            folded = attempt_payload["comments"]
            result["inline_folded"] = len(folded)
            extra = ["", "### Comments that could not be anchored to the diff", ""]
            for c in folded:
                extra.append(f"- `{c['path']}:{c['line']}`\n\n" + "\n".join("  " + l for l in c["body"].splitlines()))
            body = attempt_payload["body"].replace("\n<sub>Generated by AI Review Team</sub>", "\n".join(extra) + "\n<sub>Generated by AI Review Team</sub>")
            attempt_payload = {**attempt_payload, "body": body[:BODY_LIMIT], "comments": []}
            continue
        result["status"] = "failed"
    tmp.unlink(missing_ok=True)
    if result["status"] == "posted" and prior and prior.get("id"):
        sup = {"review_id": prior["id"], "edited": False, "dismissed": False}
        new_body = (f"{REVIEW_MARKER}\n_Superseded by the review of {short_sha(pr['head_sha'])}._\n\n<details><summary>Earlier review</summary>\n\n"
                    + prior["body"].replace(REVIEW_MARKER, "") + "\n\n</details>")
        edit = run(["gh", "api", f"repos/{owner}/{repo}/pulls/{number}/reviews/{prior['id']}", "--method", "PUT",
                    "-f", f"body={new_body[:BODY_LIMIT]}"], check=False)
        sup["edited"] = edit.returncode == 0
        if prior.get("state") == "CHANGES_REQUESTED":
            dis = run(["gh", "api", f"repos/{owner}/{repo}/pulls/{number}/reviews/{prior['id']}/dismissals", "--method", "PUT",
                       "-f", "message=Superseded by an updated AI review", "-f", "event=DISMISS"], check=False)
            sup["dismissed"] = dis.returncode == 0
            if not sup["dismissed"]:
                result["notes"].append(f"could not dismiss prior review {prior['id']}: {dis.stderr.strip()[:200]}")
        result["superseded"] = sup
    write_json(run_dir / "post.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "posted" else 7


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# usage
# ---------------------------------------------------------------------------

USAGE_FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
USAGE_LABELS = {"input_tokens": "input", "cache_creation_input_tokens": "cache write",
                "cache_read_input_tokens": "cache read", "output_tokens": "output"}
PLUGIN_PREFIX = "spk-github:"


def parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(round(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def iter_transcript(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def message_text(message: dict | None) -> str:
    content = (message or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def transcript_usage(path: Path, *, since: dt.datetime | None = None, sidechain: bool | None = None) -> dict:
    """Sum API usage recorded in one transcript.

    Claude Code writes one line per content block of an API response, each
    carrying the same usage object, so responses are deduplicated by message id
    before summing. Entries older than `since` are skipped.
    """
    responses: dict[str, dict] = {}
    models: set[str] = set()
    first: dt.datetime | None = None
    last: dt.datetime | None = None
    for entry in iter_transcript(path):
        ts = parse_ts(entry.get("timestamp"))
        if since and ts and ts < since:
            continue
        if sidechain is not None and bool(entry.get("isSidechain")) != sidechain:
            continue
        if ts:
            first = ts if first is None or ts < first else first
            last = ts if last is None or ts > last else last
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        key = message.get("id") or entry.get("requestId") or entry.get("uuid")
        responses[key] = usage
        if message.get("model"):
            models.add(message["model"])
    totals = {field: sum(int(u.get(field) or 0) for u in responses.values()) for field in USAGE_FIELDS}
    totals["total_tokens"] = sum(totals.values())
    duration = (last - first).total_seconds() if first and last else None
    return {
        "calls": len(responses), "models": sorted(models),
        "first_at": first.isoformat() if first else None,
        "last_at": last.isoformat() if last else None,
        "duration_seconds": duration, **totals,
    }


def agent_label(transcript: Path, prompt: str) -> str:
    meta_path = transcript.with_name(transcript.name[:-len(".jsonl")] + ".meta.json")
    name = None
    if meta_path.exists():
        try:
            name = (read_json(meta_path) or {}).get("agentType")
        except (OSError, ValueError):
            name = None
    if not name:
        m = re.search(r"output:\s*\S+/agents/([A-Za-z0-9_.-]+)\.json", prompt)
        name = m.group(1) if m else None
    if not name:
        name = "spk-reviewer-verifier" if re.search(r"^batch:", prompt, re.M) else "unknown-agent"
    if name.startswith(PLUGIN_PREFIX):
        name = name[len(PLUGIN_PREFIX):]
    batch = re.search(r"^batch:\s*(\S+)", prompt, re.M)
    if batch and "verifier" in name:
        name = f"{name} ({batch.group(1)})"
    return name


def find_session_files(projects_dir: Path, session_id: str) -> tuple[Path | None, Path | None]:
    main_transcript = next(iter(sorted(projects_dir.glob(f"*/{session_id}.jsonl"))), None)
    subagent_dir = next(iter(sorted(projects_dir.glob(f"*/{session_id}/subagents"))), None)
    return main_transcript, subagent_dir


def collect_usage(run_dir: Path, projects_dir: Path, session_id: str, *, now: dt.datetime | None = None) -> dict:
    collect = read_json(run_dir / "collect.json")
    run_id = collect["run_id"]
    started = parse_ts(collect.get("collected_at"))
    finished = now or dt.datetime.now(dt.timezone.utc)
    report = {
        "run_id": run_id, "session_id": session_id,
        "started_at": started.isoformat() if started else None,
        "finished_at": finished.replace(microsecond=0).isoformat(),
        "elapsed_seconds": (finished - started).total_seconds() if started else None,
        "agents": [], "orchestrator": None, "warnings": [],
    }
    main_transcript, subagent_dir = find_session_files(projects_dir, session_id)
    if subagent_dir is None:
        report["warnings"].append(f"no subagent transcripts found for session {session_id} under {projects_dir}")
    else:
        for transcript in sorted(subagent_dir.glob("agent-*.jsonl")):
            first_user = next((e for e in iter_transcript(transcript) if e.get("type") == "user"), None)
            prompt = message_text((first_user or {}).get("message"))
            if run_id not in prompt:
                continue
            usage = transcript_usage(transcript)
            report["agents"].append({"agent": agent_label(transcript, prompt), "transcript": str(transcript), **usage})
    if main_transcript is None:
        report["warnings"].append(f"no session transcript found for session {session_id} under {projects_dir}")
    else:
        usage = transcript_usage(main_transcript, since=started, sidechain=False)
        report["orchestrator"] = {"agent": "orchestrator", "transcript": str(main_transcript), **usage}
    agents_total = {field: sum(a[field] for a in report["agents"]) for field in (*USAGE_FIELDS, "total_tokens")}
    agents_total["calls"] = sum(a["calls"] for a in report["agents"])
    report["agents_total"] = agents_total
    grand = dict(agents_total)
    if report["orchestrator"]:
        for field in (*USAGE_FIELDS, "total_tokens", "calls"):
            grand[field] += report["orchestrator"][field]
    report["grand_total"] = grand
    if not report["agents"]:
        report["warnings"].append(f"no agent transcript mentions run {run_id}; agent usage is unknown")
    return report


def render_usage(report: dict) -> str:
    rows = list(report["agents"]) + ([report["orchestrator"]] if report["orchestrator"] else [])
    name_width = max([len("everything")] + [len(r["agent"]) for r in rows]) + 2
    model_width = max([len("model")] + [len(", ".join(r["models"])) for r in rows]) + 2
    header = (f"{'agent':<{name_width}}{'model':<{model_width}}{'calls':>6}"
              + "".join(f"{USAGE_LABELS[f]:>13}" for f in USAGE_FIELDS)
              + f"{'total':>13}{'time':>10}")

    def line(label: str, model: str, data: dict, duration: float | None) -> str:
        return (f"{label:<{name_width}}{model:<{model_width}}{data['calls']:>6}"
                + "".join(f"{data[f]:>13,}" for f in USAGE_FIELDS)
                + f"{data['total_tokens']:>13,}{format_duration(duration):>10}")

    out = [f"Token usage for run {report['run_id']}", header, "-" * len(header)]
    for r in rows:
        out.append(line(r["agent"], ", ".join(r["models"]), r, r.get("duration_seconds")))
    out.append("-" * len(header))
    out.append(line(f"all agents ({len(report['agents'])})", "", report["agents_total"], None))
    if report["orchestrator"]:
        out.append(line("everything", "", report["grand_total"], None))
    out.append("")
    out.append(f"Elapsed: {format_duration(report['elapsed_seconds'])} "
               f"(collect {report['started_at'] or '?'} to {report['finished_at']})")
    for w in report["warnings"]:
        out.append(f"warning: {w}")
    return "\n".join(out)


def cmd_usage(a: argparse.Namespace) -> int:
    run_dir = Path(a.run_dir)
    session_id = a.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session_id:
        print("usage unavailable: CLAUDE_CODE_SESSION_ID is not set and --session-id was not given")
        return 0
    projects_dir = Path(a.projects_dir) if a.projects_dir else Path.home() / ".claude" / "projects"
    try:
        report = collect_usage(run_dir, projects_dir, session_id)
    except (OSError, ValueError, KeyError) as exc:
        print(f"usage unavailable: {exc}")
        return 0
    write_json(run_dir / "usage.json", report)
    print(render_usage(report))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="spk_review", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="fetch PR metadata, files, diff, threads")
    c.add_argument("--repo", required=True, help="OWNER/REPO")
    c.add_argument("--pr", required=True, help="PR number")
    c.add_argument("--out", default=".reviews", help="output root (default .reviews)")
    c.set_defaults(func=cmd_collect)

    for name, func, help_text in (("snapshot", cmd_snapshot, "check out the head SHA into an isolated directory"),
                                  ("route", cmd_route, "build the review plan"),
                                  ("ingest", cmd_ingest, "validate and merge specialist output"),
                                  ("verify-plan", cmd_verify_plan, "list candidates needing verification"),
                                  ("finalize", cmd_finalize, "apply verification and select findings"),
                                  ("render", cmd_render, "render the review body and payload"),
                                  ("cleanup", cmd_cleanup, "remove the snapshot")):
        s = sub.add_parser(name, help=help_text)
        s.add_argument("run_dir")
        s.set_defaults(func=func)

    f = sub.add_parser("fetch-file", help="fetch one file at the head SHA")
    f.add_argument("run_dir")
    f.add_argument("path")
    f.set_defaults(func=cmd_fetch_file)

    po = sub.add_parser("post", help="recheck head and post the review")
    po.add_argument("run_dir")
    po.add_argument("--allow-stale", action="store_true")
    po.add_argument("--dry-run", action="store_true")
    po.set_defaults(func=cmd_post)

    u = sub.add_parser("usage", help="sum token usage and elapsed time for the run")
    u.add_argument("run_dir")
    u.add_argument("--session-id", help="Claude Code session id (default: $CLAUDE_CODE_SESSION_ID)")
    u.add_argument("--projects-dir", help="transcript root (default: ~/.claude/projects)")
    u.set_defaults(func=cmd_usage)

    v = sub.add_parser("validate", help="validate a JSON file")
    v.add_argument("file")
    v.add_argument("--schema", choices=("specialist", "aggregate"), default="specialist")
    v.set_defaults(func=cmd_validate)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
