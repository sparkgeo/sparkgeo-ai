"""Tests for the deterministic review tool. Run: python3 -m unittest discover -s plugins/spk-github/tests"""
from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "spk_review.py"
spec = importlib.util.spec_from_file_location("spk_review", SCRIPT)
spk = importlib.util.module_from_spec(spec)
sys.modules["spk_review"] = spk
spec.loader.exec_module(spk)

DIFF = """diff --git a/src/api/features.py b/src/api/features.py
--- a/src/api/features.py
+++ b/src/api/features.py
@@ -10,7 +10,7 @@ def list_features():
 context_a
-    return {"features": rows}
+    return {"items": rows}
 context_b
@@ -40,3 +40,6 @@ def other():
     pass
+
+def new_fn():
+    return 1
diff --git a/web/src/Map.tsx b/web/src/Map.tsx
--- a/web/src/Map.tsx
+++ b/web/src/Map.tsx
@@ -1,3 +1,5 @@
 import React from 'react'
+const onClick = () => load()
+<button onClick={onClick}>Go</button>
 export default Map
diff --git a/old/name.py b/new/name.py
similarity index 90%
rename from old/name.py
rename to new/name.py
--- a/old/name.py
+++ b/new/name.py
@@ -1,2 +1,2 @@
-x = 1
+x = 2
 y = 3
diff --git a/assets/logo.png b/assets/logo.png
Binary files a/assets/logo.png and b/assets/logo.png differ
diff --git a/removed.py b/removed.py
--- a/removed.py
+++ /dev/null
@@ -1,2 +0,0 @@
-gone = True
-really = True
"""


def make_finding(**over):
    base = {
        "id": "CR-001", "type": "inline_comment", "level": "severe", "category": "api_contract",
        "confidence": "high", "title": "The response rename breaks the map client",
        "problem": "The endpoint now returns `items`, but `loadFeatures()` still reads `features`.",
        "consequence": "The map renders no results.",
        "fix": "Update the client with this change and add a contract test.",
        "evidence": ["src/api/features.py:12: return {\"items\": rows}"],
        "introduced_by_pr": True,
        "dedupe_key": "api_contract|response_rename_items|src/api/features.py",
        "location": {"file_path": "src/api/features.py", "side": "new", "start_line": 12, "end_line": 12},
    }
    base.update(over)
    return base


BIG_PY_DIFF = DIFF + """diff --git a/src/api/routes.py b/src/api/routes.py
--- a/src/api/routes.py
+++ b/src/api/routes.py
@@ -1,2 +1,30 @@
 import x
+@router.get("/items")
""" + "".join(f"+line_{i} = {i}\n" for i in range(28)) + """ y = 1
"""


def make_plan(files, config=None, diff=DIFF):
    parsed = spk.parse_unified_diff(diff)
    cfg = dict(spk.DEFAULT_CONFIG)
    cfg.update(config or {})
    plan = spk.route_files(files, parsed, cfg)
    plan.update({"run_id": "run1", "head_sha": "a" * 40, "base_sha": "b" * 40, "config": cfg,
                 "config_source": "defaults",
                 "excluded": [{"path": m["path"], "reason": m["exclude_reason"]} for m in plan["manifest"] if not m["review"]],
                 "files_total": len(files), "files_reviewable": sum(1 for m in plan["manifest"] if m["review"])})
    return plan


PR = {"title": "Rename features to items", "number": 7, "url": "https://github.com/o/r/pull/7", "author": "alice",
      "base_ref": "main", "head_ref": "feat", "base_sha": "b" * 40, "head_sha": "a" * 40}


class DiffParserTests(unittest.TestCase):
    def test_new_and_old_side_anchors(self):
        parsed = spk.parse_unified_diff(DIFF)
        f = parsed["src/api/features.py"]
        self.assertIn(12, f["new_lines"])          # added line
        self.assertIn(11, f["new_lines"])          # context line
        self.assertIn(12, f["old_lines"])          # removed line on the old side
        self.assertIn(43, f["new_lines"])
        self.assertNotIn(44, f["new_lines"])
        self.assertNotIn(30, f["new_lines"])
        self.assertEqual(f["added_text"][0], '    return {"items": rows}')

    def test_rename_binary_and_deletion(self):
        parsed = spk.parse_unified_diff(DIFF)
        self.assertIn("new/name.py", parsed)
        self.assertEqual(parsed["new/name.py"]["old_path"], "old/name.py")
        self.assertTrue(parsed["assets/logo.png"]["binary"])
        self.assertIn("removed.py", parsed)
        self.assertEqual(parsed["removed.py"]["old_lines"], {1, 2})
        self.assertEqual(parsed["removed.py"]["new_lines"], set())

    def test_build_diff_from_patches_roundtrip(self):
        files = [{"filename": "a.py", "status": "modified", "patch": "@@ -1,2 +1,2 @@\n-x\n+y\n z"},
                 {"filename": "img.png", "status": "added", "patch": None}]
        parsed = spk.parse_unified_diff(spk.build_diff_from_patches(files))
        self.assertEqual(parsed["a.py"]["new_lines"], {1, 2})
        self.assertTrue(parsed["img.png"]["binary"])


class RoutingTests(unittest.TestCase):
    def files(self, *paths, status="M"):
        return [{"path": p, "status": status} for p in paths]

    def agents_for(self, plan, path):
        return next(m for m in plan["manifest"] if m["path"] == path)["reviewers"]

    def test_tsx_gets_primary_security_frontend_ux_not_five_agents(self):
        plan = make_plan(self.files("web/src/Map.tsx"))
        reviewers = self.agents_for(plan, "web/src/Map.tsx")
        self.assertEqual(set(reviewers), {spk.PRIMARY, spk.SECURITY, "spk-reviewer-frontend", "spk-reviewer-ux"})

    def test_python_gets_primary_security_backend_only(self):
        plan = make_plan(self.files("src/api/features.py"))
        reviewers = self.agents_for(plan, "src/api/features.py")
        self.assertEqual(set(reviewers), {spk.PRIMARY, spk.SECURITY, "spk-reviewer-backend-python"})
        self.assertEqual(plan["triggers"], [])   # only 4 added lines, no API change

    def test_behaviour_triggers_route_absences(self):
        plan = make_plan(self.files("src/api/routes.py"), diff=BIG_PY_DIFF)
        triggers = {t["trigger"]: t for t in plan["triggers"]}
        self.assertIn("behaviour_change_without_tests", triggers)
        self.assertIn("api_change_without_docs", triggers)
        reviewers = self.agents_for(plan, "src/api/routes.py")
        self.assertIn("spk-reviewer-tests", reviewers)
        self.assertIn("spk-reviewer-docs", reviewers)
        tests_agent = next(a for a in plan["agents"] if a["name"] == "spk-reviewer-tests")
        self.assertEqual(tests_agent["triggers"][0]["trigger"], "behaviour_change_without_tests")

    def test_python_quality_is_opt_in(self):
        plan = make_plan(self.files("src/api/features.py"))
        self.assertNotIn("spk-reviewer-python-quality", [a["name"] for a in plan["agents"]])
        plan = make_plan(self.files("src/api/features.py"), {"optional_reviewers": ["spk-reviewer-python-quality"]})
        self.assertIn("spk-reviewer-python-quality", [a["name"] for a in plan["agents"]])

    def test_lockfile_and_binary_go_to_security_only(self):
        plan = make_plan(self.files("uv.lock", "assets/logo.png"))
        for path in ("uv.lock", "assets/logo.png"):
            item = next(m for m in plan["manifest"] if m["path"] == path)
            self.assertFalse(item["review"])
            self.assertEqual(item["reviewers"], [spk.SECURITY])
        self.assertEqual([a["name"] for a in plan["agents"]], [spk.SECURITY])

    def test_repo_policy_exclusion_is_shown_with_reason(self):
        plan = make_plan(self.files("fixtures/big.json"), {"exclude": ["fixtures/**"]})
        item = plan["manifest"][0]
        self.assertEqual(item["kind"], "excluded")
        self.assertIn("repository policy", item["exclude_reason"])
        self.assertEqual(plan["agents"], [])

    def test_tests_present_suppresses_missing_test_trigger(self):
        plan = make_plan(self.files("src/api/routes.py", "tests/test_features.py"), diff=BIG_PY_DIFF)
        triggers = {t["trigger"] for t in plan["triggers"]}
        self.assertNotIn("behaviour_change_without_tests", triggers)
        self.assertIn("spk-reviewer-tests", self.agents_for(plan, "tests/test_features.py"))

    def test_glob_semantics(self):
        self.assertTrue(spk.glob_match("alembic/**", "alembic/versions/0001_init.py"))
        self.assertTrue(spk.glob_match("**/__tests__/**", "web/src/__tests__/Map.test.tsx"))
        self.assertTrue(spk.glob_match("*.tsx", "web/src/Map.tsx"))
        self.assertFalse(spk.glob_match("theme/**", "web/theme.ts"))
        self.assertTrue(spk.glob_match(".github/workflows/**", ".github/workflows/ci.yml"))


class ThreadTests(unittest.TestCase):
    def node(self, replies):
        comments = [{"databaseId": 1, "body": "**Title**\n\nText\n\n<sub>warning · CR-001</sub>\n<!-- spk-finding: api_contract|rename|src/a.py -->",
                     "createdAt": "t", "author": {"login": "ai-bot"}}]
        for login in replies:
            comments.append({"databaseId": 2, "body": "reply", "createdAt": "t", "author": {"login": login}})
        return {"id": "T1", "isResolved": False, "isOutdated": False, "path": "src/a.py", "line": 3,
                "startLine": None, "diffSide": "RIGHT", "comments": {"pageInfo": {"hasNextPage": False}, "nodes": comments}}

    def test_reply_by_other_commenter_is_not_author_reply(self):
        t = spk.normalize_thread(self.node(["bob"]), "alice", "https://github.com/o/r/pull/7")
        self.assertFalse(t["author_replied"])
        self.assertEqual(t["status"], "open")
        self.assertTrue(t["is_ai_review"])
        self.assertEqual(t["fingerprint"], "api_contract|rename|src/a.py")
        self.assertEqual(t["level"], "warning")

    def test_reply_by_pr_author_is_discussed_not_addressed(self):
        t = spk.normalize_thread(self.node(["alice"]), "alice", "https://github.com/o/r/pull/7")
        self.assertTrue(t["author_replied"])
        self.assertEqual(t["status"], "discussed")

    def test_legacy_thread_detected(self):
        node = self.node([])
        node["comments"]["nodes"][0]["body"] = "**warning** · `security` · confidence: high\n\n**Old style**\n\n<sub>Found by: x · CR-002</sub>"
        t = spk.normalize_thread(node, "alice", "u")
        self.assertTrue(t["is_ai_review"])
        self.assertIsNone(t["fingerprint"])
        self.assertEqual(t["cr_id"], "CR-002")


class ValidationTests(unittest.TestCase):
    def test_valid_finding_passes(self):
        errors, warns = spk.validate_finding(make_finding(), 0, aggregate=False)
        self.assertEqual(errors, [])

    def test_missing_evidence_and_fix_rejected_for_warning(self):
        f = make_finding(level="warning", evidence=[], fix="")
        errors, _ = spk.validate_finding(f, 0, aggregate=False)
        self.assertTrue(any("evidence" in e for e in errors))
        self.assertTrue(any("fix is required" in e for e in errors))

    def test_question_needs_no_fix(self):
        f = make_finding(level="question", fix=None, evidence=[])
        f.pop("fix")
        errors, _ = spk.validate_finding(f, 0, aggregate=False)
        self.assertEqual(errors, [])

    def test_side_and_line_order_enforced(self):
        f = make_finding(location={"file_path": "a.py", "start_line": 5, "end_line": 3})
        errors, _ = spk.validate_finding(f, 0, aggregate=False)
        self.assertTrue(any("side" in e for e in errors))
        self.assertTrue(any("start_line <= end_line" in e for e in errors))

    def test_word_budget(self):
        long = " ".join(["word"] * 120)
        errors, _ = spk.validate_finding(make_finding(problem=long), 0, aggregate=False)
        self.assertTrue(any("hard max" in e for e in errors))
        _, warns = spk.validate_finding(make_finding(problem=" ".join(["word"] * 75)), 0, aggregate=False)
        self.assertTrue(warns)

    def test_unknown_fields_and_legacy_names_rejected(self):
        f = make_finding(blocking=True, why_it_matters="x")
        errors, _ = spk.validate_finding(f, 0, aggregate=False)
        self.assertTrue(any("unknown fields" in e for e in errors))

    def test_specialist_document(self):
        doc = {"version": "2.0", "agent": {"name": "spk-reviewer-security", "role": "security"},
               "files": [{"path": "a.py", "status": "reviewed"}], "findings": [make_finding()]}
        errors, _ = spk.validate_specialist(doc, "spk-reviewer-security")
        self.assertEqual(errors, [])
        bad = copy.deepcopy(doc)
        bad["agent"]["role"] = "backend"
        bad["summary"] = {}
        errors, _ = spk.validate_specialist(bad)
        self.assertTrue(any("agent.role" in e for e in errors))
        self.assertTrue(any("unknown top-level" in e for e in errors))


class MergeTests(unittest.TestCase):
    def test_exact_key_dedupe_keeps_highest_level_and_all_agents(self):
        a = make_finding(level="warning", confidence="medium")
        a["_agent"] = "spk-reviewer-backend-python"
        b = make_finding(level="severe", confidence="high", dedupe_key="api_contract|response_rename_items|src/api/features.py|list_features|12-12",
                         evidence=["web/src/Map.tsx:4: loadFeatures() reads features"])
        b["_agent"] = spk.PRIMARY
        c = make_finding(id="CR-002", dedupe_key="correctness|other|x.py", location={"file_path": "x.py", "side": "new", "start_line": 1, "end_line": 1})
        c["_agent"] = spk.PRIMARY
        merged = spk.merge_candidates([a, b, c])
        self.assertEqual(len(merged), 2)
        top = merged[0]
        self.assertEqual(top["level"], "severe")
        self.assertEqual(set(top["found_by"]), {"spk-reviewer-backend-python", spk.PRIMARY})
        self.assertEqual(len(top["evidence"]), 2)
        self.assertEqual([m["id"] for m in merged], ["CR-001", "CR-002"])
        self.assertEqual(top["fingerprint"], "api_contract|response_rename_items|src/api/features.py")


class FinalizeTests(unittest.TestCase):
    def setUp(self):
        self.files = [{"path": "src/api/features.py", "status": "M"}, {"path": "web/src/Map.tsx", "status": "M"}]
        self.plan = make_plan(self.files)
        self.merged = {"agents": {a["name"]: {"status": "ok", "reviewed": a["files"], "partial": [], "skipped": [],
                                               "not_reported": [], "findings": 1} for a in self.plan["agents"]}}
        self.collect = {"warnings": [], "files_count_match": True, "head_consistent": True}
        self.snapshot = {"method": "worktree", "verified": True}

    def agg(self, findings):
        for i, f in enumerate(findings, 1):
            f["id"] = f"CR-{i:03d}"
            f.setdefault("found_by", [spk.PRIMARY])
        return {"version": "2.0", "findings": findings}

    def test_verified_severe_blocks_only_when_policy_allows(self):
        agg = self.agg([make_finding()])
        ver = {"CR-001": {"id": "CR-001", "status": "verified", "method": "read caller", "note": ""}}
        final = spk.finalize(agg, ver, [], self.plan, self.merged, self.collect, PR, self.snapshot)
        self.assertTrue(final["summary"]["blocking"])
        self.assertEqual(final["summary"]["event"], "COMMENT")
        self.assertEqual(final["summary"]["headline"], "1 issue needs attention")
        plan = copy.deepcopy(self.plan)
        plan["config"]["request_changes"] = True
        final = spk.finalize(agg, ver, [], plan, self.merged, self.collect, PR, self.snapshot)
        self.assertEqual(final["summary"]["event"], "REQUEST_CHANGES")

    def test_unverified_severe_is_published_but_not_blocking(self):
        final = spk.finalize(self.agg([make_finding()]), {}, [], self.plan, self.merged, self.collect, PR, self.snapshot)
        f = final["findings"][0]
        self.assertEqual(f["publication"]["status"], "published")
        self.assertEqual(f["verification"]["status"], "unverified")
        self.assertFalse(final["summary"]["blocking"])

    def test_rejections(self):
        findings = [make_finding(introduced_by_pr=False, dedupe_key="a|pre|x.py"),
                    make_finding(category="style", level="warning", dedupe_key="style|fmt|y.py"),
                    make_finding(dedupe_key="c|rej|z.py")]
        ver = {"CR-003": {"id": "CR-003", "status": "rejected", "note": "caller handles both keys"}}
        final = spk.finalize(self.agg(findings), ver, [], self.plan, self.merged, self.collect, PR, self.snapshot)
        statuses = [f["publication"]["status"] for f in final["findings"]]
        self.assertEqual(statuses, ["rejected", "rejected", "rejected"])
        self.assertEqual(final["summary"]["headline"], "No actionable issues found in the reviewed changes.")
        self.assertFalse(final["summary"]["blocking"])

    def test_budget_keeps_all_verified_severe_and_discloses_overflow(self):
        findings = []
        for i in range(3):
            findings.append(make_finding(dedupe_key=f"security|sev{i}|s{i}.py"))
        for i in range(6):
            findings.append(make_finding(level="warning", dedupe_key=f"correctness|warn{i}|w{i}.py"))
        agg = self.agg(findings)
        ver = {f"CR-00{i}": {"id": f"CR-00{i}", "status": "verified"} for i in range(1, 4)}
        plan = copy.deepcopy(self.plan)
        plan["config"]["max_published"] = 2
        final = spk.finalize(agg, ver, [], plan, self.merged, self.collect, PR, self.snapshot)
        pub = [f for f in final["findings"] if f["publication"]["status"] == "published"]
        self.assertEqual(len(pub), 3)
        self.assertTrue(all(f["level"] == "severe" for f in pub))
        self.assertEqual(final["summary"]["withheld"], 6)
        self.assertEqual(final["summary"]["counts"], {"severe": 3, "warning": 0, "question": 0})

    def test_prior_open_thread_is_not_reposted(self):
        f = make_finding(level="warning")
        thread = {"id": "T1", "is_ai_review": True, "fingerprint": spk.fingerprint_for(f), "status": "open",
                  "author_replied": False, "level": "warning", "url": "u", "path": "src/api/features.py", "line": 12}
        final = spk.finalize(self.agg([f]), {}, [thread], self.plan, self.merged, self.collect, PR, self.snapshot)
        out = final["findings"][0]
        self.assertEqual(out["publication"]["status"], "still_open")
        self.assertEqual(out["prior_state"]["state"], "still_present")
        self.assertEqual(final["summary"]["published"], 0)

    def test_reply_without_fix_keeps_finding_visible_and_severity_increase_reposts(self):
        f = make_finding(level="severe")
        thread = {"id": "T1", "is_ai_review": True, "fingerprint": spk.fingerprint_for(f), "status": "discussed",
                  "author_replied": True, "level": "warning", "url": "u", "path": "src/api/features.py", "line": 12}
        ver = {"CR-001": {"id": "CR-001", "status": "verified"}}
        final = spk.finalize(self.agg([f]), ver, [thread], self.plan, self.merged, self.collect, PR, self.snapshot)
        out = final["findings"][0]
        self.assertEqual(out["publication"]["status"], "published")
        self.assertTrue(out["prior_state"]["severity_increased"])

    def test_resolved_thread_with_author_reply_is_accepted_risk_for_warning(self):
        f = make_finding(level="warning")
        thread = {"id": "T1", "is_ai_review": True, "fingerprint": spk.fingerprint_for(f), "status": "resolved",
                  "author_replied": True, "level": "warning", "url": "u", "path": "x", "line": 1}
        ver = {"CR-001": {"id": "CR-001", "status": "verified"}}
        final = spk.finalize(self.agg([f]), ver, [thread], self.plan, self.merged, self.collect, PR, self.snapshot)
        self.assertEqual(final["findings"][0]["publication"]["status"], "accepted_risk")

    def test_resolved_severe_still_present_is_reopened(self):
        f = make_finding(level="severe")
        thread = {"id": "T1", "is_ai_review": True, "fingerprint": spk.fingerprint_for(f), "status": "resolved",
                  "author_replied": False, "level": "severe", "url": "u", "path": "x", "line": 1}
        ver = {"CR-001": {"id": "CR-001", "status": "verified"}}
        final = spk.finalize(self.agg([f]), ver, [thread], self.plan, self.merged, self.collect, PR, self.snapshot)
        self.assertEqual(final["findings"][0]["prior_state"]["state"], "reopened")
        self.assertEqual(final["findings"][0]["publication"]["status"], "published")

    def test_prior_thread_not_redetected_reported_as_not_found(self):
        thread = {"id": "T9", "is_ai_review": True, "fingerprint": "x|y|z.py", "status": "open",
                  "author_replied": False, "level": "warning", "url": "u", "path": "z.py", "line": 1, "cr_id": "CR-004"}
        final = spk.finalize(self.agg([]), {}, [thread], self.plan, self.merged, self.collect, PR, self.snapshot)
        self.assertEqual(final["prior_findings"][0]["state"], "not_found")

    def test_failed_agent_makes_coverage_incomplete_even_with_no_findings(self):
        merged = copy.deepcopy(self.merged)
        merged["agents"]["spk-reviewer-frontend"] = {"status": "failed", "reviewed": [], "partial": [], "skipped": [],
                                                      "not_reported": ["web/src/Map.tsx"], "findings": 0, "errors": ["invalid JSON"]}
        final = spk.finalize(self.agg([]), {}, [], self.plan, merged, self.collect, PR, self.snapshot)
        self.assertFalse(final["summary"]["coverage_complete"])
        self.assertTrue(any("failed" in n for n in final["summary"]["coverage_notes"]))

    def test_primary_not_reporting_a_file_makes_coverage_incomplete(self):
        merged = copy.deepcopy(self.merged)
        merged["agents"][spk.PRIMARY]["reviewed"] = ["src/api/features.py"]
        merged["agents"][spk.PRIMARY]["not_reported"] = ["web/src/Map.tsx"]
        merged["agents"][spk.PRIMARY]["status"] = "partial"
        final = spk.finalize(self.agg([]), {}, [], self.plan, merged, self.collect, PR, self.snapshot)
        self.assertFalse(final["summary"]["coverage_complete"])
        self.assertEqual(final["summary"]["files_reviewed"], 1)


class RenderTests(unittest.TestCase):
    def build(self, findings, verifications=None, config=None):
        files = [{"path": "src/api/features.py", "status": "M"}, {"path": "web/src/Map.tsx", "status": "M"}]
        plan = make_plan(files, config)
        merged = {"agents": {a["name"]: {"status": "ok", "reviewed": a["files"], "partial": [], "skipped": [],
                                          "not_reported": [], "findings": 0} for a in plan["agents"]}}
        for i, f in enumerate(findings, 1):
            f["id"] = f"CR-{i:03d}"
            f.setdefault("found_by", [spk.PRIMARY])
        final = spk.finalize({"version": "2.0", "findings": findings}, verifications or {}, [], plan, merged,
                             {"warnings": [], "files_count_match": True, "head_consistent": True}, PR,
                             {"method": "worktree", "verified": True})
        body, inline = spk.build_review(final, spk.parse_unified_diff(DIFF), ".reviews/pr7/run1")
        return final, body, inline

    def test_inline_anchor_in_diff_and_explanation_posted_once(self):
        f = make_finding(fix_caveat="Deploy the client first.")
        final, body, inline = self.build([f], {"CR-001": {"id": "CR-001", "status": "verified"}})
        self.assertEqual(len(inline), 1)
        c = inline[0]
        self.assertEqual((c["path"], c["line"], c["side"]), ("src/api/features.py", 12, "RIGHT"))
        self.assertNotIn("start_line", c)
        self.assertIn("<!-- spk-finding: api_contract|response_rename_items|src/api/features.py -->", c["body"])
        self.assertIn("> Deploy the client first.", c["body"])
        self.assertNotIn("confidence", c["body"])
        self.assertNotIn("Found by", c["body"])
        self.assertIn("**1 issue needs attention**", body)
        self.assertIn("- [ ] **The response rename breaks the map client** (severe) · see the comment at", body)
        self.assertNotIn("The map renders no results.", body)   # explanation lives inline only
        self.assertIn("Reviewed 2 of 2 files at aaaaaaa. No coverage gaps.", body)
        self.assertIn("<!-- spk-review run=run1 head=" + "a" * 40 + " -->", body)

    def test_out_of_diff_finding_folds_into_body_checklist(self):
        f = make_finding(location={"file_path": "src/api/features.py", "side": "new", "start_line": 30, "end_line": 30})
        final, body, inline = self.build([f])
        self.assertEqual(inline, [])
        self.assertIn("The map renders no results.", body)
        self.assertIn("`src/api/features.py:30` · CR-001", body)

    def test_old_side_anchor_for_deleted_line(self):
        f = make_finding(location={"file_path": "src/api/features.py", "side": "old", "start_line": 12, "end_line": 12})
        _, _, inline = self.build([f])
        self.assertEqual(inline[0]["side"], "LEFT")

    def test_multi_line_anchor(self):
        f = make_finding(location={"file_path": "src/api/features.py", "side": "new", "start_line": 41, "end_line": 43})
        _, _, inline = self.build([f])
        self.assertEqual(inline[0]["start_line"], 41)
        self.assertEqual(inline[0]["start_side"], "RIGHT")

    def test_cross_file_finding_rendered_as_checklist_with_paths(self):
        f = make_finding(type="diff_comment", cross_cutting=True,
                         applies_to={"file_paths": ["src/api/features.py", "web/src/Map.tsx"]})
        f.pop("location")
        _, body, inline = self.build([f])
        self.assertEqual(inline, [])
        self.assertIn("- [ ] **The response rename breaks the map client** (severe)", body)
        self.assertIn("`src/api/features.py`, `web/src/Map.tsx` · CR-001", body)

    def test_overflow_listed_in_details_and_unverified_severe_disclosed(self):
        findings = [make_finding(dedupe_key="security|sev|s.py")]
        for i in range(7):
            findings.append(make_finding(level="warning", dedupe_key=f"correctness|w{i}|w{i}.py",
                                         location={"file_path": "src/api/features.py", "side": "new", "start_line": 11, "end_line": 11}))
        final, body, inline = self.build(findings)
        self.assertIn("could not be independently verified", body)
        self.assertIn("**Not shown (3 lower-priority finding(s))**", body)
        self.assertEqual(final["summary"]["published"], 5)

    def test_clean_review_text(self):
        _, body, inline = self.build([])
        self.assertIn("No actionable issues found in the reviewed changes.", body)
        self.assertEqual(inline, [])

    def test_body_limit_drops_details_not_findings(self):
        f = make_finding(type="diff_comment", applies_to={"file_paths": ["src/api/features.py"]})
        f.pop("location")
        final, body, inline = self.build([f])
        final["summary"]["coverage_notes"] = ["x" * 2000] * 40
        body, _ = spk.build_review(final, spk.parse_unified_diff(DIFF), "r")
        self.assertLessEqual(len(body), spk.BODY_LIMIT)
        self.assertIn("The response rename breaks the map client", body)
        self.assertIn("Details omitted", body)


if __name__ == "__main__":
    unittest.main()
