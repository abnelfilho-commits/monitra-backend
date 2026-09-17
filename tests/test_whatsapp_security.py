"""No network transport or clinical data: signed synthetic ingress tests."""
import test_cardio_foundation  # Existing isolated test bootstrap.
import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import Mock, patch
from fastapi import FastAPI
import asyncio
from types import SimpleNamespace
from urllib.parse import urlencode
from app.database import get_db
from app.routers import whatsapp

ENV = {'WHATSAPP_APP_SECRET':'synthetic-secret', 'WHATSAPP_PHONE_NUMBER_ID':'12345',
       'WHATSAPP_VERIFY_TOKEN':'synthetic-verify', 'WHATSAPP_ACCESS_TOKEN':''}


def envelope(content='oi', sender='5565999990000', identity='synthetic-id', recipient='12345'):
    return {'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{
        'metadata':{'phone_number_id':recipient},'messages':[{
            'id':identity,'from':sender,'type':'text','text':{'body':content}}]}}]}]}


def encoded(payload):
    return json.dumps(payload, ensure_ascii=False).encode()


def signature(body):
    return 'sha256='+hmac.new(b'synthetic-secret',body,hashlib.sha256).hexdigest()


class LocalClient:
    """Exercise FastAPI/ASGI without adding an HTTP client dependency."""
    def __init__(self, app):
        self.app = app

    def get(self, path, params=None):
        return self.request('GET', path, params=params)

    def post(self, path, content=None, headers=None, json=None):
        return self.request('POST', path, content if content is not None else encoded(json), headers)

    def request(self, method, path, body=b'', headers=None, params=None):
        async def run():
            events = []
            async def receive():
                return {'type':'http.request','body':body,'more_body':False}
            async def send(event):
                events.append(event)
            await self.app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1',
                'method':method,'scheme':'http','path':path,'raw_path':path.encode(),
                'query_string':urlencode(params or {}).encode(),
                'headers':[(k.lower().encode(),v.encode()) for k,v in (headers or {}).items()],
                'client':('127.0.0.1',1),'server':('synthetic',80),'root_path':''}, receive, send)
            status = next(item['status'] for item in events if item['type']=='http.response.start')
            data = b''.join(item.get('body',b'') for item in events if item['type']=='http.response.body').decode()
            return SimpleNamespace(status_code=status,text=data,json=lambda:json.loads(data))
        return asyncio.run(run())


class IngressSecurityTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,ENV);self.env.start();self.addCleanup(self.env.stop)
        self.app=FastAPI();self.app.include_router(whatsapp.router)
        self.db=Mock()
        self.app.dependency_overrides[get_db]=lambda:self.db
        self.client=LocalClient(self.app)
        self.processing=patch.object(whatsapp,'process_message',return_value='synthetic response')
        self.process=self.processing.start();self.addCleanup(self.processing.stop)

    def post(self,payload=None,header=None,body=None):
        body=body if body is not None else encoded(payload or envelope())
        return self.client.post('/whatsapp/webhook',content=body,
            headers={'X-Hub-Signature-256':signature(body) if header is None else header,
                     'Content-Type':'application/json'})

    def rejected_without_effect(self,response,status):
        self.assertEqual(response.status_code,status)
        self.process.assert_not_called();self.assertEqual(self.db.mock_calls,[])

    def test_valid_signed_original_unicode_body(self):
        response=self.post(envelope('Observação sintética'))
        self.assertEqual(response.status_code,200)
        self.process.assert_called_once()
        self.assertEqual(self.process.call_args.args[-1],'Observação sintética')

    def test_missing_signature(self):
        self.rejected_without_effect(self.client.post('/whatsapp/webhook',json=envelope()),403)

    def test_invalid_signature(self):
        self.rejected_without_effect(self.post(header='sha256=invalid'),403)

    def test_tampered_body(self):
        self.rejected_without_effect(self.post(body=encoded(envelope('changed')),
            header=signature(encoded(envelope()))),403)

    def test_missing_config(self):
        for name in ('WHATSAPP_APP_SECRET','WHATSAPP_PHONE_NUMBER_ID'):
            with self.subTest(name=name),patch.dict(os.environ,{name:''}):
                self.rejected_without_effect(self.post(),503)

    def test_invalid_recipient(self):
        self.rejected_without_effect(self.post(envelope(recipient='other')),403)

    def test_malformed_authenticated_payload(self):
        for body in (b'not-json', b'[]', b'{}', encoded(envelope(sender='not-a-phone'))):
            with self.subTest(body=body):
                self.rejected_without_effect(self.post(body=body),400)

    def test_batch_validates_all_before_processing(self):
        payload=envelope()
        payload['entry'].extend(envelope(recipient='wrong')['entry'])
        self.rejected_without_effect(self.post(payload),403)

    def test_signed_non_text_and_status_events_ignored(self):
        payload=envelope();value=payload['entry'][0]['changes'][0]['value']
        value['messages'][0]['type']='image'
        self.assertEqual(self.post(payload).json(),{'status':'ignored'})
        del value['messages'];value['statuses']=[]
        self.assertEqual(self.post(payload).json(),{'status':'ignored'})
        self.process.assert_not_called()

    def test_get_handshake_fail_closed(self):
        params={'hub.mode':'subscribe','hub.verify_token':'synthetic-verify','hub.challenge':'abc'}
        self.assertEqual(self.client.get('/whatsapp/webhook',params=params).text,'abc')
        for token in ('','wrong'):
            self.assertEqual(self.client.get('/whatsapp/webhook',params=dict(params,**{'hub.verify_token':token})).status_code,403)
        with patch.dict(os.environ,{'WHATSAPP_VERIFY_TOKEN':''}):
            self.assertEqual(self.client.get('/whatsapp/webhook',params={'hub.mode':'subscribe'}).status_code,503)

    def test_no_diagnostic_bypass_in_any_environment(self):
        for env in ('development','hml','production'):
            with patch.dict(os.environ,{'APP_ENV':env,'WHATSAPP_TEST_ENABLED':'true'}):
                self.assertEqual(self.client.post('/whatsapp/teste',json={'telefone':'5565999990000','mensagem':'oi'}).status_code,404)
        self.process.assert_not_called()

    def test_errors_do_not_log_sensitive_contents(self):
        self.process.side_effect=RuntimeError('5565999990000 sensitive clinical text')
        with self.assertLogs(whatsapp.logger,level='ERROR') as logs:
            response=self.post(envelope('sensitive clinical text'))
        self.assertEqual(response.status_code,503)
        self.assertNotIn('5565999990000',' '.join(logs.output)+response.text)
        self.assertNotIn('sensitive clinical text',' '.join(logs.output)+response.text)

    def test_access_log_does_not_expose_handshake_token(self):
        import logging
        record=logging.LogRecord('uvicorn.access',logging.INFO,'synthetic',1,
            '%s - "%s %s HTTP/%s" %d',('local','GET','/whatsapp/webhook?hub.verify_token=sensitive','1.1',200),None)
        self.assertTrue(whatsapp.WebhookAccessFilter().filter(record))
        self.assertNotIn('sensitive',record.getMessage())
        self.assertIn('/whatsapp/webhook',record.getMessage())

    def test_transport_failure_retry_status_without_sensitive_error(self):
        with patch.dict(os.environ,{'WHATSAPP_ACCESS_TOKEN':'synthetic'}),patch.object(
            whatsapp,'deliver_reply',side_effect=RuntimeError('clinical text')):
            with self.assertLogs(whatsapp.logger,level='ERROR'):
                self.assertEqual(self.post().status_code,503)


class LongitudinalWriteBoundaryTests(unittest.TestCase):
    """The Portal's shared write route cannot bypass channel authorization."""
    def setUp(self):
        import test_cardio_channels as fixtures
        fixtures.CardioChannelTests.setUp(self)
        self.app=FastAPI()
        from app.routers import registros_longitudinais
        self.app.include_router(registros_longitudinais.router)
        self.app.dependency_overrides[get_db]=lambda:self.db
        self.client=LocalClient(self.app)
        from app.models import CampoFormulario
        field=self.db.query(CampoFormulario).filter_by(formulario_id=200,nome_campo='peso').one()
        from datetime import date
        self.payload=dict(paciente_id=3,modulo_id=2,formulario_id=200,data_registro=date.today().isoformat(),
                          origem='PROFISSIONAL',respostas=[{'campo_id':field.id,'valor':85}])

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def authenticate(self):
        from app.core.deps import get_usuario_atual
        self.app.dependency_overrides[get_usuario_atual]=lambda:self.user

    def test_authentication_required(self):
        self.assertEqual(self.client.post('/registros-longitudinais/',json=self.payload).status_code,401)
        self.assertEqual(self.client.get('/registros-longitudinais/1').status_code,401)
        self.assertEqual(self.client.request('PATCH','/registros-longitudinais/1',encoded(self.payload),
            {'Content-Type':'application/json'}).status_code,401)

    def test_line_clinic_and_actor(self):
        self.authenticate()
        for patient in (1,4):
            response=self.client.post('/registros-longitudinais/',json=dict(self.payload,paciente_id=patient),
                headers={'Content-Type':'application/json'})
            self.assertIn(response.status_code,(403,404))
        response=self.client.post('/registros-longitudinais/',json=self.payload,headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code,200,response.text)
        from app.models import RegistroLongitudinal
        row=self.db.query(RegistroLongitudinal).one()
        self.assertEqual((row.modulo_id,row.criado_por_usuario_id),(2,1))

    def test_responsible_origin_cannot_be_forged_by_professional_route(self):
        self.authenticate()
        response=self.client.post('/registros-longitudinais/',json=dict(self.payload,origem='RESPONSAVEL_WHATSAPP'),
            headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code,400,response.text)
