import argparse
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orca_coordinator as billing


RUN = 'run_aaaaaaaaaaaa'
T1, T2 = 'task_111111111111', 'task_222222222222'
D1, D2, RETRY = 'ctx_111111111111', 'ctx_222222222222', 'ctx_333333333333'
WS = '/fixture/worker'


def assignment(task, dispatch, spec='Do the synthetic task.'):
    return ('You are working inside Orca, a multi-agent IDE. You are a dispatched worker.\n'
            f"Your coordinator's terminal handle is: term_example\nYour task ID is: {task}\n"
            f'orca orchestration send --type worker_done --task-id {task} --dispatch-id {dispatch}\n'
            f'=== TASK ===\n{spec}')


def prompt(text):
    return {'type': 'message', 'message': {'role': 'user', 'content': [{'type': 'text', 'text': text}]}}


def call(entry, cost, tokens=11):
    return {'type': 'message', 'id': entry, 'message': {'role': 'assistant', 'usage': {
        'input': tokens, 'cacheRead': 7, 'output': 3, 'cost': {'total': cost}}}}


def worker(task, dispatch, workspace=None):
    return {'taskId': task, 'dispatchId': dispatch,
            'workspace': workspace if workspace is not None else {'id': f'repo::{WS}'}}


class TestUsage(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.pi = self.root / 'pi' / billing.norm_slug(WS)
        self.codex = self.root / 'codex'
        self.coordinator = self.root / 'coordinator.jsonl'
        self.home = self.root / 'billing'
        env = patch.multiple(billing, HOME=str(self.home), PI_SESSIONS=str(self.pi.parent),
                             CODEX_SESSIONS=str(self.codex))
        env.start()
        self.addCleanup(env.stop)

    def session(self, path, events, start=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with path.open('w', encoding='utf-8') as f:
            for i, event in enumerate(events, start):
                ts = (origin + timedelta(seconds=i)).isoformat().replace('+00:00', 'Z')
                f.write(json.dumps(dict(event, timestamp=ts)) + '\n')

    def bill(self, workers):
        args = argparse.Namespace(run_id=RUN, objective='fixture', coordinator_session=str(self.coordinator))
        with patch.object(billing, 'run_orca_json', return_value={'result': {'workers': workers}}), redirect_stdout(io.StringIO()):
            billing.cmd_usage(args)
        return json.loads((self.home / 'bills' / f'{RUN}.json').read_text(encoding='utf-8'))

    def test_failed_injection_replay(self):
        # Public case aggregates, synthetic events. The missing attempt and retry share a task, not a call.
        self.session(self.pi / 'retry.jsonl', [prompt(assignment(T1, RETRY))]
                     + [call(f'event-{i}', .41) for i in range(178)] + [call('event-last', .61)], start=5)
        self.session(self.pi / 'other.jsonl', [prompt(assignment(T2, D2)), call('other', 45.765)], start=5)
        self.session(self.coordinator, [prompt(RUN), call('coordinator', 43.939)])
        report = self.bill([worker(T1, D1), worker(T1, RETRY), worker(T2, D2)])
        by_id = {row['dispatch']: row for row in report['workers']}
        self.assertEqual(report['totals']['cost'], 163.294)
        self.assertEqual((report['totals']['calls'], report['totals']['input']), (181, 181 * 11))
        self.assertEqual((by_id[RETRY]['calls'], by_id[RETRY]['cost']), (179, 73.59))
        self.assertIsNone(by_id[D1]['cost'])
        self.assertEqual(by_id[D1]['attribution'], 'unknown')

    def test_reused_terminal_equal_costs_and_duplicate_observation(self):
        self.session(self.pi / 'shared.jsonl', [prompt(assignment(T1, D1)), call('first', 2),
                     prompt(f'Compare with {D2} and {T2}; this is not an assignment.'), call('second', 2),
                     prompt(assignment(T2, D2)), call('third', 2)])
        first, second = worker(T1, D1, f'repo::{WS}'), worker(T2, D2, f'repo::{WS}')
        for rows in ([first, second, first], [second, first]):
            report = self.bill(rows)
            self.assertEqual({r['dispatch']: r['calls'] for r in report['workers']}, {D1: 2, D2: 1})
            self.assertEqual((report['totals']['calls'], report['totals']['cost']), (3, 6))
        self.assertEqual(len((self.home / 'bills' / 'bills.jsonl').read_text().splitlines()), 1)

    def test_weak_mentions_and_ambiguous_sessions_are_not_charged(self):
        text = assignment(T1, D1)
        self.session(self.pi / 'a.jsonl', [prompt(text), call('a', 1)])
        self.session(self.pi / 'b.jsonl', [prompt(text), call('b', 2)])
        self.session(self.pi / 'other.jsonl', [prompt(f'Please discuss {T2} {D2}'), call('other', 4),
                     {'type': 'message', 'message': {'role': 'toolResult', 'content': assignment(T2, D2)}}])
        self.session(self.coordinator, [prompt('unrelated conversation'), call('not-ours', 10)])
        report = self.bill([worker(T1, D1), worker(T2, D2)])
        self.assertEqual(report['totals']['calls'], 0)
        self.assertIsNone(report['coordinator'])
        self.assertTrue(all(r['attribution'] == 'unknown' and r['cost'] is None for r in report['workers']))

    def test_real_retry_in_same_session_keeps_both_attempts(self):
        first = worker(T1, D1)
        first['outcome'] = 'failed'  # Failure after a real call is not a free/no-injection attempt.
        self.session(self.pi / 'retry.jsonl', [
            prompt(assignment(T1, D1)), call('before-failure', 3),
            prompt(assignment(T1, RETRY, spec=assignment(T2, D2))), call('after-retry', 3)])
        report = self.bill([first, worker(T1, RETRY), worker(T2, D2)])
        self.assertEqual([r['cost'] for r in report['workers']], [3, 3, None])
        self.assertEqual(report['totals']['calls'], 2)

    def test_incomplete_assignment_stops_billing_and_unrelated_coordinator_is_excluded(self):
        self.session(self.pi / 'interrupted.jsonl', [prompt(assignment(T1, D1)), call('proven', 1),
                     prompt('You are working inside Orca, a multi-agent IDE.\\nYour task ID is: ' + T1),
                     call('unowned', 16)])
        self.session(self.coordinator, [prompt('a different run'), call('unrelated', 4)])
        report = self.bill([worker(T1, D1)])
        self.assertEqual(report['totals']['cost'], 1)
        self.assertIsNone(report['coordinator'])

    def test_codex_pasted_assignment_ends_at_next_dispatch_even_outside_run(self):
        def codex_user(text):
            return {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                    'content': [{'type': 'input_text', 'text': text}]}}

        def codex_call(rid):
            return {'type': 'token_usage_record', 'payload': {'response_id': rid, 'usage': {
                'input_tokens': 20, 'cached_input_tokens': 10, 'output_tokens': 9}}}

        prefix = 'Please carry out this task from my Orca coordinator by following the brief I pasted below.\n'
        self.session(self.codex / '2026' / 'rollout.jsonl', [
            codex_user(prefix + '<pasted_content>\n' + assignment(T1, D1) + '\n</pasted_content>'),
            codex_call('one'), codex_call('one'), codex_call('two'),
            codex_user(assignment(T2, D2)), codex_call('outside')])
        report = self.bill([worker(T1, D1)])
        row = report['workers'][0]
        self.assertEqual((row['calls'], row['input'], row['cacheRead'], row['output'], row['hit']),
                         (2, 40, 20, 18, 50.0))
        self.assertIsNone(row['cost'])


if __name__ == '__main__':
    unittest.main()
