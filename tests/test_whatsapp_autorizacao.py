"""E12C: persisted opt-in evidence on disposable PG; external transport simulated."""
import json
import unittest
from hashlib import sha256
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import select, text, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DBAPIError
from pydantic import ValidationError
from app.schemas.whatsapp_autorizacao import AuthorizationCreate, AuthorizationRevoke
from app.models.whatsapp_autorizacao import WhatsAppAutorizacaoComunicacao as Authorization
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio
from app.services.whatsapp_autorizacao import register, read, latest, require_prior_authorization
from app.services.whatsapp_mental import now_utc
from app.services.whatsapp_ingress import process_message
from app.services.checkin_bem_estar import CheckinDenied, CheckinInvalid
from app.services.whatsapp_manual import dispatch_manual
from app.schemas.whatsapp_manual import ManualRequest
import test_whatsapp_convite_envio as delivery
import test_whatsapp_convite_persistence as foundation


def evidence(stamp=None, **changes):
    reference='TEST-ONLY-EVIDENCE-'+uuid4().hex
    data=dict(origem='CANAL_EXTERNO',obtida_em=stamp or datetime.now(timezone.utc),
        referencia_evidencia=reference,evidencia_sha256=sha256(reference.encode()).hexdigest(),evidencia_verificada=True)
    data.update(changes)
    return AuthorizationCreate(**data)


class EvidenceContractTests(unittest.TestCase):
    def test_missing_invalid_and_unverified_evidence(self):
        good=evidence().model_dump()
        for field in good:
            with self.subTest(missing=field),self.assertRaises(ValidationError):
                AuthorizationCreate(**{k:v for k,v in good.items() if k!=field})
        for changes in ({'referencia_evidencia':' '},{'referencia_evidencia':'https://remote/doc?token=secret'},
                        {'evidencia_sha256':'not-a-hash'},{'evidencia_verificada':False},
                        {'evidencia_verificada':'true'},{'origem':'WHATSAPP_PARAR'},
                        {'obtida_em':datetime.now()},{'usuario_id':1},{'telefone':'invalid'},
                        {'estado':'AUTORIZADA'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):AuthorizationCreate(**dict(good,**changes))

    def test_equivalent_time_normalized(self):
        p=evidence()
        self.assertEqual(p.model_dump(mode='json'),AuthorizationCreate(**dict(p.model_dump(),
            obtida_em=p.obtida_em.astimezone(timezone(timedelta(hours=-4))))).model_dump(mode='json'))


@unittest.skipUnless(foundation.URL,'Disposable PostgreSQL required')
class AuthorizationTests(unittest.TestCase):
    create_prior_authorization=False
    setUpClass=classmethod(foundation.PersistenceTests.setUpClass.__func__)
    cleanup=classmethod(foundation.PersistenceTests.cleanup.__func__)
    snapshot=foundation.PersistenceTests.snapshot
    command_grant=foundation.PersistenceTests.command_grant
    path=foundation.PersistenceTests.path
    response=delivery.DeliveryTests.response
    send=delivery.DeliveryTests.send

    def setUp(self):
        delivery.DeliveryTests.setUp(self)
        self.aid=self.db.get(Conversation,self.cid).acompanhamento_whatsapp_id
        self.db.rollback()
        self.key=uuid4().hex
        self.payload=evidence(now_utc(self.db))
        self.db.rollback()

    def grant(self,db=None,key=None,payload=None):
        db=db or self.db
        out=register(db,self.scope,key or self.key,payload or self.payload);db.commit();return out

    def revoke(self,db=None,key=None):
        db=db or self.db
        out=register(db,self.scope,key or uuid4().hex,AuthorizationRevoke(motivo='SOLICITACAO_TITULAR'),revoke=True)
        db.commit();return out

    def rows(self):
        with Session(self.engine) as db:
            return list(db.scalars(select(Authorization).where(Authorization.acompanhamento_id==self.aid).order_by(Authorization.id)))

    def test_valid_persisted_evidence_and_acceptance_independent(self):
        out=self.grant()
        with Session(self.engine) as db:
            f=db.get(Follow,self.aid);a=require_prior_authorization(db,f)
            self.assertEqual(a.id,out['id']);self.assertEqual(a.usuario_id,self.actor)
            self.assertEqual(a.instituicao_id,self.institution);self.assertEqual(a.contexto_assistencial_id,self.open)
            self.assertEqual(a.referencia_evidencia,self.payload.referencia_evidencia)
            self.assertEqual(a.evidencia_sha256,self.payload.evidencia_sha256)
            self.assertEqual(f.consentimento_status,'PENDENTE');self.assertIsNone(f.consentido_em)
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()) as post:
            self.assertTrue(self.send());post.assert_called_once()
        with Session(self.engine) as db:
            attempt=db.scalar(select(Envio).where(Envio.conversa_id==self.cid))
            self.assertEqual(attempt.autorizacao_comunicacao_id,out['id'])

    def test_absent_even_after_sim_blocks_all_invites(self):
        for state in ('PENDENTE','CONSENTIDO'):
            f=self.db.get(Follow,self.aid);f.consentimento_status=state;self.db.commit()
            with patch('app.services.whatsapp_sender_service.requests.post') as post:
                with self.assertRaisesRegex(CheckinInvalid,'AUTHORIZATION_ABSENT'):self.send(retry=True)
                self.db.rollback()
                self.assertIsNone(self.service.prepare(self.db,self.aid));self.db.rollback()
                self.assertNotIn(self.aid,self.service.eligible_ids(self.db));self.db.rollback()
                with self.assertRaisesRegex(CheckinInvalid,'AUTHORIZATION_ABSENT'):
                    dispatch_manual(self.db,self.scope,uuid4().hex,ManualRequest(motivo='SOLICITACAO_DA_PESSOA'))
                self.db.rollback();post.assert_not_called()
        self.assertEqual(self.rows(),[])

    def test_no_historical_backfill(self):
        self.assertEqual(self.rows(),[])
        with Session(self.engine) as db:
            self.assertEqual(db.get(Follow,self.aid).consentimento_status,'PENDENTE')
        self.assertEqual(read(self.db,self.scope)['estado'],'AUSENTE');self.db.rollback()

    def test_manual_future_schedule_uses_real_authorization(self):
        self.grant()
        c=self.db.get(Conversation,self.cid);c.status='CONCLUIDA'
        f=self.db.get(Follow,self.aid);scheduled=self.now+timedelta(days=10);f.proximo_envio_em=scheduled;self.db.commit()
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()) as post:
            out=dispatch_manual(self.db,self.scope,uuid4().hex,ManualRequest(motivo='ACOMPANHAMENTO_EXTRAORDINARIO'))
            self.assertEqual(out['estado'],'ACEITO');post.assert_called_once()
        with Session(self.engine) as db:self.assertEqual(db.get(Follow,self.aid).proximo_envio_em,scheduled)

    def test_automatic_requires_authorization_and_preserves_schedule_policy(self):
        self.db.get(Conversation,self.cid).status='CONCLUIDA';self.db.commit()
        self.assertNotIn(self.aid,self.service.eligible_ids(self.db));self.db.rollback()
        self.grant()
        self.assertIn(self.aid,self.service.eligible_ids(self.db));self.db.rollback()
        c=self.service.prepare(self.db,self.aid);self.assertIsNotNone(c);self.db.commit()
        with Session(self.engine) as db:self.assertGreater(db.get(Follow,self.aid).proximo_envio_em,self.now)

    def test_revoke_preserves_acceptance_and_blocks_manual_auto_retry(self):
        self.grant();self.db.get(Follow,self.aid).consentimento_status='CONSENTIDO';self.db.commit()
        out=self.revoke();self.assertEqual(out['estado'],'REVOGADA')
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertFalse(self.send(retry=True));self.db.rollback()
            self.assertIsNone(self.service.prepare(self.db,self.aid));self.db.rollback()
            with self.assertRaisesRegex(CheckinInvalid,'AUTHORIZATION_REVOKED'):
                dispatch_manual(self.db,self.scope,uuid4().hex,ManualRequest(motivo='SOLICITACAO_DA_PESSOA'))
            self.db.rollback();post.assert_not_called()
        self.assertEqual([r.estado for r in self.rows()],['AUTORIZADA','REVOGADA'])
        with Session(self.engine) as db:
            self.assertEqual(db.get(Follow,self.aid).consentimento_status,'CONSENTIDO')
            self.assertEqual(db.get(Follow,self.aid).status,'ATIVO')

    def test_stop_records_authenticated_receipt_and_cannot_be_reauthorized(self):
        self.grant();identity='test-stop-'+uuid4().hex
        phone=self.db.get(Follow,self.aid).telefone;self.db.rollback()
        process_message(self.db,identity,'12345',phone,'PARAR')
        process_message(self.db,identity,'12345',phone,'PARAR')
        rows=self.rows();self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].estado,'AUTORIZADA')
        from app.services.whatsapp_comunicacao import read
        state=read(self.db,self.scope)
        self.assertEqual(state['estado'],'WHATSAPP_INTERROMPIDO')
        self.assertEqual(len(state['eventos']),1)
        self.assertEqual(self.db.get(Follow,self.aid).status,'ATIVO')
        self.db.rollback()

    def test_sim_does_not_create_or_change_prior_authorization(self):
        out=self.grant();before=self.rows()[0].registrado_em
        self.service.receive(self.db,self.cid,'SIM');self.db.commit()
        self.assertEqual(len(self.rows()),1);self.assertEqual(self.rows()[0].id,out['id'])
        self.assertEqual(self.rows()[0].registrado_em,before)
        self.assertEqual(self.db.get(Follow,self.aid).consentimento_status,'CONSENTIDO')

    def test_contextual_write_required_and_no_implicit_admin(self):
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:id'),{'id':self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']})
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:id"),{'id':self.actor});self.db.commit()
        with self.assertRaises(CheckinDenied):self.grant()
        self.db.rollback();self.assertEqual(self.rows(),[])

    def test_institution_and_person_isolation(self):
        for scope in (dict(self.scope,institution=2147483647),dict(self.scope,person=2147483647),dict(self.scope,context=self.closed)):
            with self.assertRaises(CheckinDenied):register(self.db,scope,self.key,self.payload)
            self.db.rollback()
        self.assertEqual(self.rows(),[])

    def test_future_evidence_rejected(self):
        with self.assertRaisesRegex(CheckinInvalid,'TIME_IN_FUTURE'):
            self.grant(payload=evidence(now_utc(self.db)+timedelta(days=1)))
        self.db.rollback();self.assertEqual(self.rows(),[])

    def test_idempotency_and_conflict(self):
        a=self.grant();b=self.grant();self.assertEqual(a['id'],b['id']);self.assertTrue(b['repetido'])
        with self.assertRaisesRegex(CheckinInvalid,'IDEMPOTENCY_CONFLICT'):self.grant(payload=evidence())
        self.db.rollback();self.assertEqual(len(self.rows()),1)

    def test_historical_replay_never_reauthorizes(self):
        a=self.grant();self.revoke();out=self.grant()
        self.assertEqual(out['id'],a['id']);self.assertEqual(out['estado_atual'],'REVOGADA')
        self.assertEqual(len(self.rows()),2)

    def test_new_authorization_requires_new_evidence_after_revocation(self):
        self.grant();self.revoke()
        with self.assertRaisesRegex(CheckinInvalid,'NEW_AUTHORIZATION_EVIDENCE_REQUIRED'):self.grant(key=uuid4().hex)
        self.db.rollback()
        with self.assertRaisesRegex(CheckinInvalid,'EVIDENCE_ALREADY_USED'):
            self.grant(key=uuid4().hex,payload=AuthorizationCreate(**dict(self.payload.model_dump(),obtida_em=now_utc(self.db))))
        self.db.rollback()
        out=self.grant(key=uuid4().hex,payload=evidence(now_utc(self.db)))
        self.assertEqual(out['estado_atual'],'AUTORIZADA');self.assertEqual(len(self.rows()),3)

    def test_concurrent_same_request_one_ledger_event(self):
        def run():
            with Session(self.engine) as db:return self.grant(db)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
        self.assertEqual(results[0]['id'],results[1]['id']);self.assertEqual(len(self.rows()),1)

    def test_concurrent_distinct_grants_no_double_authorization(self):
        def run():
            with Session(self.engine) as db:
                try:return self.grant(db,key=uuid4().hex)['estado']
                except CheckinInvalid as exc:db.rollback();return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
        self.assertCountEqual(results,['AUTORIZADA','AUTHORIZATION_ALREADY_ACTIVE']);self.assertEqual(len(self.rows()),1)

    def test_concurrent_revocation_single_event(self):
        self.grant();key=uuid4().hex
        def run():
            with Session(self.engine) as db:return self.revoke(db,key)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
        self.assertEqual(results[0]['id'],results[1]['id']);self.assertEqual(len(self.rows()),2)

    def test_revocation_between_transport_preparation_and_execution(self):
        self.grant();commit=self.db.commit;count=0
        def revoke_after_commit():
            nonlocal count
            count+=1;commit()
            if count==1:
                with Session(self.engine) as db:self.revoke(db)
        with patch.object(self.db,'commit',side_effect=revoke_after_commit),patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertFalse(self.send());post.assert_not_called()
        self.db.rollback()
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(Envio.estado).where(Envio.conversa_id==self.cid)),'PREPARADO')

    def test_phone_change_revokes_and_does_not_transfer_evidence(self):
        self.grant();self.db.get(Conversation,self.cid).status='CONCLUIDA';self.db.commit()
        self.service.configure(self.db,'5588'+str(self.cid).zfill(9),**self.scope);self.db.commit()
        self.assertEqual(self.rows()[-1].origem,'TROCA_TELEFONE')
        self.assertIsNone(self.service.prepare(self.db,self.aid));self.db.rollback()

    def test_destination_fingerprint_protects_noncanonical_phone_change(self):
        self.grant();self.db.get(Follow,self.aid).telefone='5577'+str(self.cid).zfill(9);self.db.commit()
        with self.assertRaisesRegex(CheckinInvalid,'DESTINATION_CHANGED'):require_prior_authorization(self.db,self.db.get(Follow,self.aid))
        self.db.rollback();self.assertNotIn(self.aid,self.service.eligible_ids(self.db));self.db.rollback()

    def test_closing_followup_appends_revocation(self):
        self.grant();self.service.lifecycle(self.db,'encerrar',**self.scope);self.db.commit()
        self.assertEqual(self.rows()[-1].origem,'ENCERRAMENTO')

    def test_history_is_immutable_and_context_foreign_keys(self):
        out=self.grant()
        for sql in ('UPDATE whatsapp_autorizacoes_comunicacao SET estado=estado WHERE id=:i',
                    'DELETE FROM whatsapp_autorizacoes_comunicacao WHERE id=:i'):
            with self.assertRaises(DBAPIError),self.db.begin_nested():self.db.execute(text(sql),{'i':out['id']})
        with self.assertRaises(IntegrityError),self.db.begin_nested():
            self.db.add(Authorization(acompanhamento_id=self.aid,contexto_assistencial_id=self.open,
                paciente_id=self.db.get(Follow,self.aid).paciente_id,instituicao_id=2147483647,
                anterior_id=out['id'],estado='REVOGADA',origem='PORTAL_PROFISSIONAL',
                ocorrido_em=now_utc(self.db),usuario_id=self.actor,destino_sha256='0'*64,motivo='ERRO_REGISTRO'))
            self.db.flush()
        self.db.rollback();self.assertEqual(len(self.rows()),1)

    def test_lost_commit_response_reconciles_by_same_key(self):
        commit=self.db.commit
        def lost():commit();raise RuntimeError('lost')
        with patch.object(self.db,'commit',side_effect=lost):
            with self.assertRaises(RuntimeError):self.grant()
        self.db.rollback();out=self.grant();self.assertTrue(out['repetido']);self.assertEqual(len(self.rows()),1)

    def test_failure_before_commit_rolls_back_entire_event(self):
        with patch.object(self.db,'commit',side_effect=RuntimeError('not committed')):
            with self.assertRaises(RuntimeError):self.grant()
        self.db.rollback();self.assertEqual(self.rows(),[])

    def test_http_create_read_revoke_validation(self):
        from app.routers.whatsapp_mental import router
        self.app.include_router(router)
        base=f'/saude-mental/pessoas/{self.person}/contextos/{self.open}/whatsapp/autorizacao-comunicacao'
        def call(method,suffix='',body=None,key=None):
            return self.client.request(method,base+suffix,params={'instituicao_id':self.institution},
                body=json.dumps(body or {}).encode(),headers={'Content-Type':'application/json',**({'Idempotency-Key':key} if key else {})})
        self.assertEqual(call('POST',body=self.payload.model_dump(mode='json')).status_code,422)
        self.assertEqual(call('POST',body={},key=self.key).status_code,422)
        ok=call('POST',body=self.payload.model_dump(mode='json'),key=self.key);self.assertEqual(ok.status_code,200,ok.text)
        self.assertEqual(call('GET').json()['estado'],'AUTORIZADA')
        revoked=call('POST','/revogar',{'motivo':'SOLICITACAO_TITULAR'},uuid4().hex)
        self.assertEqual(revoked.status_code,200,revoked.text)
        out=call('GET');self.assertEqual(out.json()['estado'],'REVOGADA');self.assertEqual(len(out.json()['historico']),2)
        self.assertNotIn('destino_sha256',out.text);self.assertNotIn('telefone',out.text)

    def test_sim_without_prior_evidence_never_registers_authorization(self):
        self.service.receive(self.db,self.cid,'SIM');self.db.commit()
        self.assertEqual(self.db.get(Follow,self.aid).consentimento_status,'CONSENTIDO')
        self.assertEqual(self.rows(),[])
        with self.assertRaisesRegex(CheckinInvalid,'AUTHORIZATION_ABSENT'):
            require_prior_authorization(self.db,self.db.get(Follow,self.aid))
        self.db.rollback()

    def test_delivery_callback_cannot_authorize_communication(self):
        from app.services.whatsapp_convite_status import parse_statuses,persist_statuses
        rows=parse_statuses({'statuses':[{'id':self.wamid,'status':'failed',
            'timestamp':str(int(self.now.timestamp())),'errors':[{'code':131049}]}]},'12345')
        persist_statuses(self.db,rows)
        self.assertEqual(self.rows(),[])
        self.assertEqual(self.db.get(Follow,self.aid).consentimento_status,'PENDENTE')
        self.db.rollback()

    def test_authorization_read_requires_contextual_read_permission(self):
        self.grant()
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:id'),{'id':self.grant_ids[self.open,'ASSISTENCIAL_LER']});self.db.commit()
        with self.assertRaises(CheckinDenied):read(self.db,self.scope)
        self.db.rollback()

    def test_http_requires_authentication(self):
        from fastapi import FastAPI
        from app.routers.whatsapp_mental import router
        from test_whatsapp_security import LocalClient
        app=FastAPI();app.include_router(router)
        client=LocalClient(app)
        for method,suffix,body in (('GET','',{}),('POST','',self.payload.model_dump(mode='json')),
                                  ('POST','/revogar',{'motivo':'SOLICITACAO_TITULAR'})):
            r=client.request(method,f'/saude-mental/pessoas/{self.person}/contextos/{self.open}/whatsapp/autorizacao-comunicacao'+suffix,
                params={'instituicao_id':self.institution},body=json.dumps(body).encode(),
                headers={'Content-Type':'application/json','Idempotency-Key':self.key})
            self.assertIn(r.status_code,(401,403))


@unittest.skipUnless(foundation.URL,'Disposable PostgreSQL required')
class AuthorizationMigrationTests(unittest.TestCase):
    setUpClass=classmethod(foundation.PersistenceTests.setUpClass.__func__)
    cleanup=classmethod(foundation.PersistenceTests.cleanup.__func__)
    snapshot=foundation.PersistenceTests.snapshot
    command_grant=foundation.PersistenceTests.command_grant
    path=foundation.PersistenceTests.path

    def setUp(self):
        # Exercise the real E12B -> E12C upgrade with pre-existing accepted evidence.
        with patch.object(foundation,'HEAD','d92e12_whatsapp_manual'):
            foundation.PersistenceTests.setUp(self)

    def test_additive_upgrade_preserves_historical_acceptance_without_optin(self):
        from alembic import command
        from test_m0_baseline import config
        aid=self.db.execute(text("INSERT INTO whatsapp_convite_envios(conversa_id,tentativa,correlacao_id,phone_number_id,wamid,estado,confirmado_em) VALUES (:c,1,:key,'test-emitter',:wamid,'ACEITO',clock_timestamp()) RETURNING id"),
            {'c':self.cid,'key':str(uuid4()),'wamid':'wamid.'+uuid4().hex}).scalar_one()
        self.db.commit()
        with self.engine.connect() as c:
            tables=set(inspect(c).get_table_names())
            before=c.execute(text('SELECT row_to_json(t)::jsonb FROM whatsapp_convite_envios t WHERE id=:id'),{'id':aid}).scalar_one()
        with self.engine.begin() as c:command.upgrade(config(c),'d92e12c_autorizacao_whatsapp')
        with self.engine.connect() as c:
            after=c.execute(text('SELECT row_to_json(t)::jsonb FROM whatsapp_convite_envios t WHERE id=:id'),{'id':aid}).scalar_one()
            self.assertIsNone(after.pop('autorizacao_comunicacao_id'))
            self.assertEqual(after,before)
            self.assertEqual(set(inspect(c).get_table_names())-tables,{'whatsapp_autorizacoes_comunicacao'})
            self.assertEqual(c.execute(text('SELECT count(*) FROM whatsapp_autorizacoes_comunicacao')).scalar_one(),0)
            self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),'d92e12c_autorizacao_whatsapp')
            fk=next(f for f in inspect(c).get_foreign_keys('whatsapp_convite_envios') if f['name']=='fk_wce_autorizacao')
            self.assertEqual(fk['referred_table'],'whatsapp_autorizacoes_comunicacao')
