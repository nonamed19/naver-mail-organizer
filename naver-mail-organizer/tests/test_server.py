import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).parents[1] / 'server/server.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def mail(uid, flagged=False, seen=True):
    return {'raw': f'From: sender@example.org\r\nTo: recipient@example.org\r\nSubject: Test {uid}\r\nDate: Fri, 23 Oct 2026 01:00:00 +0000\r\nMessage-ID: <test-{uid}@example.org>\r\n\r\nhello'.encode(),
            'flags': (['\\Seen'] if seen else []) + (['\\Flagged'] if flagged else [])}


class Fake:
    capabilities = (b'IMAP4rev1', b'MOVE')

    def __init__(self, count=3):
        self.boxes = {'INBOX': {str(i): mail(i, flagged=i % 2 == 1) for i in range(1, count + 1)}, 'Work': {}, 'Other': {}}
        self.validity = {'INBOX': '42', 'Work': '84', 'Other': '85'}
        self.next_uid = {'INBOX': count + 1, 'Work': 100, 'Other': 200}
        self.calls = []
        self.selected = 'INBOX'
        self.responses = {}
        self.emit_copyuid = True
        self.mode = 'normal'
        self.logouts = 0

    def list(self):
        self.calls.append(('LIST',))
        return 'OK', [b'(\\HasNoChildren) "/" "Work"', b'(\\HasNoChildren) "/" "Other"', b'(\\Sent) "/" "Sent"', b'(\\HasNoChildren) "/" "INBOX"']

    def noop(self):
        self.calls.append(('NOOP',))
        return 'OK', [b'alive']

    def select(self, folder, readonly=True):
        self.selected = s.decode_folder(folder.strip('"'))
        self.calls.append(('SELECT', self.selected, readonly))
        self.responses['UIDVALIDITY'] = [self.validity[self.selected].encode()]
        self.responses['UIDNEXT'] = [str(self.next_uid[self.selected]).encode()]
        return 'OK', [str(len(self.boxes[self.selected])).encode()]

    def response(self, name):
        return name, self.responses.pop(name, [None])

    def uid(self, command, *args):
        self.calls.append((command, *args))
        if command == 'SEARCH':
            ids = list(self.boxes[self.selected])
            if 'SEEN' in args:
                ids = [uid for uid in ids if '\\Seen' in self.boxes[self.selected][uid]['flags']]
            if 'UNDELETED' in args:
                ids = [uid for uid in ids if '\\Deleted' not in self.boxes[self.selected][uid]['flags']]
            if 'UID' in args:
                expr = args[args.index('UID') + 1]
                floor = int(expr.split(':')[0])
                # Simulate IMAP n:* reversing when n exceeds max.
                maximum = max(map(int, ids), default=floor)
                ids = [uid for uid in ids if int(uid) >= min(floor, maximum)]
            return 'OK', [' '.join(reversed(ids)).encode()]
        if command == 'FETCH':
            wanted, query = args
            out = []
            for uid in reversed(wanted.split(',')):
                obj = self.boxes[self.selected].get(uid)
                if obj is None:
                    continue
                flags = ' '.join(obj['flags']).encode()
                metadata = b'1 (UID ' + uid.encode() + b' FLAGS (' + flags + b') RFC822.SIZE ' + str(len(obj['raw'])).encode()
                if query == '(UID RFC822.SIZE)':
                    out.append(metadata + b')')
                else:
                    raw = obj['raw'] if 'BODY.PEEK[]' in query else obj['raw'].split(b'\r\n\r\n')[0] + b'\r\n\r\n'
                    out.append((metadata + b' BODY[] {' + str(len(raw)).encode() + b'}', raw))
                    out.append(b')')
            return 'OK', out
        if command == 'MOVE':
            uids, destination = args
            destination = s.decode_folder(destination.strip('"'))
            sources, targets = [], []
            for uid in uids.split(','):
                if self.mode == 'partial' and sources:
                    break
                if self.mode == 'noop':
                    break
                obj = self.boxes['INBOX'].pop(uid)
                target = str(self.next_uid[destination])
                self.next_uid[destination] += 1
                if self.mode == 'flags_lost':
                    obj['flags'] = []
                self.boxes[destination][target] = obj
                sources.append(uid)
                targets.append(target)
                if self.mode == 'duplicate':
                    self.boxes[destination][str(self.next_uid[destination])] = dict(obj)
                    self.next_uid[destination] += 1
            if self.emit_copyuid and sources:
                self.responses['COPYUID'] = [f"{self.validity[destination]} {','.join(sources)} {','.join(targets)}".encode()]
            if self.mode == 'disconnect':
                raise s.imaplib.IMAP4.abort('simulated socket loss')
            return ('NO' if self.mode == 'partial' else 'OK'), [b'completed']
        raise AssertionError(command)

    def logout(self):
        self.logouts += 1
        return 'BYE', [b'done']


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'NAVER_USER': 'test-owner', 'NAVER_APP_PASSWORD': 'test-password',
            'NAVER_HANDLE_KEY': 'unit-test-signing-secret', 'MCP_API_TOKEN': 'unit-test-api-token',
            'NAVER_CLASSIFICATION_FOLDERS': '["Work","Other","Sent","INBOX"]',
            'NAVER_ALLOW_MOVE': 'true', 'NAVER_AUDIT_DB': self.tmp.name + '/audit.sqlite3'})
        self.env.start()
        self.fake = Fake()
        self.pooled = s.MeasuredConnection(self.fake)

        @contextmanager
        def lease():
            self.pooled.commands = 0
            self.pooled.command_ms = {}
            yield self.pooled
        self.lease_patch = patch.object(s.POOL, 'lease', lease)
        self.lease_patch.start()

    def tearDown(self):
        self.lease_patch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def handle(self, uid=1, validity='42', kind='candidate'):
        return s.signed('INBOX' if kind == 'candidate' else 'Work', str(uid), validity, kind)

    def items(self, *uids, dest='Work'):
        return [{'handle': self.handle(uid), 'destination': dest} for uid in uids]

    def move(self, *uids, **kwargs):
        return s.dispatch('naver_move_read_inbox_batch', dict(items=self.items(*uids), dry_run=False, **kwargs))

    def commands(self, name):
        return [call for call in self.fake.calls if call[0] == name]

    def test_folder_codec_and_system_filter(self):
        for text in ['보안·계정', 'A&B', 'Work']:
            self.assertEqual(s.decode_folder(s.encode_folder(text)), text)
        self.assertEqual(s.folders(self.fake), ['Work', 'Other'])

    def test_tamper_rejected(self):
        with self.assertRaises(ValueError):
            s.unpack(self.handle()[:-1] + 'x')

    def test_header_listing_uses_one_fetch_for_100(self):
        self.fake.boxes['INBOX'] = {str(i): mail(i) for i in range(1, 101)}
        result = s.dispatch('naver_list_read_inbox', {'limit': 100})
        self.assertEqual(len(result['messages']), 100)
        self.assertEqual(len(self.commands('FETCH')), 1)
        self.assertEqual(result['next_after_uid'], 100)
        self.assertIn('BODY.PEEK[HEADER.FIELDS', self.commands('FETCH')[0][2])
        self.assertEqual(result['metrics']['imap_commands'], 4)  # LIST SELECT SEARCH FETCH

    def test_default_100_max_200_and_strict_limits(self):
        self.fake.boxes['INBOX'] = {str(i): mail(i) for i in range(1, 221)}
        self.assertEqual(len(s.dispatch('naver_list_read_inbox', {})['messages']), 100)
        self.assertEqual(len(s.dispatch('naver_list_read_inbox', {'limit': 200})['messages']), 200)
        for limit in [0, 201, True, '100']:
            with self.assertRaises(ValueError):
                s.dispatch('naver_list_read_inbox', {'limit': limit})

    def test_pagination_excludes_old_uids_in_reversed_range(self):
        result = s.dispatch('naver_list_read_inbox', {'after_uid': 999})
        self.assertEqual(result['messages'], [])
        result = s.dispatch('naver_list_read_inbox', {'limit': 1, 'after_uid': 1})
        self.assertEqual(result['next_after_uid'], 2)
        self.assertEqual(result['remaining'], 1)

    def test_body_peek_and_large_body_guard(self):
        before = list(self.fake.boxes['INBOX']['1']['flags'])
        self.assertEqual(s.dispatch('naver_read_message', {'handle': self.handle()})['body'], 'hello')
        self.assertEqual(self.fake.boxes['INBOX']['1']['flags'], before)
        self.assertIn('BODY.PEEK[]', self.commands('FETCH')[-1][2])
        with patch.dict(os.environ, {'NAVER_MAX_MESSAGE_BYTES': '10'}), self.assertRaises(ValueError):
            s.dispatch('naver_read_message', {'handle': self.handle()})

    def test_read_batch_per_item_errors(self):
        result = s.dispatch('naver_read_messages', {'handles': [self.handle(), 'bad']})
        self.assertEqual([x['status'] for x in result['results']], ['read', 'error'])

    def test_batch_preview_is_default_and_never_journals(self):
        result = s.dispatch('naver_move_read_inbox_batch', {'items': self.items(1, 2)})
        self.assertEqual(result['counts'], {'preview': 2})
        self.assertFalse(self.commands('MOVE'))
        self.assertEqual(s.dispatch('naver_get_move_results', {})['results'], [])

    def test_move_batch_verified_one_move_and_preserves_both_flags(self):
        result = self.move(1, 2, 3)
        self.assertEqual(result['newly_verified_count'], 3)
        self.assertEqual(result['verified_count'], 3)
        self.assertEqual(len(self.commands('MOVE')), 1)
        self.assertEqual(self.commands('MOVE')[0][1], '1,2,3')
        self.assertEqual(self.fake.boxes['INBOX'], {})
        for item in result['results']:
            self.assertTrue(item['details']['source_absent'])
            self.assertTrue(item['details']['seen_preserved'])
            self.assertTrue(item['details']['flagged_preserved'])
            self.assertEqual(item['details']['identity_method'], 'copyuid')
            body = s.dispatch('naver_read_message', {'handle': item['destination_handle']})
            self.assertEqual(body['flags'], item['flags_before'])
        self.assertFalse(any(self.commands(command) for command in ['STORE', 'EXPUNGE', 'COPY']))

    def test_replay_does_not_move_or_double_count(self):
        self.move(1)
        result = self.move(1)
        self.assertTrue(result['results'][0]['replayed'])
        self.assertEqual(result['newly_verified_count'], 0)
        self.assertEqual(len(self.commands('MOVE')), 1)

    def test_journal_committed_before_move(self):
        original = self.fake.uid
        def inspect(command, *args):
            if command == 'MOVE':
                with s.audit() as db:
                    rows = db.execute('SELECT state FROM move_journal').fetchall()
                    self.assertEqual([row['state'] for row in rows], ['pending'])
            return original(command, *args)
        with patch.object(self.fake, 'uid', side_effect=inspect):
            self.assertEqual(self.move(1)['verified_count'], 1)

    def test_flags_mismatch_is_not_success(self):
        self.fake.mode = 'flags_lost'
        result = self.move(1)
        self.assertEqual(result['counts'], {'verification_failed': 1})
        self.assertEqual(result['verified_count'], 0)
        self.assertFalse(result['results'][0]['details']['seen_preserved'])

    def test_partial_no_retains_per_message_results(self):
        self.fake.mode = 'partial'
        result = self.move(1, 2)
        self.assertEqual(result['verified_count'], 1)
        self.assertEqual(result['results'][1]['status'], 'unresolved')
        self.assertIn('2', self.fake.boxes['INBOX'])
        self.move(2)
        self.assertEqual(len(self.commands('MOVE')), 1)

    def test_group_failure_stops_other_destinations(self):
        self.fake.mode = 'flags_lost'
        result = s.dispatch('naver_move_read_inbox_batch', {'items': self.items(1) + self.items(2, dest='Other'), 'dry_run': False})
        self.assertEqual(result['results'][1]['status'], 'not_attempted')
        self.assertIn('2', self.fake.boxes['INBOX'])

    def test_timeout_after_server_move_reconciles_without_retry(self):
        self.fake.mode = 'disconnect'
        result = self.move(1)
        self.assertEqual(result['results'][0]['status'], 'pending')
        self.assertTrue(self.pooled._discard)
        self.fake.responses.pop('COPYUID', None)  # Response lost with the old socket.
        self.fake.mode = 'normal'
        result = s.dispatch('naver_verify_moves', {'handles': [self.handle()]})
        self.assertEqual(result['verified_count'], 1)
        self.assertEqual(result['results'][0]['details']['identity_method'], 'new_uid_and_header_fingerprint')
        self.move(1)
        self.assertEqual(len(self.commands('MOVE')), 1)

    def test_missing_copyuid_unique_fallback(self):
        self.fake.emit_copyuid = False
        result = self.move(1)
        self.assertEqual(result['verified_count'], 1)
        self.assertEqual(result['results'][0]['details']['identity_method'], 'new_uid_and_header_fingerprint')

    def test_fallback_ignores_identical_existing_destination(self):
        self.fake.emit_copyuid = False
        self.fake.boxes['Work']['99'] = mail(1, flagged=True)
        result = self.move(1)
        self.assertEqual(result['verified_count'], 1)

    def test_ambiguous_fallback_not_assumed_success(self):
        self.fake.emit_copyuid = False
        self.fake.mode = 'duplicate'
        result = self.move(1)
        self.assertEqual(result['verified_count'], 0)
        self.assertEqual(result['results'][0]['details']['reason'], 'ambiguous_destination_identity')

    def test_noop_move_ok_not_assumed_success(self):
        self.fake.mode = 'noop'
        result = self.move(1)
        self.assertEqual(result['verified_count'], 0)
        self.assertEqual(result['results'][0]['status'], 'unresolved')

    def test_uidvalidity_change_is_unresolved(self):
        self.move(1)
        self.fake.validity['Work'] = '999'
        result = s.dispatch('naver_verify_moves', {'handles': [self.handle()]})
        self.assertEqual(result['verified_count'], 0)
        self.assertEqual(result['results'][0]['details']['reason'], 'destination_uidvalidity_changed')

    def test_deleted_destination_not_success(self):
        self.move(1)
        self.fake.boxes['Work']['100']['flags'].append('\\Deleted')
        result = s.dispatch('naver_verify_moves', {'handles': [self.handle()]})
        self.assertEqual(result['results'][0]['status'], 'verification_failed')

    def test_source_uidvalidity_change(self):
        self.move(1)
        self.fake.validity['INBOX'] = '999'
        result = s.dispatch('naver_verify_moves', {'handles': [self.handle()]})
        self.assertEqual(result['results'][0]['details']['reason'], 'source_uidvalidity_changed')

    def test_unread_deleted_reference_invalid_destination_blocked(self):
        self.fake.boxes['INBOX']['1']['flags'] = []
        self.fake.boxes['INBOX']['2']['flags'].append('\\Deleted')
        result = self.move(1, 2)
        self.assertEqual(result['counts'], {'rejected': 2})
        items = [{'handle': self.handle(1, kind='reference'), 'destination': 'Work'}, {'handle': self.handle(3), 'destination': 'Sent'}]
        result = s.dispatch('naver_move_read_inbox_batch', {'items': items, 'dry_run': False})
        self.assertEqual(result['counts'], {'rejected': 2})
        self.assertFalse(self.commands('MOVE'))

    def test_disabled_and_unsupported_move(self):
        with patch.dict(os.environ, {'NAVER_ALLOW_MOVE': 'false'}), self.assertRaises(ValueError):
            self.move(1)
        self.fake.capabilities = (b'IMAP4rev1',)
        with self.assertRaises(ValueError):
            self.move(1)

    def test_duplicate_batch_no_second_move(self):
        result = self.move(1, 1)
        self.assertEqual(result['verified_count'], 1)
        self.assertEqual(result['counts']['rejected'], 1)

    def test_destination_conflict_rejected(self):
        self.move(1)
        result = s.dispatch('naver_move_read_inbox_batch', {'items': self.items(1, dest='Other'), 'dry_run': False})
        self.assertEqual(result['counts'], {'rejected': 1})

    def test_legacy_migration_never_claims_verified(self):
        with s.audit() as db:
            db.execute("INSERT INTO moved(account,validity,uid,destination) VALUES('test-owner','42','1','Work')")
            db.commit()
        result = s.dispatch('naver_get_move_results', {})
        self.assertEqual(result['results'][0]['status'], 'legacy_unverified')
        self.assertFalse(result['results'][0]['verified'])
        self.assertEqual(self.move(1)['counts'], {'legacy_unverified': 1})
        self.assertFalse(self.commands('MOVE'))

    def test_audit_pagination_without_imap(self):
        self.move(1, 2, 3)
        self.fake.calls.clear()
        first = s.dispatch('naver_get_move_results', {'limit': 2})
        self.assertTrue(first['has_more'])
        second = s.dispatch('naver_get_move_results', {'after_id': first['next_after_id']})
        self.assertEqual(len(second['results']), 1)
        self.assertEqual(self.fake.calls, [])

    def test_verify_unknown_handle_does_not_move(self):
        result = s.dispatch('naver_verify_moves', {'handles': [self.handle()]})
        self.assertEqual(result['counts'], {'not_recorded': 1})
        self.assertFalse(self.commands('MOVE'))

    def test_single_move_compatible_input_verifiable_output(self):
        result = s.dispatch('naver_move_read_inbox', self.items(1)[0])
        self.assertEqual(result['status'], 'verified')
        self.assertTrue(result['verified'])

    def test_tools_annotations_and_bad_rpc(self):
        tools = s.rpc({'id': 1, 'method': 'tools/list'})['result']['tools']
        self.assertEqual(len(tools), 10)
        self.assertTrue(all(tool['inputSchema']['additionalProperties'] is False for tool in tools))
        for tool in tools:
            self.assertEqual(tool['annotations']['readOnlyHint'], tool['name'] not in s.WRITE_TOOLS)
        self.assertEqual(s.rpc([])['error']['code'], -32600)
        self.assertTrue(s.rpc({'id': 1, 'method': 'tools/call', 'params': {'name': 'naver_status', 'arguments': {'unknown': 1}}})['result']['isError'])

    def test_fifty_message_move_is_one_command(self):
        self.fake.boxes['INBOX'] = {str(uid): mail(uid, flagged=uid % 2 == 1) for uid in range(1, 51)}
        result = self.move(*range(1, 51))
        self.assertEqual(result['newly_verified_count'], 50)
        self.assertEqual(len(self.commands('MOVE')), 1)
        self.assertEqual(len(self.commands('FETCH')), 4)  # preflight, recheck, source, destination

    def test_move_limit_is_enforced_before_writes(self):
        with self.assertRaises(ValueError):
            self.move(*range(1, 52))
        self.assertFalse(self.commands('MOVE'))

    def test_mixed_destinations_grouped_and_verified(self):
        result = s.dispatch('naver_move_read_inbox_batch', {
            'items': self.items(1, 3) + self.items(2, dest='Other'), 'dry_run': False})
        self.assertEqual(result['newly_verified_count'], 3)
        self.assertEqual(len(self.commands('MOVE')), 2)

    def test_replayed_batch_verification_uses_batched_fetch(self):
        self.move(1, 2, 3)
        self.fake.calls.clear()
        result = self.move(1, 2, 3)
        self.assertEqual(result['newly_verified_count'], 0)
        self.assertEqual(len(self.commands('FETCH')), 2)  # source and destination
        self.assertFalse(self.commands('MOVE'))

    def test_reverify_connection_failure_does_not_return_stale_success(self):
        self.move(1)
        with patch.object(self.fake, 'uid', side_effect=s.imaplib.IMAP4.abort('broken')):
            result = s.dispatch('naver_verify_moves', {'handles': [self.handle()]})
        self.assertEqual(result['verified_count'], 0)
        self.assertEqual(result['results'][0]['status'], 'unresolved')
        self.assertFalse(result['results'][0]['verified'])

    def test_existing_unresolved_stops_fresh_moves(self):
        self.fake.mode = 'noop'
        self.move(1)
        self.fake.mode = 'normal'
        result = self.move(1, 2)
        self.assertEqual(result['results'][1]['status'], 'not_attempted')
        self.assertEqual(len(self.commands('MOVE')), 1)
        self.assertIn('2', self.fake.boxes['INBOX'])

    def test_history_attention_filter_and_unique_totals(self):
        self.move(1, 2)
        self.fake.mode = 'noop'
        self.move(3)
        result = s.dispatch('naver_get_move_results', {'needs_attention': True})
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['totals']['verified'], 2)
        self.assertEqual(result['totals']['operations'], 3)

    def test_crash_after_journal_before_send_never_blindly_replays(self):
        original = self.fake.uid
        def crash(command, *args):
            if command == 'MOVE':
                raise SystemExit('simulated process death')
            return original(command, *args)
        with patch.object(self.fake, 'uid', side_effect=crash), self.assertRaises(SystemExit):
            self.move(1)
        with s.audit() as db:
            self.assertEqual(db.execute('SELECT state FROM move_journal').fetchone()[0], 'pending')
        result = self.move(1)
        self.assertEqual(result['results'][0]['status'], 'unresolved')
        self.assertFalse(self.commands('MOVE'))
        self.assertIn('1', self.fake.boxes['INBOX'])

    def test_fallback_scan_limit_fails_closed(self):
        self.fake.emit_copyuid = False
        original = self.fake.uid
        def incoming(command, *args):
            result = original(command, *args)
            if command == 'MOVE':
                for uid in range(101, 302):
                    self.fake.boxes['Work'][str(uid)] = mail(uid)
                self.fake.next_uid['Work'] = 302
            return result
        with patch.object(self.fake, 'uid', side_effect=incoming):
            result = self.move(1)
        self.assertEqual(result['verified_count'], 0)
        self.assertEqual(result['results'][0]['details']['reason'], 'fallback_scan_limit_exceeded')

    def test_copyuid_bounded_parser(self):
        self.assertEqual(s.expand_uids(b'1,3:5'), ['1', '3', '4', '5'])
        with self.assertRaises(ValueError):
            s.expand_uids(b'1:9999999999')


class PoolTests(unittest.TestCase):
    def test_reuse_and_discard(self):
        with patch.dict(os.environ, {'NAVER_USER': 'test', 'NAVER_APP_PASSWORD': 'test'}):
            raw = Fake()
            conn = s.MeasuredConnection(raw)
            pool = s.ConnectionPool()
            with patch.object(s, 'connect', return_value=conn) as factory:
                with pool.lease() as first:
                    self.assertFalse(first.reused)
                with pool.lease() as second:
                    self.assertIs(first, second)
                    self.assertTrue(second.reused)
                    second._discard = True
                self.assertEqual(factory.call_count, 1)
                self.assertEqual(raw.logouts, 1)
                self.assertTrue(pool.idle.empty())

    def test_connection_failure_not_reused(self):
        with patch.dict(os.environ, {'NAVER_USER': 'test', 'NAVER_APP_PASSWORD': 'test'}):
            raw = Fake()
            pool = s.ConnectionPool()
            with patch.object(s, 'connect', return_value=s.MeasuredConnection(raw)):
                with self.assertRaises(RuntimeError), pool.lease():
                    raise RuntimeError('broken')
                self.assertTrue(pool.idle.empty())
                self.assertEqual(raw.logouts, 1)


if __name__ == '__main__':
    unittest.main()
