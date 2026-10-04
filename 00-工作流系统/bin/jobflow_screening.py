#!/usr/bin/env python3
"""Deterministic evidence-bounded screening, not an offer probability or approval.

No network, dependencies, identity loading, state mutation, or inferred job facts.
Assessment values are reviewer judgments; the engine enforces their bookkeeping.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jobflow_profile import ProfileError, load_goals

POLICY_VERSION = "screening-v1"


class ScreeningError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScreeningError(message)


def _object(value: object, allowed: set[str], required: set[str], label: str) -> dict:
    _require(isinstance(value, dict), f"{label} must be an object")
    _require(required <= value.keys() <= allowed, f"{label} has missing or unsupported fields")
    return value


def _string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: object, low: float, high: float) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def validate_goals(goals: dict) -> None:
    _object(goals, {"schema_version", "dimensions", "hard_rules", "thresholds", "foreign_first"},
            {"schema_version", "dimensions", "hard_rules", "thresholds", "foreign_first"}, "goals")
    _require(type(goals["schema_version"]) is int and goals["schema_version"] == 1, "Unsupported goals version")
    _require(type(goals["foreign_first"]) is bool, "foreign_first must be boolean")
    dimensions = goals["dimensions"]
    _require(isinstance(dimensions, dict) and bool(dimensions), "dimensions must be nonempty")
    for key, item in dimensions.items():
        _require(_string(key), "Dimension ID must be nonempty")
        _object(item, {"label", "weight", "rubric"}, {"label", "weight", "rubric"}, "dimension")
        _require(_string(item["label"]) and _string(item["rubric"]), "Dimension needs label and rubric")
        _require(_number(item["weight"], 0, 100) and item["weight"] > 0, "Weight must be positive and <=100")
    _require(math.isclose(sum(d["weight"] for d in dimensions.values()), 100, abs_tol=1e-9, rel_tol=0),
             "Dimension weights must sum to 100")
    rules = goals["hard_rules"]
    _require(isinstance(rules, dict) and bool(rules), "hard_rules must be nonempty")
    _require(all(_string(k) and _string(v) for k, v in rules.items()), "Hard rules need nonempty IDs and descriptions")
    thresholds = _object(goals["thresholds"], {"reject_below", "recommend_at", "minimum_coverage"},
                         {"reject_below", "recommend_at", "minimum_coverage"}, "thresholds")
    _require(all(_number(v, 0, 100) for v in thresholds.values()), "Thresholds must be in 0..100")
    _require(thresholds["reject_below"] <= thresholds["recommend_at"], "Reject threshold exceeds recommend threshold")


def goal_config_sha256(goals: dict) -> str:
    """Hash validated UTF-8 JSON with sorted keys, compact separators, no NaN."""
    validate_goals(goals)
    canonical = json.dumps(goals, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def profile_summary(goals: dict) -> dict:
    """Operational summary only: never echo identity, rubrics or hard-rule text."""
    config_hash = goal_config_sha256(goals)
    return {"valid": True, "policy_version": POLICY_VERSION, "goal_config_sha256": config_hash,
            "dimension_weights": {key: item["weight"] for key, item in goals["dimensions"].items()},
            "total_weight": sum(item["weight"] for item in goals["dimensions"].values()),
            "hard_rule_count": len(goals["hard_rules"]), "foreign_first": goals["foreign_first"]}


def _refs(value: object, evidence: dict) -> list[str]:
    _require(isinstance(value, list) and all(_string(r) for r in value), "evidence_refs must be a string list")
    _require(len(set(value)) == len(value), "Duplicate evidence reference")
    _require(all(r in evidence for r in value), "Unresolved evidence reference")
    return value


def _validate_evidence(evidence: object, *, now: datetime) -> dict:
    _require(isinstance(evidence, dict), "evidence must be an object")
    for key, item in evidence.items():
        _require(_string(key), "Evidence ID must be nonempty")
        _object(item, {"source", "observed_at", "note"}, {"source", "observed_at", "note"}, "evidence item")
        _require(all(_string(value) for value in item.values()), "Evidence requires source, observed_at, note")
        try:
            observed = datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00"))
        except ValueError:
            raise ScreeningError("Evidence observed_at must be ISO 8601") from None
        _require(observed.tzinfo is not None, "Evidence timestamp requires timezone")
        _require(observed <= now + timedelta(minutes=5), "Evidence observed_at is in the future (over five minutes)")
    return evidence


def _ownership(item: dict, evidence: dict) -> tuple[bool, str, list[str]]:
    _object(item, {"status", "legal_entity", "ultimate_parent", "parent_jurisdiction", "control_chain"},
            {"status"}, "ownership")
    _require(item["status"] in ("verified_foreign", "verified_domestic", "unknown"), "Invalid ownership status")
    chain = item.get("control_chain", [])
    _require(isinstance(chain, list), "control_chain must be a list")
    refs = []
    previous = item.get("legal_entity")
    complete = bool(chain) and all(_string(item.get(k)) for k in ("legal_entity", "ultimate_parent", "parent_jurisdiction"))
    seen = {previous} if _string(previous) else set()
    for edge in chain:
        _object(edge, {"entity", "controller", "control_basis", "share_percent", "evidence_refs"},
                {"entity", "controller", "control_basis", "evidence_refs"}, "control edge")
        _require(all(_string(edge[k]) for k in ("entity", "controller", "control_basis")), "Control edge text is missing")
        if "share_percent" in edge:
            _require(_number(edge["share_percent"], 0, 100), "share_percent must be in 0..100")
        edge_refs = _refs(edge["evidence_refs"], evidence)
        complete = complete and bool(edge_refs) and previous == edge["entity"] and edge["controller"] not in seen
        refs.extend(edge_refs)
        previous = edge["controller"]
        seen.add(previous)
    complete = complete and previous == item.get("ultimate_parent")
    verified = bool(complete and item["status"] != "unknown")
    status = item["status"] if verified else "unknown"
    return status == "verified_foreign", status, sorted(set(refs)) if verified else []


def score_assessment(assessment: dict, goals: dict, *, now: datetime | None = None) -> dict:
    """Return a JSON-ready result; missing observations remain unknown.

    Lower = sum(weight * supported value). Upper = lower + unknown weights.
    Evidence coverage measures supported dimension weights, not source credibility.
    """
    validate_goals(goals)
    now = datetime.now(timezone.utc) if now is None else now
    _require(isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None,
             "now must be a timezone-aware datetime")
    _object(assessment, {"schema_version", "candidate_id", "evidence", "dimensions", "hard_rules", "ownership", "employment"},
            {"schema_version", "candidate_id", "evidence", "dimensions", "hard_rules"}, "assessment")
    _require(type(assessment["schema_version"]) is int and assessment["schema_version"] == 1, "Unsupported assessment version")
    _require(_string(assessment["candidate_id"]), "candidate_id must be nonempty")
    evidence = _validate_evidence(assessment["evidence"], now=now)
    for section in ("dimensions", "hard_rules"):
        _require(isinstance(assessment[section], dict), f"{section} must be an object")
        _require(assessment[section].keys() <= goals[section].keys(), f"Unknown {section} ID")

    hard_results = {}
    for key in goals["hard_rules"]:
        item = assessment["hard_rules"].get(key, {"status": "unknown", "reason": "未取得证据", "evidence_refs": []})
        _object(item, {"status", "reason", "evidence_refs"}, {"status", "reason", "evidence_refs"}, "hard rule")
        _require(item["status"] in ("pass", "fail", "unknown") and _string(item["reason"]), "Invalid hard rule")
        refs = _refs(item["evidence_refs"], evidence)
        status = item["status"] if refs else "unknown"
        hard_results[key] = {"status": status, "reason": item["reason"], "evidence_refs": refs}
        if item["status"] != "unknown" and not refs:
            hard_results[key]["reason"] = "缺少证据，原判断未采信：" + item["reason"]
    states = [h["status"] for h in hard_results.values()]
    gate = "fail" if "fail" in states else "unknown" if "unknown" in states else "pass"

    lower = coverage = 0.0
    details = {}
    for key, dimension in goals["dimensions"].items():
        item = assessment["dimensions"].get(key, {"value": None, "reason": "未取得证据", "evidence_refs": []})
        _object(item, {"value", "reason", "evidence_refs"}, {"value", "reason", "evidence_refs"}, "dimension assessment")
        _require(item["value"] is None or _number(item["value"], 0, 1), "Dimension value must be null or in 0..1")
        _require(_string(item["reason"]), "Dimension reason is missing")
        refs = _refs(item["evidence_refs"], evidence)
        supported = item["value"] is not None and bool(refs)
        points = dimension["weight"] * item["value"] if supported else 0.0
        lower += points
        coverage += dimension["weight"] if supported else 0.0
        details[key] = {"label": dimension["label"], "weight": dimension["weight"],
                        "value": item["value"] if supported else None, "supported": supported,
                        "points": round(points, 4), "reason": item["reason"], "evidence_refs": refs}
    upper = min(100.0, lower + (100.0 - coverage))
    threshold = goals["thresholds"]
    if gate == "fail":
        decision, reason = "不推荐", "已命中硬线，任何维度得分都不能抵消"
    elif upper < threshold["reject_below"]:
        decision, reason = "不推荐", "即使未知项全部满足，仍低于最低匹配门槛"
    elif gate == "unknown":
        decision, reason = "待核实", "硬线尚有未知项"
    elif coverage < threshold["minimum_coverage"]:
        decision, reason = "待核实", "证据覆盖率不足"
    elif lower < threshold["recommend_at"]:
        decision, reason = "待核实", "有证据支持的匹配分尚未达到推荐门槛"
    else:
        decision, reason = "推荐", "硬线全部通过，证据覆盖与最低匹配分达到门槛"

    foreign, ownership_status, ownership_refs = _ownership(assessment.get("ownership", {"status": "unknown"}), evidence)
    tags = ["真外企"] if foreign else ["内资"] if ownership_status == "verified_domestic" else ["所有制待核实"]
    employment = assessment.get("employment", {"kind": "unknown", "evidence_refs": []})
    _object(employment, {"kind", "evidence_refs"}, {"kind", "evidence_refs"}, "employment")
    _require(employment["kind"] in ("own_product", "outsourcing_delivery", "unknown"), "Invalid employment kind")
    employment_refs = _refs(employment["evidence_refs"], evidence)
    kind = employment["kind"] if employment_refs else "unknown"
    tags.append({"own_product": "自研产品", "outsourcing_delivery": "外包·交付", "unknown": "用工未核实"}[kind])

    # Sort ascending: decision class first, then verified foreign ownership,
    # then the conservative score and coverage. Failures never outrank passes.
    sort_key = [{"推荐": 0, "待核实": 1, "不推荐": 2}[decision],
                0 if foreign or not goals["foreign_first"] else 1, -round(lower, 4), -round(coverage, 4), assessment["candidate_id"]]
    return {"schema_version": 1, "policy_version": POLICY_VERSION,
            "goal_config_sha256": goal_config_sha256(goals),
            "candidate_id": assessment["candidate_id"], "gate": gate,
            "decision": decision, "decision_reason": reason,
            "score_lower": round(lower, 4), "score_upper": round(upper, 4),
            "evidence_coverage_percent": round(coverage, 4),
            "hard_rules": hard_results, "dimensions": details, "tags": tags,
            "ownership_status": ownership_status, "ownership_evidence_refs": ownership_refs,
            "employment_kind": kind, "employment_evidence_refs": employment_refs,
            "sort_key": sort_key,
            "limitations": ["匹配分不是录用概率，也不是投递或发送授权", "证据引用有据可查不代表已由程序验证真实、充分或时效性", "最低分与上限表示当前证据范围，不是统计置信区间"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", type=Path, nargs="?", help="Candidate assessment JSON (required for scoring)")
    parser.add_argument("--goals", type=Path, help="Explicit goals JSON (examples allowed); default uses external profile")
    parser.add_argument("--validate-profile", action="store_true", help="Validate goals only and print a non-sensitive summary")
    args = parser.parse_args(argv)
    if not args.validate_profile and args.assessment is None:
        parser.error("assessment is required unless --validate-profile is used")
    if args.validate_profile and args.assessment is not None:
        parser.error("--validate-profile does not take an assessment")
    try:
        goals = json.loads(args.goals.read_text(encoding="utf-8")) if args.goals else load_goals()
        if args.validate_profile:
            result = profile_summary(goals)
        else:
            assessment = json.loads(args.assessment.read_text(encoding="utf-8"))
            result = score_assessment(assessment, goals)
    except (OSError, UnicodeError, json.JSONDecodeError):
        print("Screening input is unreadable or invalid JSON", file=sys.stderr)
        return 2
    except (ScreeningError, ProfileError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
