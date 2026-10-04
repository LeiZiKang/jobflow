#!/usr/bin/env python3
"""Record reviewed evidence assessments under the existing Decider write guard."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from jobflow import JobflowRepo, _atomic_write_json
from jobflow_profile import load_goals
from jobflow_screening import score_assessment
from jobflow_writes import mutation


@mutation
def record(repo, assessment, source, actor):
    goals = load_goals()
    result = score_assessment(assessment, goals)
    ids = {c['candidate_id'] for c in repo.load('candidates.json')['candidates']}
    for path in (repo.repo_root / '05-检索报告/每日岗位检索').glob('*.candidates.json'):
        ids.update(c['candidate_id'] for c in json.loads(path.read_text())['candidates'])
    if assessment['candidate_id'] not in ids:
        raise ValueError('assessment candidate must already exist in the candidate catalog')
    path = repo.state_dir / 'screening.json'
    doc = json.loads(path.read_text()) if path.exists() else {'schema_version': 1, 'assessments': []}
    doc['assessments'] = [a for a in doc['assessments'] if a['candidate_id'] != assessment['candidate_id']] + [assessment]
    doc['updated_at'] = datetime.now(timezone.utc).isoformat()
    doc['policy_version'] = result['policy_version']
    doc['goal_config_sha256'] = result['goal_config_sha256']
    _atomic_write_json(path, doc)
    repo.record_event('candidate_screening_recorded', f"Evidence-based screening: {assessment['candidate_id']} ({result['decision']}); no approval or application changed.", actor, [assessment['candidate_id']], [str(source)])
    repo.write_generated()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--actor', default='active-decider')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding='utf-8'))
        result = score_assessment(data, load_goals()) if args.dry_run else record(JobflowRepo(), data, args.input, args.actor)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
