"""Scoped Serve configuration regressions; all CLI/network calls are mocked."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

from tools import configure_tailscale as helper


HOST = 'organiza-server.example-tail.ts.net'
ENDPOINT = HOST + ':443'
BACKEND = 'http://127.0.0.1:8765'
NODE = {'BackendState': 'Running', 'Self': {'DNSName': HOST + '.', 'Online': True},
        'CurrentTailnet': {'MagicDNSEnabled': True}}
SERVICES = {'version': '0.0.1', 'services': {'svc:another-app': {'endpoints': {'tcp:443': 'http://127.0.0.1:3200'}}}}


def owned_route():
    return {'TCP': {'443': {'HTTPS': True}},
            'Web': {ENDPOINT: {'Handlers': {'/': {'Proxy': BACKEND}}}}}


def observation(serve=None, node=None, services=None):
    return deepcopy({'node': NODE if node is None else node,
                     'serve': {} if serve is None else serve,
                     'services': SERVICES if services is None else services})


class TailscaleConfigurationTests(unittest.TestCase):
    def setUp(self):
        results = helper.ROOT / 'test-results'
        results.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='tailscale-helper-', dir=results)
        self.root = Path(self.temporary.name).resolve()
        self.root_patch = patch.object(helper, 'ROOT', self.root)
        self.root_patch.start()
        self.config = {'port': 8765, 'database': self.root / 'existing-official.sqlite3',
                       'private_url': 'https://' + HOST}
        self.validate = patch.object(helper, 'validate_database').start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.temporary.cleanup)

    def desired(self, config=None):
        return helper.target(config or self.config, NODE)

    def run_mutation(self, before, after, action='apply', command_success=True):
        with patch.object(helper, 'inspect', side_effect=[before, after]), \
             patch.object(helper, 'change', return_value=command_success) as change:
            result = helper.mutate(self.config, 'tailscale.exe', action)
            change.assert_called_once()
            return result

    def test_empty_serve_adds_only_own_handler_and_snapshots_configuration(self):
        before = observation()
        after = observation(owned_route())
        result = self.run_mutation(before, after)
        self.assertEqual(result['result'], 'configured')
        self.assertTrue(result['other_services_preserved'])
        self.validate.assert_called_once_with(self.config['database'])
        saved = json.loads(Path(result['snapshot']).read_text(encoding='utf-8'))
        self.assertEqual(saved['serve_status'], {})
        self.assertEqual(saved['service_config'], SERVICES)
        self.assertNotIn('node', saved)
        self.assertNotIn('database', saved)

    def test_other_paths_ports_and_services_are_preserved_on_apply_and_disable(self):
        existing = {'TCP': {'443': {'HTTPS': True}, '9443': {'HTTPS': True}},
                    'Web': {ENDPOINT: {'Handlers': {'/another': {'Proxy': 'http://127.0.0.1:3200'}}},
                            HOST + ':9443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:4100'}}}},
                    'AllowFunnel': {HOST + ':10000': True}}
        with_own = deepcopy(existing)
        with_own['Web'][ENDPOINT]['Handlers']['/'] = {'Proxy': BACKEND}
        self.assertEqual(self.run_mutation(observation(existing), observation(with_own))['result'], 'configured')
        self.assertEqual(self.run_mutation(observation(with_own), observation(existing), action='disable')['result'], 'disabled')

    def test_another_root_handler_is_never_overwritten_or_disabled(self):
        for action in ('apply', 'disable'):
            for handler in ({'Proxy': 'http://127.0.0.1:9999'}, {'Path': 'C:/another-app'}, {'Text': 'another-app'}):
                before = owned_route()
                before['Web'][ENDPOINT]['Handlers']['/'] = handler
                with self.subTest(action=action, handler=handler), \
                     patch.object(helper, 'inspect', return_value=observation(before)), \
                     patch.object(helper, 'change') as change, patch.object(helper, 'snapshot') as snapshot:
                    with self.assertRaisesRegex(RuntimeError, 'outro serviço'):
                        helper.mutate(self.config, 'tailscale.exe', action)
                    change.assert_not_called()
                    snapshot.assert_not_called()

    def test_raw_tcp_or_tls_forwarder_prevents_any_mutation(self):
        for transport in ({'TCPForward': '127.0.0.1:22'}, {'HTTPS': False}, {'HTTPS': True, 'TCPForward': '127.0.0.1:22'}):
            with self.subTest(transport=transport), \
                 patch.object(helper, 'inspect', return_value=observation({'TCP': {'443': transport}})), \
                 patch.object(helper, 'change') as change:
                with self.assertRaisesRegex(RuntimeError, 'TCP/TLS'):
                    helper.mutate(self.config, 'tailscale.exe', 'apply')
                change.assert_not_called()

    def test_public_funnel_on_same_port_is_not_changed_even_on_different_host(self):
        for endpoint in (ENDPOINT, 'another.example-tail.ts.net:443'):
            for action in ('apply', 'disable'):
                public = owned_route()
                public['AllowFunnel'] = {endpoint: True}
                with self.subTest(endpoint=endpoint, action=action), \
                     patch.object(helper, 'inspect', return_value=observation(public)), \
                     patch.object(helper, 'change') as change:
                    with self.assertRaisesRegex(RuntimeError, 'Funnel público'):
                        helper.mutate(self.config, 'tailscale.exe', action)
                    change.assert_not_called()

    def test_exact_self_dnsname_and_https_origin_are_required(self):
        invalid = ['http://' + HOST, 'https://other.example-tail.ts.net',
                   'https://' + HOST + '/organiza', 'https://person:secret@' + HOST,
                   'https://' + HOST + '?token=secret', 'https://' + HOST + ':0',
                   'https://*.example-tail.ts.net']
        for origin in invalid:
            with self.subTest(origin=origin), self.assertRaises(RuntimeError):
                helper.target({**self.config, 'private_url': origin}, NODE, require_online=True)
        alternate = helper.target({**self.config, 'private_url': 'https://' + HOST + ':8443'}, NODE)
        self.assertEqual(alternate['endpoint'], HOST + ':8443')

    def test_disconnected_or_unconfirmed_magicdns_cannot_mutate(self):
        cases = [deepcopy(NODE), deepcopy(NODE), deepcopy(NODE), deepcopy(NODE)]
        cases[0]['BackendState'] = 'Stopped'
        cases[1]['Self']['Online'] = False
        cases[2]['CurrentTailnet']['MagicDNSEnabled'] = False
        cases[3].pop('CurrentTailnet')
        for node in cases:
            with self.subTest(node=node), patch.object(helper, 'inspect', return_value=observation(node=node)), \
                 patch.object(helper, 'change') as change:
                with self.assertRaises(RuntimeError):
                    helper.mutate(self.config, 'tailscale.exe', 'apply')
                change.assert_not_called()

    def test_missing_database_stops_apply_without_creating_database_or_calling_cli(self):
        from tools.organiza_runtime import validate_database
        with patch.object(helper, 'validate_database', side_effect=validate_database), \
             patch.object(helper, 'inspect') as inspect, patch.object(helper, 'change') as change:
            with self.assertRaisesRegex(RuntimeError, 'Banco existente não encontrado'):
                helper.mutate(self.config, 'tailscale.exe', 'apply')
            self.assertFalse(self.config['database'].exists())
            inspect.assert_not_called()
            change.assert_not_called()

    def test_repeated_apply_and_disable_do_not_issue_a_change(self):
        for action, serve in (('apply', owned_route()), ('disable', {})):
            with self.subTest(action=action), patch.object(helper, 'inspect', return_value=observation(serve)), \
                 patch.object(helper, 'change') as change, patch.object(helper, 'snapshot') as snapshot:
                result = helper.mutate(self.config, 'tailscale.exe', action)
                self.assertTrue(result['result'].startswith('already_'))
                change.assert_not_called()
                snapshot.assert_not_called()

    def test_change_uses_scoped_argv_and_bounded_timeout_without_shell(self):
        for action, final in (('apply', BACKEND), ('disable', 'off')):
            with self.subTest(action=action), patch.object(helper.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                self.assertTrue(helper.change('tailscale.exe', action, self.desired()))
                arguments, = run.call_args.args
                self.assertEqual(arguments, ['tailscale.exe', 'serve', '--bg', '--https=443', '--set-path=/', final])
                self.assertEqual(run.call_args.kwargs['timeout'], helper.CHANGE_TIMEOUT)
                self.assertNotIn('shell', run.call_args.kwargs)

    def test_timeout_with_no_route_preserves_snapshot_and_gives_manual_https_step(self):
        with patch.object(helper, 'inspect', side_effect=[observation(), observation()]), \
             patch.object(helper.subprocess, 'run', side_effect=subprocess.TimeoutExpired('tailscale', helper.CHANGE_TIMEOUT)) as run:
            with self.assertRaisesRegex(RuntimeError, 'HTTPS Certificates > Enable HTTPS'):
                helper.mutate(self.config, 'tailscale.exe', 'apply')
            self.assertEqual(run.call_count, 1)
            self.assertEqual(len(list((self.root / 'data' / 'runtime').glob('tailscale-before-*.json'))), 1)

    def test_uncertain_cli_result_uses_observed_persisted_route(self):
        result = self.run_mutation(observation(), observation(owned_route()), command_success=False)
        self.assertEqual(result['serve_state'], 'configured')

    def test_change_to_unrelated_endpoint_is_detected_without_global_restore(self):
        before = {'TCP': {'9443': {'HTTPS': True}},
                  'Web': {HOST + ':9443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:3200'}}}}}
        after = owned_route()
        after['TCP'].update(before['TCP'])
        after['Web'][HOST + ':9443'] = {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:9999'}}}
        with patch.object(helper, 'inspect', side_effect=[observation(before), observation(after)]), \
             patch.object(helper, 'change', return_value=True) as change:
            with self.assertRaisesRegex(RuntimeError, 'alteração fora do endpoint'):
                helper.mutate(self.config, 'tailscale.exe', 'apply')
            self.assertEqual(change.call_count, 1)
            self.assertEqual(len(list((self.root / 'data' / 'runtime').glob('tailscale-before-*.json'))), 1)

    def test_service_config_change_is_detected_without_restore(self):
        with patch.object(helper, 'inspect', side_effect=[observation(), observation(owned_route(), services={'version': '0.0.1'})]), \
             patch.object(helper, 'change', return_value=True) as change:
            with self.assertRaisesRegex(RuntimeError, 'alteração fora do endpoint'):
                helper.mutate(self.config, 'tailscale.exe', 'apply')
            change.assert_called_once()

    def test_shared_https_transport_is_preserved_and_loss_detected(self):
        before = owned_route()
        before['Web'][ENDPOINT]['Handlers']['/another'] = {'Proxy': 'http://127.0.0.1:3200'}
        after = deepcopy(before)
        after['Web'][ENDPOINT]['Handlers'].pop('/')
        after.pop('TCP')
        with patch.object(helper, 'inspect', side_effect=[observation(before), observation(after)]), \
             patch.object(helper, 'change', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'alteração fora do endpoint'):
                helper.mutate(self.config, 'tailscale.exe', 'disable')

    def test_incomplete_owned_route_is_not_falsely_reported_as_removed(self):
        incomplete = owned_route()
        incomplete.pop('TCP')
        with patch.object(helper, 'inspect', side_effect=[observation(incomplete), observation(incomplete)]), \
             patch.object(helper, 'change', return_value=True) as change:
            with self.assertRaisesRegex(RuntimeError, 'resultado não corresponde'):
                helper.mutate(self.config, 'tailscale.exe', 'disable')
            change.assert_called_once()

    def test_readonly_check_reports_provisional_url_without_mutation_or_financial_read(self):
        with patch.object(helper, 'inspect', return_value=observation()), \
             patch.object(helper, 'change') as change, patch.object(helper, 'health_check') as health:
            result = helper.check(self.config, 'tailscale.exe')
            self.assertEqual(result['serve_state'], 'not_configured')
            self.assertTrue(result['provisional_url'])
            self.assertEqual(result['private_url'], 'https://' + HOST + '/')
            change.assert_not_called()
            health.assert_not_called()
            self.validate.assert_not_called()

    def test_verification_only_requests_health_and_keeps_tls_validation(self):
        response = Mock()
        response.read.return_value = json.dumps({'application': 'organiza', 'instance_id': helper.instance_id(self.root)}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(helper.urllib.request, 'build_opener', return_value=opener) as build:
            self.assertTrue(helper.health_check('https://' + HOST)['ok'])
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, 'https://' + HOST + '/api/health')
            self.assertIsNone(request.data)
            self.assertEqual(build.call_args.args[0].proxies, {})
            # No custom insecure HTTPS handler/context is supplied.
            self.assertEqual(len(build.call_args.args), 2)
        response.read.return_value = b'{"application":"another-service"}'
        with patch.object(helper.urllib.request, 'build_opener', return_value=opener):
            self.assertFalse(helper.health_check('https://' + HOST)['ok'])


if __name__ == '__main__':
    unittest.main()
