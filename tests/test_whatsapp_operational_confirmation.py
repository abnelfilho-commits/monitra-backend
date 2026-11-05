"""Operational E12C; real disposable PG18 and existing external-evidence regressions."""
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from alembic import command
from pydantic import ValidationError
from app.schemas.whatsapp_autorizacao import OperationalConfirmation, AuthorizationCreate
from app.services.whatsapp_autorizacao import register, read
from app.services.checkin_bem_estar import CheckinDenied, CheckinInvalid
from test_m0_baseline import config
import test_whatsapp_autorizacao as external


def payload(**changes):
    data = dict(modalidade='PRESENCIAL', obtida_em=datetime.now(timezone.utc)-timedelta(minutes=1),
                permissao_previa_identificada=True, atestacao=True)
    data.update(changes)
    return OperationalConfirmation(**data)


class ContractTests(unittest.TestCase):
    def test_no_defaults_fabrication_or_implicit_confirmation(self):
        good = payload().model_dump()
        for key in good:
            with self.assertRaises(ValidationError):
                OperationalConfirmation(**{k:v for k,v in good.items() if k != key})
        for changes in ({'modalidade':'OUTRO'}, {'atestacao':False}, {'atestacao':'true'},
                        {'permissao_previa_identificada':False}, {'obtida_em':datetime.now()},
                        {'usuario_id':1}, {'telefone':'12345678'}):
            with self.assertRaises(ValidationError):
                payload(**changes)
        with self.assertRaises(ValidationError):
            AuthorizationCreate(**good)


@unittest.skipUnless(external.foundation.URL, 'Explicit disposable PostgreSQL required')
class OperationalTests(external.AuthorizationTests):
    # Run the complete inherited E12C regression matrix on the extended schema too.
    def setUp(self):
        super().setUp()
        with self.engine.begin() as connection:
            command.upgrade(config(connection), 'mh_e12c_operacional_v1')

    def test_operational_persistence_idempotence_and_consent_independent(self):
        initial_consent = self.db.execute(text('SELECT consentimento_status FROM acompanhamentos_whatsapp WHERE id=:id'), {'id':self.aid}).scalar()
        self.db.rollback()
        p = payload()
        out = register(self.db, self.scope, self.key, p); self.db.commit()
        self.assertEqual(out['origem'], 'CONFIRMACAO_OPERACIONAL')
        self.assertEqual(out['modalidade'], 'PRESENCIAL')
        self.assertIsNone(out['referencia_evidencia'])
        self.assertIsNone(out['evidencia_sha256'])
        self.assertEqual(out['usuario_id'], self.actor)
        self.assertEqual(register(self.db, self.scope, self.key, p)['id'], out['id'])
        self.db.commit()
        state = read(self.db, self.scope)
        self.assertEqual(state['estado'], 'AUTORIZADA')
        self.assertEqual(state['historico'][-1]['chave'], self.key)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM whatsapp_confirmacoes_operacionais WHERE autorizacao_id=:id'), {'id':out['id']}).scalar(), 1)
        self.assertEqual(self.db.execute(text('SELECT consentimento_status FROM acompanhamentos_whatsapp WHERE id=:id'), {'id':self.aid}).scalar(), initial_consent)
        self.db.rollback()
        with self.assertRaises(CheckinInvalid):
            register(self.db, self.scope, self.key, payload(modalidade='TELEFONE'))
        self.db.rollback()
        self.revoke()
        self.assertEqual(read(self.db, self.scope)['estado'], 'REVOGADA')
        self.db.rollback()
        self.assertEqual(register(self.db, self.scope, self.key, p)['estado_atual'], 'REVOGADA')
        self.db.rollback()

    def test_operational_future_denied_and_isolation(self):
        with self.assertRaises(CheckinInvalid):
            register(self.db, self.scope, self.key, payload(obtida_em=datetime.now(timezone.utc)+timedelta(days=1)))
        self.db.rollback()
        with self.assertRaises(CheckinDenied):
            register(self.db, dict(self.scope, institution=2147483647), self.key, payload())
        self.db.rollback()

    def test_operational_audit_immutable_and_atomic_rollback(self):
        out = register(self.db, self.scope, self.key, payload())
        self.db.rollback()
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM whatsapp_confirmacoes_operacionais WHERE autorizacao_id=:id'), {'id':out['id']}).scalar(), 0)
        self.db.rollback()
        out = register(self.db, self.scope, self.key, payload()); self.db.commit()
        with self.assertRaises(DBAPIError):
            self.db.execute(text('DELETE FROM whatsapp_confirmacoes_operacionais WHERE autorizacao_id=:id'), {'id':out['id']})
        self.db.rollback()

    def test_operational_http_contract_and_readback(self):
        import json
        from app.routers.whatsapp_mental import router
        self.app.include_router(router)
        base=f'/saude-mental/pessoas/{self.person}/contextos/{self.open}/whatsapp'
        response=self.client.request('POST',base+'/confirmacao-operacional',
            params={'instituicao_id':self.institution},
            body=json.dumps(payload().model_dump(mode='json')).encode(),
            headers={'Content-Type':'application/json','Idempotency-Key':self.key})
        self.assertEqual(response.status_code,200,response.text)
        state=self.client.request('GET',base+'/autorizacao-comunicacao',params={'instituicao_id':self.institution})
        self.assertEqual(state.status_code,200)
        self.assertEqual(state.json()['historico'][-1]['id'],response.json()['id'])
        self.assertEqual(state.json()['historico'][-1]['modalidade'],'PRESENCIAL')

    def test_operational_concurrency_creates_one_event(self):
        from concurrent.futures import ThreadPoolExecutor
        from sqlalchemy.orm import Session
        p = payload()
        def operation():
            with Session(self.engine) as db:
                out=register(db,self.scope,self.key,p);db.commit();return out['id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:operation(),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(len(self.rows()),1)

    def test_metadata_required_at_commit(self):
        from app.services.whatsapp_autorizacao import append_event
        from app.models.whatsapp_contextual import AcompanhamentoWhatsApp
        append_event(self.db,self.db.get(AcompanhamentoWhatsApp,self.aid),state='AUTORIZADA',
                     origin='CONFIRMACAO_OPERACIONAL',occurred=datetime.now(timezone.utc),
                     actor=self.actor,key=uuid4().hex,fingerprint='a'*64)
        with self.assertRaises(DBAPIError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.rows(),[])
