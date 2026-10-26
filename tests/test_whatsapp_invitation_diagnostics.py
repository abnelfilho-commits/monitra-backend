"""Synthetic invite failures: no real HTTP calls, credentials or clinical data."""
import test_whatsapp_security  # Existing isolated application bootstrap.
import os
import unittest
import re
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
import requests
from app.routers import whatsapp_mental as api
from app.services.whatsapp_sender_service import WhatsAppSenderService, invitation_diagnostics

ENV = {'WHATSAPP_ACCESS_TOKEN': 'secret-token-sentinel', 'WHATSAPP_PHONE_NUMBER_ID': '12345',
       'WHATSAPP_MENTAL_TEMPLATE_NAME': 'integra_care_checkin_bem_estar', 'WHATSAPP_MENTAL_TEMPLATE_LANGUAGE': 'pt_BR'}
PHONE = '5565999990000'
PRIVATE = 'clinical-sentinel Authorization: Bearer secret-token-sentinel ' + PHONE


class InvitationDiagnosticsTests(unittest.TestCase):
    def invoke(self, *, env=None, response=None, error=None, local_failure=None):
        db = Mock()
        db.scalar.return_value = SimpleNamespace(id=7)
        db.commit.side_effect = [None, RuntimeError(PRIVATE)] if local_failure == 'commit' else None
        def delivery(*_, **__):
            WhatsAppSenderService.enviar_template(PHONE)
            if local_failure == 'flush':
                raise RuntimeError(PRIVATE)
            return True
        with patch.dict(os.environ, ENV if env is None else env, clear=True), \
                patch.object(api.service, 'authorized'), \
                patch.object(api.service, 'prepare', return_value=SimpleNamespace(id=1)), \
                patch.object(api.service, 'deliver_invitation', side_effect=delivery), \
                patch('app.services.whatsapp_sender_service.requests.post', return_value=response, side_effect=error) as post:
            with self.assertLogs(api.logger, level='WARNING') as captured:
                result = api.invitation(db, {'context': 1})
        self.assertEqual(result, {'status': 'ENVIO_PENDENTE', 'conversa_id': 1})
        self.assertEqual(db.rollback.call_count, 2)
        log = '\n'.join(captured.output)
        for secret in (PHONE, ENV['WHATSAPP_ACCESS_TOKEN'], PRIVATE, 'Authorization', 'clinical-sentinel'):
            self.assertNotIn(secret, log)
        self.assertTrue(all(r.exc_info is None for r in captured.records))
        self.assertIn('conversation_id=1', log)
        self.assertIn('graph_version=v25.0', log)
        stamp = re.search(r'observed_at_utc=(\S+)', log).group(1)
        self.assertEqual(datetime.fromisoformat(stamp).utcoffset(), timedelta(0))
        return log, post

    def test_missing_configuration(self):
        for key in ENV:
            with self.subTest(key=key):
                log, post = self.invoke(env=dict(ENV, **{key: ''}))
                self.assertIn('stage=configuration category=configuration', log)
                post.assert_not_called()

    def test_graph_rejection_allowlisted_metadata_only(self):
        response = Mock(ok=False, status_code=400)
        response.json.return_value = {'error': {'code': 132000, 'error_subcode': 2494073,
            'fbtrace_id': 'ABC_safe-trace', 'message': PRIVATE, 'error_data': {'details': PRIVATE}}}
        log, _ = self.invoke(response=response)
        self.assertIn('category=http_rejection graph_http_status=400 meta_code=132000 meta_subcode=2494073 meta_trace_id=ABC_safe-trace', log)
        self.assertIn('meta_accepted=False', log)

    def test_malformed_error_metadata_is_not_logged(self):
        for trace in (PRIVATE, PHONE, ENV['WHATSAPP_ACCESS_TOKEN'], 'bad\ntrace'):
            response = Mock(ok=False, status_code=403)
            response.json.return_value = {'error': {'code': PRIVATE, 'error_subcode': {'raw': PRIVATE}, 'fbtrace_id': trace}}
            log, _ = self.invoke(response=response)
            self.assertIn('meta_code=None meta_subcode=None meta_trace_id=None', log)
        response.json.side_effect = ValueError(PRIVATE)
        log, _ = self.invoke(response=response)
        self.assertIn('category=http_rejection', log)

    def test_timeout_connection_and_other_exceptions(self):
        for error, category in ((requests.Timeout(PRIVATE), 'timeout'),
                                (requests.ConnectionError(PRIVATE), 'connection'),
                                (RuntimeError(PRIVATE), 'other')):
            with self.subTest(category=category):
                log, _ = self.invoke(error=error)
                self.assertIn('stage=meta_request category=' + category, log)
                self.assertIn('meta_accepted=False', log)

    def test_local_commit_and_flush_after_meta_success(self):
        for failure, stage in (('commit', 'local_commit'), ('flush', 'local_confirmation')):
            response = Mock(ok=True, status_code=200)
            response.json.return_value = {'messages': [{'id': PRIVATE}]}
            log, _ = self.invoke(response=response, local_failure=failure)
            self.assertIn('stage=' + stage, log)
            self.assertIn('graph_http_status=200', log)
            self.assertIn('meta_accepted=True', log)

    def test_invalid_json_after_http_success_is_not_local_confirmation(self):
        response = Mock(ok=True, status_code=200)
        response.json.side_effect = ValueError(PRIVATE)
        log, _ = self.invoke(response=response)
        self.assertIn('stage=meta_response', log)
        self.assertIn('meta_accepted=True', log)

    def test_request_local_diagnostics_do_not_leak_between_calls(self):
        with invitation_diagnostics() as outer:
            with invitation_diagnostics() as inner:
                inner['meta_code'] = 123
            self.assertIsNone(outer['meta_code'])
        with invitation_diagnostics() as fresh:
            self.assertIsNone(fresh['meta_code'])
            self.assertFalse(fresh['meta_accepted'])

    def test_success_and_no_new_send_preserve_response(self):
        for sent, status in ((True, 'ENVIADO'), (False, 'SEM_NOVO_ENVIO')):
            db = Mock(); db.scalar.return_value = SimpleNamespace(id=7)
            with patch.object(api.service, 'authorized'), \
                    patch.object(api.service, 'prepare', return_value=SimpleNamespace(id=1)), \
                    patch.object(api.service, 'deliver_invitation', return_value=sent), \
                    patch.object(api.logger, 'warning') as warning:
                self.assertEqual(api.invitation(db, {'context': 1}), {'status': status, 'conversa_id': 1})
                warning.assert_not_called()

    def test_success_logs_http_and_utc_without_sensitive_data(self):
        for retry in (False, True):
            db = Mock(); db.scalar.side_effect = [SimpleNamespace(id=7), SimpleNamespace(id=1)] if retry else [SimpleNamespace(id=7)]
            response = Mock(ok=True, status_code=200)
            response.json.return_value = {'messages': [{'id': PRIVATE}]}
            def delivery(*_, **__):
                WhatsAppSenderService.enviar_template(PHONE)
                return True
            with patch.dict(os.environ, ENV, clear=True), \
                    patch.object(api.service, 'authorized'), \
                    patch.object(api.service, 'prepare', return_value=SimpleNamespace(id=1)) as prepare, \
                    patch.object(api.service, 'deliver_invitation', side_effect=delivery), \
                    patch('app.services.whatsapp_sender_service.requests.post', return_value=response) as post, \
                    self.assertLogs(api.logger, level='INFO') as captured:
                result = api.invitation(db, {'context': 1}, retry=retry)
            self.assertEqual(result, {'status': 'ENVIADO', 'conversa_id': 1})
            self.assertEqual(post.call_count, 1)
            if retry: prepare.assert_not_called()
            log = '\n'.join(captured.output)
            self.assertIn('graph_version=v25.0', log)
            self.assertIn('graph_http_status=200 meta_accepted=True', log)
            stamp = re.search(r'observed_at_utc=(\S+)', log).group(1)
            self.assertEqual(datetime.fromisoformat(stamp).utcoffset(), timedelta(0))
            for secret in (PHONE, PRIVATE, ENV['WHATSAPP_ACCESS_TOKEN'], 'Authorization'):
                self.assertNotIn(secret, log)
            self.assertEqual(db.commit.call_count, 2)
