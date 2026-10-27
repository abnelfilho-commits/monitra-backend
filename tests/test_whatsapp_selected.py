"""Dormant orchestration on disposable PostgreSQL; no external transport."""
import unittest
from uuid import uuid4
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException
import test_whatsapp_multilinhas as fixture
from app.services.whatsapp_selected import process_selected, propose
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.models.whatsapp_resolucao import WhatsAppResolucao as Audit
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Mental

@unittest.skipUnless(fixture.delivery.foundation.URL, 'Owned disposable PostgreSQL required')
class SelectedTests(unittest.TestCase):
    setUpClass = fixture.MultilineTests.__dict__['setUpClass']
    cleanup = fixture.MultilineTests.__dict__['cleanup']
    snapshot = fixture.MultilineTests.snapshot
    command_grant = fixture.MultilineTests.command_grant
    path = fixture.MultilineTests.path
    setUp = fixture.MultilineTests.setUp
    evidence = fixture.MultilineTests.evidence
    legacy = fixture.MultilineTests.legacy

    def run_message(self, content='SIM', reference=None, sender=None, mid=None, db=None):
        self.mid = mid or 'selected-'+uuid4().hex
        return process_selected(db or self.db,self.mid,'12345',sender or self.sender,content,reference)
    def outcome(self):
        return self.db.get(Audit,self.mid,populate_existing=True).decisao['outcome']
    def test_unique_mental(self):
        self.evidence(mental=self.cid)
        self.run_message()
        self.assertEqual(self.outcome(),'SELECIONADA')
        self.assertEqual(self.db.get(Mental,self.cid).status,'EM_ANDAMENTO')
    def test_reference_mental(self):
        e=self.evidence(mental=self.cid)
        self.run_message(reference=e.wamid)
        self.assertEqual(self.db.get(Receipt,self.mid).resolucao,'REFERENCIA_CONTEXTUAL')
    def test_reference_unknown_no_fallback(self):
        self.run_message(reference='wamid.unknown')
        self.assertEqual(self.outcome(),'REFERENCIA_DESCONHECIDA')
    def test_reference_incompatible_sender(self):
        e=self.evidence(mental=self.cid)
        self.run_message(reference=e.wamid,sender='551100000000')
        self.assertEqual(self.outcome(),'IDENTIDADE_RECUSADA')
    def test_other_emitter_reference(self):
        e=self.evidence(mental=self.cid,emitter='999')
        self.run_message(reference=e.wamid)
        self.assertEqual(self.outcome(),'REFERENCIA_DESCONHECIDA')
    def test_ambiguous_lines_no_effect(self):
        self.evidence(mental=self.cid)
        c=self.legacy();self.evidence(legacy=c.id)
        self.run_message()
        self.assertEqual(self.outcome(),'AMBIGUA')
        self.assertEqual(self.db.get(Mental,self.cid).status,'AGUARDANDO_ACEITE')
        self.assertEqual(c.etapa_atual,'SONO')
    def test_reference_selects_only_target(self):
        e=self.evidence(mental=self.cid)
        c=self.legacy();self.evidence(legacy=c.id)
        self.run_message(reference=e.wamid)
        self.assertEqual(self.outcome(),'SELECIONADA');self.assertEqual(c.etapa_atual,'SONO')
    def test_no_candidate_no_session_created(self):
        self.run_message(sender='551100000001')
        self.assertEqual(self.outcome(),'INDISPONIVEL')
    def test_no_alias_inference(self):
        self.run_message()
        self.assertEqual(self.outcome(),'INDISPONIVEL')
    def test_conflicting_identity(self):
        self.evidence(mental=self.cid);self.evidence(mental=self.cid,sender='551100000002')
        self.run_message();self.assertEqual(self.outcome(),'IDENTIDADE_RECUSADA')
    def test_expired_reference_no_change(self):
        e=self.evidence(mental=self.cid)
        c=self.db.get(Mental,self.cid);c.created_at=self.now-timedelta(days=2);c.expires_at=self.now-timedelta(days=1);self.db.commit()
        self.run_message(reference=e.wamid)
        self.assertEqual(self.outcome(),'CONVERSA_INDISPONIVEL');self.assertEqual(c.status,'AGUARDANDO_ACEITE')
    def test_closed_reference(self):
        e=self.evidence(mental=self.cid);self.db.get(Mental,self.cid).status='CONCLUIDA';self.db.commit()
        self.run_message(reference=e.wamid);self.assertEqual(self.outcome(),'CONVERSA_INDISPONIVEL')
    def test_replay_and_fingerprint_conflict(self):
        self.evidence(mental=self.cid)
        response=self.run_message();mid=self.mid
        self.assertEqual(self.run_message(mid=mid),response)
        with self.assertRaises(HTTPException):self.run_message(content='NAO',mid=mid)
        self.assertEqual(self.db.get(Mental,self.cid).status,'EM_ANDAMENTO')
    def test_concurrent_replay(self):
        self.evidence(mental=self.cid);self.db.rollback();mid='selected-'+uuid4().hex
        def run(_):
            with Session(self.engine) as db:return process_selected(db,mid,'12345',self.sender,'SIM')
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(run,range(2)))
        self.assertEqual(results[0],results[1]);self.assertIsNotNone(self.db.get(Audit,mid))
    def test_handler_failure_rolls_back_receipt_and_state(self):
        self.evidence(mental=self.cid)
        with patch('app.services.whatsapp_mental.WhatsAppMentalService.receive',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):self.run_message()
        self.assertIsNone(self.db.get(Receipt,self.mid))
        self.assertEqual(self.db.get(Mental,self.cid).status,'AGUARDANDO_ACEITE')
    def test_parar_is_not_integrated(self):
        self.evidence(mental=self.cid);self.run_message(content='PARAR')
        self.assertEqual(self.outcome(),'PARAR_NAO_INTEGRADO')
        self.assertEqual(self.db.get(Mental,self.cid).status,'AGUARDANDO_ACEITE')
    def test_selection_is_immutable(self):
        from dataclasses import FrozenInstanceError
        self.evidence(mental=self.cid)
        chosen=propose(self.db,'12345',self.sender,'SIM','synthetic')[1]
        with self.assertRaises(FrozenInstanceError):chosen.conversation_id=999
    def test_legacy_neuro_selected(self):
        self.db.get(Mental,self.cid).status='CONCLUIDA';self.db.commit()
        c=self.legacy();e=self.evidence(legacy=c.id)
        self.run_message(content='8',reference=e.wamid)
        self.assertEqual(self.outcome(),'SELECIONADA')
        self.assertEqual(self.db.get(Receipt,self.mid).conversa_legada_id,c.id)
    def test_legacy_cardio_selected(self):
        self.db.get(Mental,self.cid).status='CONCLUIDA';self.db.commit()
        c=self.legacy('CARDIO');e=self.evidence(legacy=c.id)
        self.run_message(content='1',reference=e.wamid)
        self.assertEqual(self.outcome(),'SELECIONADA')
    def test_navigation_existing(self):
        c=self.legacy(phone=('55119'+str(self.cid).zfill(8)));c.paciente_id=None;c.etapa_atual='INICIO';self.db.commit()
        self.run_message(content='OI',sender=c.telefone)
        self.assertEqual(self.outcome(),'NAVEGACAO')
        self.assertEqual(self.db.get(Receipt,self.mid).conversa_legada_id,c.id)
    def test_navigation_not_clinical_authorization(self):
        c=self.legacy(phone=('55119'+str(self.cid).zfill(8)));c.paciente_id=None;c.etapa_atual='INICIO';self.db.commit()
        from app.models.responsavel_paciente import ResponsavelPaciente
        link=self.db.scalar(select(ResponsavelPaciente).where(ResponsavelPaciente.responsavel_id==c.responsavel_id));link.ativo=False;self.db.commit()
        self.run_message(content='OI',sender=c.telefone)
        self.assertEqual(self.outcome(),'INDISPONIVEL')

    def test_changed_selection_under_locks_is_audited(self):
        self.evidence(mental=self.cid)
        from app.services import whatsapp_selected as module
        original=module._lock_selected
        def change(db, chosen):
            original(db,chosen)
            # Simulate state discovered after locking, without clinical effects.
            db.get(Mental,chosen.conversation_id).status='CONCLUIDA'
            db.flush()
        with patch.object(module,'_lock_selected',side_effect=change):self.run_message()
        self.assertEqual(self.outcome(),'SELECAO_ALTERADA')
        self.assertIsNone(self.db.get(Receipt,self.mid).conversa_contextual_id)
    def test_reference_without_clinical_link(self):
        c=self.legacy();c.paciente_id=None;c.etapa_atual='INICIO';self.db.commit()
        e=self.evidence(legacy=c.id);self.run_message(reference=e.wamid)
        self.assertEqual(self.outcome(),'NAVEGACAO')
    def test_explicit_conflicting_identity_is_refused(self):
        e=self.evidence(mental=self.cid);self.evidence(mental=self.cid,sender='551100000005')
        self.run_message(reference=e.wamid);self.assertEqual(self.outcome(),'IDENTIDADE_RECUSADA')
    def test_historical_only_no_legacy_start(self):
        self.evidence(mental=self.cid);self.db.get(Mental,self.cid).status='CONCLUIDA';self.db.commit()
        self.run_message(content='OI');self.assertEqual(self.outcome(),'INDISPONIVEL')
    def test_navigation_with_clinical_candidate_is_not_selected(self):
        c=self.legacy();c.paciente_id=None;c.etapa_atual='INICIO';self.db.commit()
        self.evidence(mental=self.cid);self.evidence(legacy=c.id)
        self.run_message()
        self.assertEqual(self.outcome(),'SELECIONADA')
        self.assertEqual(self.db.get(Receipt,self.mid).conversa_contextual_id,self.cid)
        self.assertEqual(c.etapa_atual,'INICIO')
    def test_absent_prior_authorization(self):
        from app.services.whatsapp_autorizacao import register
        from app.schemas.whatsapp_autorizacao import AuthorizationRevoke
        self.evidence(mental=self.cid)
        register(self.db,self.scope,uuid4().hex,AuthorizationRevoke(motivo='SOLICITACAO_TITULAR'),revoke=True)
        self.db.commit();self.run_message();self.assertEqual(self.outcome(),'INDISPONIVEL')
    def test_sanitized_audit(self):
        self.evidence(mental=self.cid);self.run_message()
        import json
        data=json.dumps(self.db.get(Audit,self.mid).decisao)
        self.assertNotIn(self.sender,data);self.assertNotIn(self.phone,data)
    def test_fresh_fallback_does_not_create_session(self):
        from app.models.whatsapp_conversa import WhatsAppConversa
        c=self.legacy(phone=('55119'+str(self.cid).zfill(8)));cid=c.id
        self.db.delete(c);self.db.commit()
        self.run_message(content='OI',sender=('55119'+str(self.cid).zfill(8)))
        self.assertEqual(self.outcome(),'NAVEGACAO_NOVA')
        self.assertIsNone(self.db.get(WhatsAppConversa,cid))

    def separate_legacy(self, phone, different_institution=False):
        from app.models.pessoa import Pessoa
        from app.models.paciente import Paciente
        from app.models.responsavel import Responsavel
        from app.models.responsavel_paciente import ResponsavelPaciente
        from app.models.modular import PacienteModulo
        from app.models.clinica import Clinica
        c=self.legacy(phone=phone)
        person=Pessoa(nome_completo='Synthetic other');self.db.add(person);self.db.flush()
        clinic=None
        if different_institution:
            clinic=Clinica(nome='Synthetic other institution');self.db.add(clinic);self.db.flush()
        patient=Paciente(nome='Synthetic other',pessoa_id=person.id,ativo=True,clinica_id=clinic.id if clinic else None)
        self.db.add(patient);self.db.flush()
        link=self.db.scalar(select(ResponsavelPaciente).where(ResponsavelPaciente.responsavel_id==c.responsavel_id))
        link.paciente_id=patient.id;c.paciente_id=patient.id
        self.db.get(Responsavel,c.responsavel_id).clinica_id=patient.clinica_id
        self.db.add(PacienteModulo(paciente_id=patient.id,modulo_id=1,ativo=True));self.db.commit()
        return c
    def test_same_phone_different_people_is_ambiguous(self):
        c=self.legacy();self.evidence(legacy=c.id)
        other=self.separate_legacy(self.phone);self.evidence(legacy=other.id)
        self.run_message();self.assertEqual(self.outcome(),'AMBIGUA')
    def test_same_phone_different_institutions_is_ambiguous(self):
        c=self.legacy();self.evidence(legacy=c.id)
        other=self.separate_legacy(self.phone,True);self.evidence(legacy=other.id)
        self.run_message();self.assertEqual(self.outcome(),'AMBIGUA')
    def test_unreferenced_unique_neuro(self):
        c=self.legacy(phone=('55119'+str(self.cid).zfill(8)));self.evidence(legacy=c.id,phone=c.telefone)
        self.run_message(content='8');self.assertEqual(self.outcome(),'SELECIONADA')
        self.assertEqual(self.db.get(Receipt,self.mid).conversa_legada_id,c.id)
    def test_real_ninth_digit_bridge_requires_evidence(self):
        from app.models.whatsapp_contextual import AcompanhamentoWhatsApp
        c=self.db.get(Mental,self.cid);c.status='CONCLUIDA';self.db.commit()
        self.service.configure(self.db,'5511998760000',**self.scope);self.db.commit()
        c.telefone='5511998760000';c.status='AGUARDANDO_ACEITE';self.db.commit()
        self.phone=c.telefone;self.sender='551198760000'
        from app.services.whatsapp_autorizacao import register
        from app.schemas.whatsapp_autorizacao import AuthorizationCreate
        from app.services.whatsapp_mental import now_utc
        register(self.db,self.scope,uuid4().hex,AuthorizationCreate(origem='DOCUMENTO_ELETRONICO',
            obtida_em=now_utc(self.db),referencia_evidencia='synthetic-renewed-evidence',
            evidencia_sha256='c'*64,evidencia_verificada=True))
        self.db.commit()
        self.run_message();self.assertEqual(self.outcome(),'INDISPONIVEL')
        self.evidence(mental=self.cid);self.run_message();self.assertEqual(self.outcome(),'SELECIONADA')
    def test_navigation_ambiguous_is_refused(self):
        for _ in range(2):
            c=self.legacy(phone=('55119'+str(self.cid).zfill(8)));c.paciente_id=None;c.etapa_atual='INICIO';self.db.commit()
        self.run_message(content='OI',sender=('55119'+str(self.cid).zfill(8)))
        self.assertEqual(self.outcome(),'INDISPONIVEL')

    def test_concurrent_expiry_revalidation(self):
        import time
        from sqlalchemy import text
        from app.services.whatsapp_comunicacao import coordinate_many
        self.evidence(mental=self.cid);self.db.rollback();mid='selected-'+uuid4().hex
        with Session(self.engine) as owner:
            coordinate_many(owner,'12345',(self.phone,self.sender),identity_check=False)
            c=owner.get(Mental,self.cid);c.status='CONCLUIDA';owner.flush()
            def run():
                with Session(self.engine) as db:return process_selected(db,mid,'12345',self.sender,'SIM')
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(run)
                deadline=time.monotonic()+2;observed=False
                while time.monotonic()<deadline:
                    with self.engine.connect() as probe:
                        observed=bool(probe.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND pid<>pg_backend_pid()")))
                    if observed:break
                    time.sleep(.01)
                owner.commit();future.result(5)
                self.assertTrue(observed)
        self.assertEqual(self.db.get(Audit,mid).decisao['outcome'],'SELECAO_ALTERADA')
        self.assertEqual(self.db.get(Mental,self.cid).status,'CONCLUIDA')
    def test_communication_barrier_blocks_selected_execution(self):
        from app.services.whatsapp_comunicacao import append,recipient_scope,coordinate_many
        self.evidence(mental=self.cid)
        mid='barrier-'+uuid4().hex
        coordinate_many(self.db,'12345',(self.phone,self.sender),identity_check=False)
        self.db.add(Receipt(message_id=mid,phone_number_id='12345',fingerprint='a'*64,resposta=''))
        self.db.flush()
        append(self.db,scope=recipient_scope('12345',self.phone),emitter='12345',phone=self.phone,
            state='INTERROMPIDA',key=uuid4().hex*2,fingerprint='b'*64,message=mid)
        self.db.commit();self.run_message();self.assertEqual(self.outcome(),'COMUNICACAO_INDISPONIVEL')
        self.assertEqual(self.db.get(Mental,self.cid).status,'AGUARDANDO_ACEITE')

    def test_link_revoked_during_lock_is_audited(self):
        self.evidence(mental=self.cid)
        with patch('app.services.whatsapp_selected._lock_selected',side_effect=ValueError('Synthetic revoked scope')):
            self.run_message()
        self.assertEqual(self.outcome(),'SELECAO_ALTERADA')
        self.assertEqual(self.db.get(Mental,self.cid).status,'AGUARDANDO_ACEITE')
