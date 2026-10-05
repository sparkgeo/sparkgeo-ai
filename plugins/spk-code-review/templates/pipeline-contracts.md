# Pipeline Contracts

This file defines the JSON that each non-reviewer stage of the `spk-code-review` pipeline produces. Specialist reviewers use `finding-schema.json` instead.

Every stage returns **one JSON code block and nothing else**.

```text
context-builder ─► risk-classifier ─► coordinator ─► specialists (parallel) ─► verifier ─► synthesizer
     (1)                (2)               (3)              (4, 5)                 (6)          (7)
```

## 1. Context package (`spk-cr-context-builder`)

```json
{
  "change_summary": "Adds retry with backoff to the job submission client.",
  "intent": "Make job submission tolerate transient upstream failures (from PR body and linked issue #412).",
  "intent_matches_implementation": true,
  "intent_mismatch_notes": [],
  "linked_issues": ["#412"],
  "affected_components": [
    { "name": "jobs worker", "paths": ["src/jobs/"], "role": "Submits jobs to the upstream scheduler API." }
  ],
  "changed_files": [
    {
      "path": "src/jobs/worker.py",
      "status": "M",
      "additions": 40,
      "deletions": 6,
      "kind": "source",
      "behavior_change": true,
      "notes": "Adds retry loop around submit()."
    }
  ],
  "mechanical_files": ["uv.lock"],
  "related_files": [
    { "path": "src/jobs/client.py", "why": "submit() is defined here; called by the changed code." }
  ],
  "test_files": [
    { "path": "tests/jobs/test_worker.py", "changed": true }
  ],
  "architecture_rules": [
    { "rule": "Domain services must not import from api/.", "source": "docs/adr/0003-layering.md", "kind": "fact" }
  ],
  "repository_conventions": [
    { "convention": "HTTP clients use the shared session in src/common/http.py.", "source": "src/common/http.py usage in 6 modules", "kind": "inferred" }
  ],
  "ownership": [
    { "path": "src/jobs/", "owners": ["@sparkgeo/platform"], "source": ".github/CODEOWNERS" }
  ],
  "history_notes": [
    "src/jobs/worker.py had a duplicate-job bug fixed in 3f2a9c1 (2026-07-02)."
  ],
  "deterministic_results": {
    "ci_checks": { "status": "passing", "failing": [], "pending": [] },
    "scanners": { "gitleaks": "0 findings", "semgrep": "not installed" },
    "notes": []
  },
  "unknowns": [
    "Could not find the upstream API contract for idempotency."
  ]
}
```

Rules:

- `kind: "fact"` means the item comes from a file in the repo. `kind: "inferred"` means the context builder deduced it.
- `kind` on a changed file is one of `source`, `test`, `config`, `infrastructure`, `migration`, `dependency_manifest`, `lockfile`, `docs`, `generated`, `asset`.

## 2. Risk classification (`spk-cr-risk-classifier`)

```json
{
  "risk": "high",
  "confidence": "high",
  "reasons": [
    "Changes authorization checks for project resources (src/api/projects.py:40-61)",
    "Modifies a public API endpoint"
  ],
  "domains": ["authorization", "public_api", "sensitive_data"],
  "risk_factors": {
    "blast_radius": "high",
    "reversibility": "medium",
    "data_sensitivity": "high",
    "change_complexity": "medium",
    "validation_strength": "high"
  },
  "escalations": ["Repository policy: authorization is always high"],
  "de_escalations_considered": ["Tests pass, but policy prevents downgrade"],
  "minimum_review_path": [
    "author_review",
    "automated_checks",
    "ai_specialist_review",
    "senior_or_specialist_human_review"
  ],
  "human_review_required": true,
  "specialist_human_review_required": true,
  "requires_human_confirmation": false,
  "uncertainties": []
}
```

Allowed `domains`: `authentication`, `authorization`, `permissions`, `cryptography`, `secrets`, `sensitive_data`, `privacy`, `tenant_isolation`, `public_api`, `internal_api`, `database_schema`, `data_migration`, `destructive_data_operation`, `infrastructure`, `iam`, `networking`, `deployment_config`, `ci_cd`, `billing`, `concurrency`, `performance`, `dependencies`, `architecture`, `frontend`, `business_logic`, `tests_only`, `docs_only`, `mechanical`.

Allowed risk factor values: `low`, `medium`, `high`.

## 3. Routing plan (`spk-cr-coordinator`)

```json
{
  "risk": "high",
  "domains": ["authorization", "public_api"],
  "required_agents": [
    {
      "agent": "spk-cr-security",
      "depth": "deep",
      "files": ["src/api/projects.py", "src/services/access.py"],
      "focus": "Object-level authorization on GET /projects/{id}.",
      "reason": "Authorization logic changed."
    }
  ],
  "optional_agents": [
    {
      "agent": "spk-cr-api-compatibility",
      "depth": "standard",
      "files": ["src/api/projects.py", "openapi.yaml"],
      "focus": "Response field removed.",
      "reason": "Public API change."
    }
  ],
  "skipped_agents": [
    { "agent": "spk-cr-performance-ops", "reason": "No change to queries, loops, or I/O paths." }
  ],
  "high_scrutiny_files": ["src/services/access.py"],
  "coverage_manifest": [
    { "file": "src/api/projects.py", "agents": ["spk-cr-security", "spk-cr-correctness"] }
  ],
  "unreviewed_files": [
    { "file": "uv.lock", "reason": "Mechanical lockfile. Covered by spk-cr-dependency via pyproject.toml." }
  ],
  "human_review_required": true,
  "human_review_profile": ["senior_application", "security"],
  "routing_rationale": "Authorization change on a public endpoint: security, correctness, tests, and architecture are required."
}
```

Rules:

- The orchestrator runs every entry in `required_agents` and `optional_agents`. "Optional" means the agent was added by a conditional trigger, not that it may be skipped.
- `depth` is one of `light`, `standard`, `deep`.
- Allowed `human_review_profile` values: `application`, `senior_application`, `security`, `database_operations`, `infrastructure_platform`, `architecture`, `frontend`, `billing_domain`.

## 4-5. Specialist output

See `finding-schema.json` and `reviewer-guide.md`.

## 6. Verification results (`spk-cr-verifier`)

```json
{
  "results": [
    {
      "finding_id": "security-2",
      "status": "confirmed",
      "confidence": "high",
      "severity": "blocker",
      "reason": "get_project() loads by ID at line 44 and returns at line 52. No call to check_access() on any path. The router has no dependency that enforces ownership.",
      "evidence_checked": [
        "src/api/projects.py:40-61",
        "src/api/deps.py: get_current_user only authenticates",
        "tests/api/test_projects.py: no cross-user test"
      ],
      "mitigations_found": []
    }
  ]
}
```

Allowed `status`: `confirmed`, `partially_confirmed`, `unconfirmed`, `rejected`, `requires_human_review`.

`severity` is the verifier's adjusted severity. It may be lower than the original, and higher only with a stated reason.

## 7. Synthesis (`spk-cr-synthesizer`)

The orchestrator saves this to `.reviews/` and turns it into the GitHub review.

```json
{
  "version": "1.0",
  "pr": {
    "number": 42,
    "repo": "sparkgeo/example",
    "title": "Restrict project access",
    "base_ref": "main",
    "head_ref": "feature/project-acl",
    "head_sha": "abc123"
  },
  "assessment": "request_changes",
  "summary": "Adds per-project access checks. One endpoint still returns projects without an ownership check.",
  "risk": {
    "level": "high",
    "confidence": "high",
    "reasons": ["Changes authorization checks for project resources"],
    "minimum_review_path": ["author_review", "automated_checks", "ai_specialist_review", "senior_or_specialist_human_review"]
  },
  "findings": [
    {
      "id": "CR-001",
      "severity": "blocker",
      "confidence": "high",
      "category": "authorization",
      "title": "GET /projects/{id} returns any project without an access check",
      "body": "`get_project()` loads the project by ID and returns it. It never calls `check_access()`. A user who knows another project ID can read it.",
      "recommendation": "Call `check_access(user, project)` in the service layer before returning.",
      "file": "src/api/projects.py",
      "start_line": 44,
      "end_line": 52,
      "side": "new",
      "related_files": [],
      "found_by": ["spk-cr-security", "spk-cr-correctness", "spk-cr-architecture"],
      "verification": "confirmed",
      "placement": "inline",
      "previously_flagged": false
    }
  ],
  "questions": [
    {
      "question": "Should archived projects stay visible to former members?",
      "file": "src/services/access.py",
      "start_line": 30,
      "end_line": 30
    }
  ],
  "positive_observations": [
    "The new access tests cover both owner and non-owner cases for update."
  ],
  "specialist_review_recommended": [
    { "profile": "security", "reason": "Authorization boundary for project data changed." }
  ],
  "merge_gate": {
    "deterministic_checks_pass": true,
    "verified_blockers": 1,
    "high_confidence_security_findings": 1,
    "required_agents_completed": true,
    "risk_permits_auto_approval": false,
    "auto_approval_eligible": false
  },
  "budget": {
    "issues_limit": 10,
    "suggestions_limit": 5,
    "nits_limit": 0,
    "folded_into_summary": 2
  },
  "stats": {
    "agents_run": ["spk-cr-architecture", "spk-cr-correctness", "spk-cr-security", "spk-cr-tests"],
    "raw_findings": 9,
    "duplicates_merged": 3,
    "rejected_by_verifier": 2,
    "dropped_low_value": 1,
    "suppressed_as_addressed": 0,
    "per_agent": [
      { "agent": "spk-cr-security", "raw": 3, "kept": 1, "rejected": 1 }
    ]
  }
}
```

Rules:

- `assessment` is one of `approve`, `approve_with_suggestions`, `request_changes`.
- `placement` is `inline` (anchored to a diff line) or `summary` (in the review body).
- `verification` is the verifier status, or `not_required` when the finding was not sent to the verifier.
- `found_by` lists every specialist that reported the finding.
- `stats` exists so the team can track false-positive rate, duplicate rate, and comment volume per agent over time.
