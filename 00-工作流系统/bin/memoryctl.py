#!/usr/bin/env python3
"""CLI for proposing, reviewing, querying, and exporting jobflow memory."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from jobflow_memory import AUTHOR_TYPES, MEMORY_STATES, MEMORY_TYPES, SENSITIVITY, MemoryStore


SYSTEM_DIR = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Canonical jobflow long-term memory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    listing = sub.add_parser("list")
    listing.add_argument("--status", choices=sorted(MEMORY_STATES))
    listing.add_argument("--scope")
    listing.add_argument("--type", dest="memory_type", choices=sorted(MEMORY_TYPES))
    listing.add_argument("--query")
    context = sub.add_parser("context")
    context.add_argument("--scope", action="append", default=[])
    context.add_argument("--query")
    context.add_argument("--max-items", type=int, default=20)
    context.add_argument("--max-chars", type=int, default=12_000)
    propose = sub.add_parser("propose")
    propose.add_argument("--type", dest="memory_type", required=True, choices=sorted(MEMORY_TYPES))
    propose.add_argument("--scope", required=True)
    propose.add_argument("--subject", required=True)
    propose.add_argument("--statement", required=True)
    propose.add_argument("--source", action="append", required=True)
    propose.add_argument("--author-type", required=True, choices=sorted(AUTHOR_TYPES))
    propose.add_argument("--author-id", required=True)
    propose.add_argument("--evidence-strength", required=True)
    propose.add_argument("--tag", action="append", default=[])
    propose.add_argument("--sensitivity", default="internal", choices=sorted(SENSITIVITY))
    propose.add_argument("--valid-until")
    propose.add_argument("--supersedes", action="append", default=[])
    propose.add_argument("--expected-revision", type=int)
    decide = sub.add_parser("decide")
    decide.add_argument("--memory-id", required=True)
    decide.add_argument("--decision", required=True, choices=["accepted", "rejected"])
    decide.add_argument("--reviewer-type", required=True, choices=["human", "agent"])
    decide.add_argument("--reviewer-id", required=True)
    decide.add_argument("--note", required=True)
    decide.add_argument("--expected-revision", type=int)
    return parser


def refresh_generated() -> None:
    subprocess.run(
        [sys.executable, str(SYSTEM_DIR / "bin" / "jobflow.py"), "brief", "--write"],
        cwd=SYSTEM_DIR.parent,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = MemoryStore(SYSTEM_DIR)
    try:
        if args.command == "validate":
            errors = store.validate()
            for error in errors:
                print(f"ERROR: {error}")
            if errors:
                return 1
            document = store.load()
            print(f"OK: memory revision={document['revision']} items={len(document['items'])}")
            return 0
        if args.command == "list":
            print(
                json.dumps(
                    {
                        "revision": store.load().get("revision"),
                        "items": store.list_items(
                            status=args.status,
                            scope=args.scope,
                            memory_type=args.memory_type,
                            query=args.query,
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.command == "context":
            print(
                store.context(
                    scopes=args.scope or ["job_search"],
                    query=args.query,
                    max_items=args.max_items,
                    max_chars=args.max_chars,
                ),
                end="",
            )
            return 0
        if args.command == "propose":
            item = store.propose(
                memory_type=args.memory_type,
                scope=args.scope,
                subject=args.subject,
                statement=args.statement,
                source_refs=args.source,
                author_type=args.author_type,
                author_id=args.author_id,
                evidence_strength=args.evidence_strength,
                tags=args.tag,
                sensitivity=args.sensitivity,
                valid_until=args.valid_until,
                supersedes=args.supersedes,
                expected_revision=args.expected_revision,
            )
            refresh_generated()
            print(json.dumps(item, ensure_ascii=False, indent=2))
            return 0
        if args.command == "decide":
            item = store.decide(
                args.memory_id,
                args.decision,
                reviewer_type=args.reviewer_type,
                reviewer_id=args.reviewer_id,
                note=args.note,
                expected_revision=args.expected_revision,
            )
            refresh_generated()
            print(json.dumps(item, ensure_ascii=False, indent=2))
            return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
