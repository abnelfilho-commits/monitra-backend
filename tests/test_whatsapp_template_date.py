"""E14A: deterministic invitation payloads; no real network or database."""
import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock, patch
from app.services.whatsapp_sender_service import (
    WhatsAppSenderService, mental_template_payload, DATED_MENTAL_TEMPLATE,
    LEGACY_MENTAL_TEMPLATE,
)
ENV = {'WHATSAPP_ACCESS_TOKEN': 'synthetic-token', 'WHATSAPP_PHONE_NUMBER_ID': '12345',
       'WHATSAPP_MENTAL_TEMPLATE_NAME': LEGACY_MENTAL_TEMPLATE, 'WHATSAPP_MENTAL_TEMPLATE_LANGUAGE': 'pt_BR'}


class TemplateDateTests(unittest.TestCase):
    def test_new_template_exact_payload(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {'messages': [{'id': 'wamid.test'}]}
        with patch.dict(os.environ, dict(ENV, WHATSAPP_MENTAL_TEMPLATE_NAME=DATED_MENTAL_TEMPLATE), clear=True), patch('app.services.whatsapp_sender_service.requests.post', return_value=response) as post:
            WhatsAppSenderService.enviar_template('synthetic-destination', checkin_date=date(2026, 10, 25))
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['template'], {'name': DATED_MENTAL_TEMPLATE, 'language': {'code': 'pt_BR'}, 'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': '25/10/2026'}]}]})
        self.assertEqual(set(payload), {'messaging_product', 'to', 'type', 'template'})

    def test_civil_dates_preserved_and_not_current_date(self):
        for value, expected in [(date(2024,2,29),'29/02/2024'), (date(2026,1,1),'01/01/2026'), (date(2026,12,31),'31/12/2026')]:
            self.assertEqual(mental_template_payload(DATED_MENTAL_TEMPLATE,'pt_BR',value)['components'][0]['parameters'][0]['text'],expected)

    def test_legacy_has_no_parameters_even_with_date(self):
        self.assertEqual(mental_template_payload(LEGACY_MENTAL_TEMPLATE,'pt_BR',date(2026,10,25)), {'name':LEGACY_MENTAL_TEMPLATE,'language':{'code':'pt_BR'}})

    def test_invalid_dates_fail_before_http(self):
        for value in [None, '25/10/2026', datetime(2026,10,25), datetime(2026,10,25,tzinfo=timezone.utc)]:
            with patch.dict(os.environ, dict(ENV, WHATSAPP_MENTAL_TEMPLATE_NAME=DATED_MENTAL_TEMPLATE), clear=True), patch('app.services.whatsapp_sender_service.requests.post') as post, self.assertRaises(ValueError):
                WhatsAppSenderService.enviar_template('synthetic-destination',checkin_date=value)
            post.assert_not_called()

    def test_unknown_name_and_language_fail_before_http(self):
        for key,value in [('WHATSAPP_MENTAL_TEMPLATE_NAME','unknown'),('WHATSAPP_MENTAL_TEMPLATE_LANGUAGE','en_US')]:
            with patch.dict(os.environ, dict(ENV, **{key:value}), clear=True), patch('app.services.whatsapp_sender_service.requests.post') as post, self.assertRaises(ValueError):
                WhatsAppSenderService.enviar_template('synthetic-destination',checkin_date=date(2026,10,25))
            post.assert_not_called()

    def test_template_change_rejected(self):
        with patch.dict(os.environ, ENV, clear=True), patch('app.services.whatsapp_sender_service.requests.post') as post, self.assertRaises(ValueError):
            WhatsAppSenderService.enviar_template('synthetic-destination',expected_template=(DATED_MENTAL_TEMPLATE,'pt_BR'))
        post.assert_not_called()
