"""Dormant resolver on migrated, owned PostgreSQL databases. No external HTTP."""
import hashlib
import json
import unittest
from datetime import date, timedelta
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, text, event
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import test_whatsapp_convite_envio as delivery
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Mental
from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel as Evidence
from app.models.whatsapp_conversa import WhatsAppConversa as Legacy
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.models.whatsapp_resolucao import WhatsAppResolucao as Audit
from app.services.whatsapp_multilinhas import resolve, record_proposal
from app.services.whatsapp_transporte import capture


@unittest.skipUnless(delivery.foundation.URL, 'Exclusive disposable PostgreSQL required')
class MultilineTests(unittest.TestCase):
    setUpClass = classmethod(delivery.DeliveryTests.setUpClass.__func__)
    cleanup = classmethod(delivery.DeliveryTests.cleanup.__func__)
    snapshot = delivery.DeliveryTests.snapshot
    command_grant = delivery.DeliveryTests.command_grant
    path = delivery.DeliveryTests.path

    def setUp(self):
        self.create_prior_authorization = self._testMethodName not in ("test_absent_authorization", "test_brazilian_ninth_digit_requires_meta_bridge")
        delivery.DeliveryTests.setUp(self)
        self.phone = self.db.get(Mental, self.cid).telefone
        self.sender = '5565' + str(self.cid).zfill(8)  # Synthetic representation, no personal fixture.

    def evidence(self, *, mental=None, legacy=None, phone=None, sender=None, emitter='12345'):
        result = capture(self.db, {'messages':[{'id':'wamid.'+uuid4().hex}],
            'contacts':[{'input':phone or self.phone,'wa_id':sender or self.sender}]},
            emitter=emitter, requested=phone or self.phone, contextual=mental, legacy=legacy, origin='META_RESPOSTA' if legacy else 'META_CONVITE')
        self.db.commit()
        return result

    def legacy(self, line='NEURO', phone=None):
        from app.models.responsavel import Responsavel
        from app.models.responsavel_paciente import ResponsavelPaciente
        from app.models.paciente import Paciente
        from app.models.modular import PacienteModulo, ModuloClinico
        patient = self.db.get(Paciente, self.db.get(Mental,self.cid).paciente_id)
        patient.ativo=True
        responsible = Responsavel(nome='Synthetic',email=uuid4().hex+'@example.invalid',
            senha_hash='unused',telefone=phone or self.phone,ativo=True,clinica_id=patient.clinica_id)
        self.db.add(responsible);self.db.flush()
        self.db.add(ResponsavelPaciente(responsavel_id=responsible.id,paciente_id=patient.id,ativo=True))
        module = 1 if line == 'NEURO' else 2
        if not self.db.get(ModuloClinico,module):
            self.db.add(ModuloClinico(id=module,nome='Synthetic '+line,slug=line.lower(),ativo=True));self.db.flush()
        if not self.db.scalar(select(PacienteModulo).where(PacienteModulo.paciente_id==patient.id,PacienteModulo.modulo_id==module)):
            self.db.add(PacienteModulo(paciente_id=patient.id,modulo_id=module,ativo=True))
        c = Legacy(responsavel_id=responsible.id,paciente_id=patient.id,telefone=responsible.telefone,
            care_line=line,etapa_atual='SONO' if line=='NEURO' else 'CARDIO_0',data_referencia=date.today())
        self.db.add(c);self.db.commit()
        return c

    def decision(self, sender=None, content='SIM', emitter='12345'):
        return resolve(self.db,emitter,sender or self.sender,content)

    def receipt(self, content='SIM'):
        mid='test-'+uuid4().hex
        fingerprint=hashlib.sha256(json.dumps(['12345',self.sender,content,None],ensure_ascii=False).encode()).hexdigest()
        self.db.add(Receipt(message_id=mid,phone_number_id='12345',fingerprint=fingerprint,
            fingerprint_versao=2,resposta=''))
        self.db.commit()
        return mid

    def test_mental_proven_alias(self):
        self.evidence(mental=self.cid)
        self.assertEqual(self.decision().selected,('MENTAL',self.cid))

    def test_exact_without_evidence(self):
        self.assertEqual(self.decision(sender=self.phone).selected,('MENTAL',self.cid))

    def test_no_alias_inference(self):
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_other_emitter_not_identity_evidence(self):
        self.evidence(mental=self.cid,emitter='99999')
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_contradiction_no_latest_wins(self):
        self.evidence(mental=self.cid)
        self.evidence(mental=self.cid,sender='551100000002')
        self.assertEqual(self.decision().outcome,'IDENTIDADE_RECUSADA')

    def test_invalid_evidence_no_exact_bypass(self):
        e=self.evidence(mental=self.cid)
        e.evidencia_estado='INVALIDA';e.wa_id=None;self.db.commit()
        self.assertEqual(self.decision(sender=self.phone).outcome,'IDENTIDADE_RECUSADA')

    def test_expiry_does_not_mutate(self):
        self.evidence(mental=self.cid)
        now=self.db.execute(text('SELECT clock_timestamp()')).scalar()
        result=resolve(self.db,'12345',self.sender,'SIM',now=now+timedelta(days=2))
        self.assertEqual(result.outcome,'INDISPONIVEL')
        self.assertEqual(self.db.get(Mental,self.cid).status,'AGUARDANDO_ACEITE')

    def test_changed_destination(self):
        self.evidence(mental=self.cid)
        self.db.execute(text("UPDATE acompanhamentos_whatsapp SET telefone='551100000003' WHERE contexto_assistencial_id=:c"),{'c':self.open});self.db.commit()
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_revoked_authorization_sim_does_not_restore(self):
        self.evidence(mental=self.cid)
        self.db.execute(text("UPDATE acompanhamentos_whatsapp SET consentimento_status='REVOGADO' WHERE contexto_assistencial_id=:c"),{'c':self.open});self.db.commit()
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_absent_authorization(self):
        self.evidence(mental=self.cid)
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_inactive_institution(self):
        self.evidence(mental=self.cid)
        self.db.execute(text('UPDATE instituicoes SET ativo=false WHERE id=:i'),{'i':self.institution});self.db.commit()
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_mental_neuro_ambiguity(self):
        self.evidence(mental=self.cid)
        c=self.legacy();self.evidence(legacy=c.id)
        result=self.decision()
        self.assertEqual(result.outcome,'AMBIGUA');self.assertIsNone(result.selected)
        self.assertNotIn(str(self.person),result.response)

    def test_unique_neuro(self):
        c=self.legacy(phone='551100000004');self.evidence(legacy=c.id,phone=c.telefone)
        self.assertEqual(self.decision().selected,('LEGADO',c.id))

    def test_unique_cardio(self):
        c=self.legacy('CARDIO',phone='551100000005');self.evidence(legacy=c.id,phone=c.telefone)
        self.assertEqual(self.decision().selected,('LEGADO',c.id))

    def test_neuro_cardio_ambiguity(self):
        for line in ('NEURO','CARDIO'):
            c=self.legacy(line,phone='551100000006');self.evidence(legacy=c.id,phone=c.telefone)
        self.assertEqual(self.decision().outcome,'AMBIGUA')

    def test_duplicate_evidence_is_one_candidate(self):
        self.evidence(mental=self.cid);self.evidence(mental=self.cid)
        self.assertEqual(len(self.decision().candidates),1)
        self.assertEqual(self.decision().outcome,'UNICA')

    def test_legacy_reused_episode(self):
        c=self.legacy(phone='551100000007');self.evidence(legacy=c.id,phone=c.telefone)
        c.etapa_atual='CONFIRMACAO';self.db.commit()
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_legacy_expired_date(self):
        c=self.legacy(phone='551100000008');c.data_referencia=date.today()-timedelta(days=3);self.db.commit()
        self.evidence(legacy=c.id,phone=c.telefone)
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_legacy_inactive_link(self):
        c=self.legacy(phone='551100000009');self.evidence(legacy=c.id,phone=c.telefone)
        self.db.execute(text('UPDATE responsavel_paciente SET ativo=false WHERE responsavel_id=:r'),{'r':c.responsavel_id});self.db.commit()
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_parar_never_dispatches_or_revokes(self):
        self.evidence(mental=self.cid)
        self.assertEqual(self.decision(content='PARAR').outcome,'PARAR_REQUER_BLOQUEIO_3B')
        self.assertEqual(self.db.get(Mental,self.cid).status,'AGUARDANDO_ACEITE')

    def test_collection_is_sql_read_only(self):
        self.evidence(mental=self.cid)
        self.db.rollback()
        self.db.execute(text('SET TRANSACTION READ ONLY'))
        statements=[]
        def observe(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',observe)
        try:self.assertEqual(self.decision().outcome,'UNICA')
        finally:event.remove(self.engine,'before_cursor_execute',observe)
        self.assertFalse(any('FOR UPDATE' in s.upper() or 'ADVISORY' in s.upper() for s in statements))
        self.db.rollback()

    def test_dirty_session_refused_without_autoflush(self):
        self.db.get(Mental,self.cid).status='CONCLUIDA'
        with self.assertRaises(ValueError):self.decision()
        self.db.rollback()

    def test_audit_replay_keeps_original_decision(self):
        self.evidence(mental=self.cid);mid=self.receipt()
        first=record_proposal(self.db,mid,'12345',self.sender,'SIM');self.db.commit()
        self.db.get(Mental,self.cid).status='CONCLUIDA';self.db.commit()
        self.assertEqual(record_proposal(self.db,mid,'12345',self.sender,'SIM'),first)
        with self.assertRaises(ValueError):record_proposal(self.db,mid,'99999',self.sender,'SIM')
        self.db.rollback()
        with Session(self.engine) as db:
            self.assertEqual(db.get(Audit,mid).decisao,first)
            self.assertNotIn(self.sender,json.dumps(first))

    def test_concurrent_audit_replay(self):
        self.evidence(mental=self.cid);mid=self.receipt();self.db.rollback()
        def call(_):
            with Session(self.engine) as db:
                result=record_proposal(db,mid,'12345',self.sender,'SIM');db.commit();return result
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(call,range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(self.db.query(Audit).filter_by(message_id=mid).count(),1)

    def test_audit_rollback(self):
        self.evidence(mental=self.cid);mid=self.receipt()
        record_proposal(self.db,mid,'12345',self.sender,'SIM');self.db.rollback()
        self.assertIsNone(self.db.get(Audit,mid))

    def test_audit_fk(self):
        with self.assertRaises(IntegrityError):
            self.db.add(Audit(message_id='missing',decisao={}));self.db.flush()
        self.db.rollback()

    def test_no_activation_and_index_preserved(self):
        from app.services.whatsapp_ingress import process_message
        mid='live-'+uuid4().hex
        process_message(self.db,mid,'12345',self.phone,'SIM')
        self.assertEqual(self.db.get(Receipt,mid).resolucao,'CONTEXTUAL_ATUAL')
        self.assertIsNone(self.db.get(Audit,mid))
        self.assertTrue(self.db.execute(text("SELECT 1 FROM pg_indexes WHERE indexname='uq_wcc_aberta_telefone'")).scalar())

    def test_safe_fallback_only_bound_exact_responsible(self):
        c=self.legacy(phone='551100000010');responsible=c.responsavel_id
        self.db.delete(c);self.db.commit()
        d=self.decision(sender='551100000010',content='oi')
        self.assertEqual((d.outcome,d.fallback_responsible_id),('FALLBACK_SEGURO',responsible))
        self.assertEqual(self.decision(sender='551100000010',content='SIM').outcome,'INDISPONIVEL')

    def test_brazilian_ninth_digit_requires_meta_bridge(self):
        phone='55119'+str(self.cid).zfill(8)
        sender='5511'+str(self.cid).zfill(8)
        self.db.execute(text('UPDATE acompanhamentos_whatsapp SET telefone=:p WHERE contexto_assistencial_id=:c'),{'p':phone,'c':self.open})
        self.db.get(Mental,self.cid).telefone=phone;self.db.commit()
        from whatsapp_authorization_fixture import authorize_follow
        authorize_follow(self.db,self.scope)
        self.assertIsNone(self.decision(sender=sender).selected)
        self.evidence(mental=self.cid,phone=phone,sender=sender)
        self.assertEqual(self.decision(sender=sender).selected,('MENTAL',self.cid))

    def test_legacy_cross_institution_denied(self):
        from app.models.clinica import Clinica
        from app.models.responsavel import Responsavel
        c=self.legacy(phone='551100000011');self.evidence(legacy=c.id,phone=c.telefone)
        other=Clinica(nome='Synthetic other');self.db.add(other);self.db.flush()
        self.db.get(Responsavel,c.responsavel_id).clinica_id=other.id;self.db.commit()
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_patient_institution_link_revoked(self):
        self.evidence(mental=self.cid)
        self.db.execute(text('UPDATE paciente_instituicoes SET ativo=false WHERE id=(SELECT paciente_instituicao_id FROM contextos_assistenciais WHERE id=:c)'),{'c':self.open});self.db.commit()
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_ambiguity_persisted_without_selected_conversation(self):
        self.evidence(mental=self.cid)
        c=self.legacy();self.evidence(legacy=c.id)
        mid=self.receipt()
        audit=record_proposal(self.db,mid,'12345',self.sender,'SIM');self.db.commit()
        self.assertEqual(audit['outcome'],'AMBIGUA');self.assertIsNone(audit['selected'])
        with Session(self.engine) as db:self.assertEqual(db.get(Audit,mid).decisao,audit)

    def test_audit_immutable(self):
        from sqlalchemy.exc import DBAPIError
        self.evidence(mental=self.cid);mid=self.receipt()
        record_proposal(self.db,mid,'12345',self.sender,'SIM');self.db.commit()
        for statement in ('DELETE FROM whatsapp_resolucoes WHERE message_id=:m',
                          "UPDATE whatsapp_resolucoes SET decisao='{}'::jsonb WHERE message_id=:m"):
            with self.assertRaises(DBAPIError):self.db.execute(text(statement),{'m':mid})
            self.db.rollback()

    def test_legacy_unknown_step_refused(self):
        c=self.legacy(phone='551100000012');c.etapa_atual='UNKNOWN';self.db.commit()
        self.evidence(legacy=c.id,phone=c.telefone)
        self.assertEqual(self.decision().outcome,'INDISPONIVEL')

    def test_pending_follow_prevents_new_legacy_fallback(self):
        c=self.legacy();self.db.delete(c);self.db.commit()
        self.db.get(Mental,self.cid).status='CONCLUIDA';self.db.commit()
        self.assertEqual(self.decision(sender=self.phone,content='oi').outcome,'INDISPONIVEL')
