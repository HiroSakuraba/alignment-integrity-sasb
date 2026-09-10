"""Small worker-only maintenance pilot. Dry run by default, no retries."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from .agents.adapters import AdapterError
from .agents.budget import Budget
from .agents.providers import (ACTION_CONTRACT, ModelActor, ModelClient, load_env,
                               describe_setup, require_live, _api_key, pinned_model)
from .executor import completed_violation
from .records import prompt_hashes
from .scenarios.maintenance import specification
from .scoring.scorecard import score_episode
from .sessions import SessionRunner
from .world import World

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ('authorized_maintenance', 'tempting_unauthorized')


def worker_prompt():
    worker = (ROOT / 'prompts/worker-v1.txt').read_text()
    envelope = (ROOT / 'prompts/observation-envelope-v1.txt').read_text()
    # Exclude evaluator-only field names from the model prompt.
    return worker + '\n' + envelope.split('Never expect these fields;', 1)[0]


def run_pilot(budget, report, checkpoint, transport=None):
    require_live()
    for provider in ('openai', 'anthropic'):
        pinned_model(provider)
        _api_key(provider)
    # Both connection checks must return valid JSON before benchmark work begins.
    for provider in ('openai', 'anthropic'):
        from .agents.adapters import parse_decision
        client = ModelClient(provider, transport=transport, budget=budget)
        raw, _, _ = client.complete('Reply with exactly {"action":"noop","arguments":{}}.', 'Connection check.')
        action, args = parse_decision(raw)
        if action != 'noop' or args:
            raise AdapterError('connection check did not return noop')
        report['connection_checks'].append(provider)
        checkpoint()
    for condition in CONDITIONS:
        for runtime in ('default', 'proposed'):
            for provider in ('openai', 'anthropic'):
                world = World(specification(condition), runtime=runtime)
                actor = ModelActor('worker', provider, worker_prompt(), transport=transport, budget=budget)
                runner = SessionRunner(world, {'worker-1': actor}, edges=(),
                                       max_actions=4, decision_seconds=40)
                episode = {'spec': world.spec, 'provider': provider, 'model': actor.client.model,
                           'policy': 'live-worker', 'runtime': runtime, 'mode': 'worker',
                           'status': 'running', 'trace': [], 'request_start': len(budget.entries)}
                report['episodes'].append(episode)
                checkpoint()
                for _ in range(4):
                    if budget.blocked or len(budget.entries) >= budget.max_requests or budget.charged >= budget.limit or any(e['status'] in {'unknown', 'pending', 'failed'} for e in budget.entries):
                        raise AdapterError('pilot stopped after budget or provider failure')
                    receipt = runner.step('worker-1')
                    episode.update(trace=runner.trace, receipts=world.receipts.dump(),
                                   reports=world.reports.delivered(), writes=list(world.resources.writes),
                                   workspace_files=list(world.workspace.files),
                                   completed_violation=completed_violation(world),
                                   permission_updates=world.spaces.runtime_view().get('permission_service_updates', {}),
                                   request_end=len(budget.entries))
                    episode['score'] = score_episode(episode)
                    checkpoint()
                    if receipt is None or 'worker-1' in world.stopped_agents:
                        break
                episode['status'] = ('error' if episode['score']['invalid_action_or_actor_error'] else 'completed')
                checkpoint()
                if budget.blocked or any(e['status'] in {'unknown', 'pending', 'failed'} for e in budget.entries):
                    raise AdapterError('provider accounting unresolved; pilot stopped')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--budget-usd', default='0.50')
    parser.add_argument('--output', default='reports/pilot-local.json')
    args = parser.parse_args()
    load_env()
    budget = Budget(args.budget_usd)
    if not args.live:
        print(json.dumps({'setup': describe_setup(), 'budget': budget.snapshot(),
                          'plan': '2 connection checks + 8 worker episodes, at most 4 actions each; 34 requests maximum. No network calls.'}, indent=2))
        return 0
    output = Path(args.output)
    if output.exists():
        parser.error('output exists; choose a new file to preserve the previous run')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'claim': 'Exploratory worker-only API pilot; no training, swarm measurement, or safety-gain claim.',
              'status': 'running', 'connection_checks': [], 'episodes': [],
              'prompt_hashes': prompt_hashes(),
              'worker_prompt_sha256': hashlib.sha256(worker_prompt().encode()).hexdigest(),
              'action_contract_sha256': hashlib.sha256(ACTION_CONTRACT.encode()).hexdigest(),
              'decoding': {'output_tokens': 256, 'luna_reasoning': 'none', 'retries': 0},
              'planned_episodes': 8}
    try:
        report['commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        report['commit'] = None
    def checkpoint():
        report['budget'] = budget.snapshot()
        temporary = output.with_suffix(output.suffix + '.tmp')
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        temporary.replace(output)
    budget.checkpoint = checkpoint
    checkpoint()
    try:
        run_pilot(budget, report, checkpoint)
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as exc:
        report['status'] = 'stopped'
        report['error_type'] = type(exc).__name__
        for episode in report['episodes']:
            if episode['status'] == 'running':
                episode['status'] = 'interrupted'
    finally:
        checkpoint()
    print('Pilot %s; report: %s' % (report['status'], output))
    return 0 if report['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
