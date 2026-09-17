import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest
from fastapi import FastAPI
from app.database import get_db
from app.routers import registros_longitudinais, responsavel_registros, cardiometabolico
from app.schemas.registro import RegistroDiarioResponsavelCreate
from app.schemas.cardiometabolico import RegistroDiarioCardio
from app.services.care_lines import CareOrigin
from app.services.daily_record import DailyRecordResult
import test_daily_record as fixtures
DAY = fixtures.DAY


class RouteTests(unittest.TestCase):
    def setUp(self):
        fixtures.PersistenceTests.setUp(self)
        # Generic PATCH now checks canonical attendance linkage before dispatch.
        from app.models import SessaoAssistencial
        SessaoAssistencial.__table__.create(self.engine)
    tearDown = fixtures.PersistenceTests.tearDown
    count = fixtures.PersistenceTests.count
    # Separate adapter tests use the same synthetic database fixture.
    def request(self, method, path, payload):
        app = FastAPI()
        app.include_router(registros_longitudinais.router)
        app.dependency_overrides[get_db] = lambda: self.db
        from app.core.deps import get_usuario_atual
        app.dependency_overrides[get_usuario_atual] = lambda: SimpleNamespace(id=7)
        async def send():
            messages = []
            delivered = False
            async def receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type':'http.request', 'body':json.dumps(payload).encode(), 'more_body':False}
                await asyncio.sleep(3600)
            async def send_message(message):
                messages.append(message)
            scope = {'type':'http', 'asgi':{'version':'3.0'}, 'http_version':'1.1',
                     'method':method, 'scheme':'http', 'path':path, 'raw_path':path.encode(),
                     'query_string':b'', 'headers':[(b'content-type', b'application/json')],
                     'client':('127.0.0.1', 1), 'server':('test', 80), 'root_path':''}
            await app(scope, receive, send_message)
            status = next(m['status'] for m in messages if m['type']=='http.response.start')
            body = b''.join(m.get('body', b'') for m in messages if m['type']=='http.response.body').decode()
            return SimpleNamespace(status_code=status, text=body, json=lambda:json.loads(body))
        with patch.object(registros_longitudinais, "authorized_patient"):
            return asyncio.run(send())

    def test_http_neuro_create_get_patch(self):
        payload = dict(paciente_id=10, modulo_id=1, formulario_id=100,
                       data_registro=DAY.isoformat(), origem='PROFISSIONAL',
                       respostas=[{'campo_id':1000, 'valor':4}])
        response = self.request('POST', '/registros-longitudinais/', payload)
        self.assertEqual(response.status_code, 200, response.text)
        record_id = response.json()['id']
        self.assertEqual(response.json()['status'], 'ok')
        response = self.request('GET', '/registros-longitudinais/'+str(record_id), None)
        self.assertEqual(response.json()['respostas']['sono_qualidade'], 4)
        payload['respostas'][0]['valor'] = 2
        response = self.request('PATCH', '/registros-longitudinais/'+str(record_id), payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['respostas']['sono_qualidade'], 2)

    def test_http_cross_form_rejected(self):
        payload = dict(paciente_id=10, modulo_id=1, formulario_id=100,
                       data_registro=DAY.isoformat(), origem='PROFISSIONAL',
                       respostas=[{'campo_id':2000, 'valor':4}])
        response = self.request('POST', '/registros-longitudinais/', payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.count(), (0, 0))

    def test_non_daily_still_uses_legacy_service(self):
        with patch.object(registros_longitudinais, 'is_daily', return_value=False), \
             patch.object(registros_longitudinais, 'criar_registro_longitudinal', return_value=SimpleNamespace(id=77)) as legacy, \
             patch.object(registros_longitudinais, "authorized_patient"):
            result = registros_longitudinais.criar_registro(SimpleNamespace(formulario_id=90,paciente_id=10,modulo_id=1), self.db)
            self.assertEqual(result, {'id':77, 'status':'ok'})
            legacy.assert_called_once()

    def test_cardio_adapter_explicit_date_and_shape(self):
        payload = RegistroDiarioCardio(paciente_id=10, peso=100, atividade_fisica='baixa')
        with patch.object(cardiometabolico, 'authorized_patient'):
            result = cardiometabolico.criar_registro_diario(payload, self.db, SimpleNamespace(id=7))
        self.assertEqual(set(result), {'message', 'registro_id'})
        from app.models.modular import RegistroLongitudinal
        self.assertEqual(self.db.query(RegistroLongitudinal).one().data_registro, date.today())

    def test_responsible_adapter_context_and_shape(self):
        from app.models.modular import RegistroLongitudinal
        # Authorization and active patient lookup are exercised as adapter prerequisites;
        # no operational patient table is read.
        actual_query = self.db.query
        def query(model, *args):
            if model is responsavel_registros.Paciente:
                mock = unittest.mock.MagicMock()
                mock.filter.return_value.with_for_update.return_value.first.return_value = SimpleNamespace(id=10)
                return mock
            return actual_query(model, *args)
        with patch.object(responsavel_registros, 'validar_vinculo_ativo', return_value=True), \
             patch.object(self.db, 'query', side_effect=query):
            result = responsavel_registros.criar_registro_meu_paciente(10,
                RegistroDiarioResponsavelCreate(data=date.today(), sono_qualidade=4),
                self.db, SimpleNamespace(id=99))
        self.assertEqual(result['origem'], 'RESPONSAVEL_APP')
        self.assertEqual(result['sono_qualidade'], 4)
        self.assertEqual(self.db.query(RegistroLongitudinal).one().criado_por_responsavel_id, 99)
