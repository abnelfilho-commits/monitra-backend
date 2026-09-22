"""Durable synthetic WhatsApp journey/migration/concurrency checks in disposable PG."""
import test_whatsapp_security as http
import os
import importlib.util
import threading
import unittest
import uuid
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from app.database import Base, get_db
from app.models import (Clinica, Paciente, ModuloClinico, PacienteModulo, Responsavel,
    ResponsavelPaciente, FormularioModulo, CampoFormulario, RegistroLongitudinal, RespostaRegistro)
from app.models.whatsapp_conversa import WhatsAppConversa
from app.models.whatsapp_mensagem import WhatsAppMensagem
from app.services.whatsapp_ingress import process_message
from app.services.daily_record.providers.neuro import FIELDS
from app.services.daily_record.providers.cardio import NUMERIC, TEXT
from app.services.whatsapp_daily_record import create_record
from app.services.whatsapp_conversation_service import buscar_responsavel_por_telefone
from app.routers import whatsapp, responsavel_registros, responsavel_cardio
from app.schemas.registro import RegistroDiarioResponsavelCreate
from app.schemas.responsavel_cardio import RegistroCardioResponsavelCreate

URL=os.getenv('WHATSAPP_TEST_POSTGRES_URL')


@unittest.skipUnless(URL, 'Requires disposable PostgreSQL WHATSAPP_TEST_POSTGRES_URL')
class WhatsAppPostgresTests(unittest.TestCase):
    def setUp(self):
        self.schema='whatsapp_test_'+uuid.uuid4().hex
        self.admin=create_engine(URL)
        with self.admin.begin() as conn: conn.execute(text('CREATE SCHEMA '+self.schema))
        self.engine=create_engine(URL,connect_args={'options':'-c search_path='+self.schema})
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.db.add(Clinica(id=1,nome='Synthetic'));self.db.flush()
        self.db.add_all([ModuloClinico(id=i,nome=str(i),slug=str(i),ativo=True) for i in (1,2)])
        self.db.add_all([Paciente(id=i,nome='Synthetic '+str(i),clinica_id=1,ativo=True) for i in (1,2,3)])
        self.db.add_all([Responsavel(id=i,nome='Synthetic',email=str(i)+'@example.invalid',
            senha_hash='unused',telefone='556599999000'+str(i),ativo=True,clinica_id=1) for i in (1,2,3)])
        self.db.flush()
        for p,m in ((1,1),(2,2),(3,1),(3,2)):
            self.db.add(PacienteModulo(paciente_id=p,modulo_id=m,ativo=True))
        for i in (1,2,3): self.db.add(ResponsavelPaciente(responsavel_id=i,paciente_id=i,ativo=True))
        for module,fields in ((1,FIELDS),(2,sorted(NUMERIC|TEXT))):
            form_id=2 if module==1 else 200
            self.db.add(FormularioModulo(id=form_id,modulo_id=module,nome='Synthetic',tipo='REGISTRO_DIARIO',ativo=True))
            self.db.flush()
            for name in fields: self.db.add(CampoFormulario(formulario_id=form_id,nome_campo=name,label=name,tipo_campo='texto',ativo=True))
        self.db.commit()
        with self.engine.begin() as conn:
            for name, kind in {'score_clinico':'NUMERIC', 'risco':'VARCHAR', 'protocolo':'VARCHAR',
                               'leitura_clinica':'TEXT', 'observacoes':'TEXT'}.items():
                conn.execute(text('ALTER TABLE registros_longitudinais ADD COLUMN '+name+' '+kind))
        self.env=patch.dict(os.environ,http.ENV);self.env.start()
        self.app=FastAPI();self.app.include_router(whatsapp.router)
        def session():
            with Session(self.engine) as db: yield db
        self.app.dependency_overrides[get_db]=session
        self.client=http.LocalClient(self.app)
        self.counter=0

    def tearDown(self):
        self.env.stop();self.db.close();self.engine.dispose()
        with self.admin.begin() as conn: conn.execute(text('DROP SCHEMA '+self.schema+' CASCADE'))
        self.admin.dispose()

    def send(self,content,patient=2,identity=None):
        self.counter+=1
        body=http.encoded(http.envelope(content,'556599999000'+str(patient),identity or str(self.counter)))
        response=self.client.post('/whatsapp/webhook',content=body,headers={'X-Hub-Signature-256':http.signature(body)})
        self.assertEqual(response.status_code,200,response.text)
        self.db.expire_all()
        return response

    def cardio(self,patient=2):
        self.send('oi',patient)
        if patient==3: self.send('CARDIO',patient)
        for message in ('1','180','140','90','85','  synthetic observation\nexact  ','1'):
            self.send(message,patient)

    def neuro(self,patient=1):
        self.send('oi',patient)
        if patient==3:self.send('NEURO',patient)
        # Today, sleep, no evacuation, irritability, crisis, screen, selectivity,
        # new food, observation, confirmation. Existing questionnaire mappings.
        for message in ('1','4','2','1','0','1','1','1','synthetic neuro','1'):
            self.send(message,patient)

    def test_cardio_signed_journey_and_canonical_text(self):
        self.cardio()
        record=self.db.query(RegistroLongitudinal).one()
        self.assertEqual((record.modulo_id,record.origem,record.criado_por_responsavel_id),(2,'RESPONSAVEL_WHATSAPP',2))
        result=self.db.execute(text('SELECT observacoes,risco FROM registros_longitudinais')).one()
        self.assertEqual(result[0],'  synthetic observation\nexact  ')
        self.assertIsNotNone(result[1])
        from app.services.clinical_reading.service import ClinicalReadingService
        reading=ClinicalReadingService().get_reading(self.db,2,'CARDIO')
        self.assertIsNone(reading.trend)

    def test_neuro_signed_journey_preserves_answers(self):
        self.neuro()
        record=self.db.query(RegistroLongitudinal).one()
        self.assertEqual((record.modulo_id,record.origem,record.criado_por_responsavel_id),(1,'RESPONSAVEL_WHATSAPP',1))
        answers=responsavel_registros.extrair_respostas_registro(self.db,record.id)
        self.assertEqual(answers['sono_qualidade'],4)
        self.assertFalse(answers['evacuacao']);self.assertIsNone(answers['consistencia_fezes'])
        self.assertEqual(answers['irritabilidade'],1);self.assertEqual(answers['crise_sensorial'],0)
        self.assertEqual(answers['observacao'],'synthetic neuro')

    def test_multiline_requires_explicit_line_and_isolates_records(self):
        self.send('oi',3)
        conversation=self.db.query(WhatsAppConversa).one()
        self.assertEqual(conversation.etapa_atual,'SELECIONAR_LINHA')
        self.assertIsNone(conversation.care_line)
        self.send('invalid',3)
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),0)
        self.send('CARDIO',3)
        for value in ('1','180','140','90','85','pular','1'):self.send(value,3)
        self.neuro(3)
        self.assertEqual(sorted((r.paciente_id,r.modulo_id) for r in self.db.query(RegistroLongitudinal)),[(3,1),(3,2)])

    def test_ambiguous_and_unknown_phone_expose_no_context(self):
        self.db.query(Responsavel).filter_by(id=2).update({'telefone':'5565999990001'});self.db.commit()
        self.assertIsNone(buscar_responsavel_por_telefone(self.db,'5565999990001'))
        self.db.rollback()
        self.send('oi',1);self.send('oi',2)
        self.assertEqual(self.db.query(WhatsAppConversa).count(),0)
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),0)

    def test_revoked_link_prevents_final_write(self):
        self.send('oi')
        for value in ('1','180','140','90','85','pular'):self.send(value)
        self.db.query(ResponsavelPaciente).filter_by(responsavel_id=2).update({'ativo':False});self.db.commit()
        self.send('1')
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),0)

    def test_inactive_line_prevents_final_write(self):
        self.send('oi')
        for value in ('1','180','140','90','85','pular'):self.send(value)
        self.db.query(PacienteModulo).filter_by(paciente_id=2).update({'ativo':False});self.db.commit()
        self.send('1')
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),0)

    def test_replay_does_not_advance_conversation(self):
        self.send('oi',identity='same')
        self.send('oi',identity='same')
        self.assertEqual(self.db.query(WhatsAppMensagem).count(),1)
        self.assertEqual(self.db.query(WhatsAppConversa).one().etapa_atual,'SELECIONAR_DATA')

    def test_concurrent_delivery_creates_one_receipt_and_transition(self):
        barrier=threading.Barrier(2)
        def worker(_):
            with Session(self.engine) as db:
                barrier.wait(timeout=10)
                return process_message(db,'concurrent','12345','5565999990002','oi')
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(worker,range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(self.db.query(WhatsAppMensagem).count(),1)
        self.assertEqual(self.db.query(WhatsAppConversa).count(),1)

    def test_failed_transaction_rolls_back_receipt_and_conversation(self):
        from app.services import whatsapp_ingress
        original=whatsapp_ingress.processar_mensagem
        def fail(db,*args):
            original(db,*args)
            raise RuntimeError('synthetic failure')
        with patch.object(whatsapp_ingress,'processar_mensagem',side_effect=fail):
            with self.assertRaises(RuntimeError):
                process_message(self.db,'failure','12345','5565999990002','oi')
        self.assertEqual(self.db.query(WhatsAppMensagem).count(),0)
        self.assertEqual(self.db.query(WhatsAppConversa).count(),0)
        process_message(self.db,'failure','12345','5565999990002','oi')
        self.assertEqual(self.db.query(WhatsAppMensagem).count(),1)

    def test_app_channel_and_cross_channel_duplicate(self):
        responsible=self.db.query(Responsavel).filter_by(id=2).one()
        result=responsavel_cardio.criar_registro_cardio_responsavel(2,
            RegistroCardioResponsavelCreate(data=date.today(),peso=85,observacoes='synthetic'),self.db,responsible)
        row=self.db.query(RegistroLongitudinal).filter_by(id=result['registro_id']).one()
        self.assertEqual(row.origem,'RESPONSAVEL_APP')
        with self.assertRaises(ValueError):create_record(self.db,2,2,'CARDIO',date.today(),{'peso':85})
        self.db.rollback()
        self.neuro()
        responsible=self.db.query(Responsavel).filter_by(id=1).one()
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):responsavel_registros.criar_registro_meu_paciente(1,
            RegistroDiarioResponsavelCreate(data=date.today(),sono_qualidade=4),self.db,responsible)
        self.db.rollback()
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),2)

    def test_app_reads_both_channels_and_legacy_origin(self):
        self.neuro()
        responsible=self.db.query(Responsavel).filter_by(id=1).one()
        rows=responsavel_registros.listar_registros_meu_paciente(1,self.db,responsible)
        self.assertEqual(rows[0]['origem'],'RESPONSAVEL_WHATSAPP')
        self.assertEqual(rows[0]['criado_por_id'],1)
        self.db.query(RegistroLongitudinal).update({'origem':'RESPONSAVEL'});self.db.commit()
        self.assertEqual(len(responsavel_registros.listar_registros_meu_paciente(1,self.db,responsible)),1)
        self.cardio()
        responsible=self.db.query(Responsavel).filter_by(id=2).one()
        rows=responsavel_cardio.listar_registros_cardio_responsavel(2,self.db,responsible)
        self.assertEqual(rows[0]['origem'],'RESPONSAVEL_WHATSAPP')
        self.assertEqual(rows[0]['criado_por_responsavel_id'],2)

    def test_same_id_with_different_content_rejected(self):
        process_message(self.db,'identity','12345','5565999990002','oi')
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            process_message(self.db,'identity','12345','5565999990002','1')
        self.assertEqual(self.db.query(WhatsAppConversa).one().etapa_atual,'SELECIONAR_DATA')

    def test_inactive_responsible_and_cross_clinic_rejected(self):
        self.db.query(Responsavel).filter_by(id=1).update({'ativo':False})
        self.db.add(Clinica(id=2,nome='Synthetic other'));self.db.flush()
        self.db.query(Responsavel).filter_by(id=2).update({'clinica_id':2});self.db.commit()
        self.send('oi',1);self.send('oi',2)
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),0)
        receipts=self.db.query(WhatsAppMensagem).all()
        self.assertTrue(all('Synthetic 2' not in r.resposta for r in receipts))

    def test_cardio_no_data_remains_unavailable(self):
        self.send('oi')
        for value in ('1','pular','pular','pular','pular','only synthetic text','1'):self.send(value)
        row=self.db.execute(text('SELECT risco,score_clinico,observacoes FROM registros_longitudinais')).one()
        self.assertEqual(tuple(row),(None,None,'only synthetic text'))

    def test_final_projection_failure_is_atomic_and_retryable(self):
        self.send('oi')
        for value in ('1','180','140','90','85','synthetic'):self.send(value)
        with patch('app.services.daily_record.providers.cardio.CardioDailyRecordProvider.persist_projection',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):process_message(self.db,'confirm','12345','5565999990002','1')
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),0)
        self.assertEqual(self.db.query(RespostaRegistro).count(),0)
        self.assertEqual(self.db.query(WhatsAppConversa).one().etapa_atual,'CARDIO_5')
        self.assertEqual(self.db.query(WhatsAppMensagem).filter_by(message_id='confirm').count(),0)
        process_message(self.db,'confirm','12345','5565999990002','1')
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),1)

    def test_neuro_app_whatsapp_concurrent_duplicate_policy(self):
        barrier=threading.Barrier(2)
        def worker(channel):
            with Session(self.engine) as db:
                responsible=db.query(Responsavel).filter_by(id=1).one()
                barrier.wait(timeout=10)
                try:
                    if channel=='APP':
                        responsavel_registros.criar_registro_meu_paciente(1,
                            RegistroDiarioResponsavelCreate(data=date.today(),sono_qualidade=4),db,responsible)
                    else:
                        create_record(db,1,1,'NEURO',date.today(),{'sono_qualidade':4});db.commit()
                    return 'ok'
                except (ValueError,http.whatsapp.HTTPException):
                    db.rollback();return 'duplicate'
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(worker,('APP','WHATSAPP')))
        self.assertEqual(sorted(results),['duplicate','ok'])
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),1)

    def test_delivery_retry_does_not_repeat_processing_or_successful_send(self):
        from app.services.whatsapp_ingress import deliver_reply
        process_message(self.db,'delivery','12345','5565999990002','oi')
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):deliver_reply(self.db,'delivery','5565999990002')
        self.assertIsNone(self.db.query(WhatsAppMensagem).one().enviado_em)
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto') as sender:
            deliver_reply(self.db,'delivery','5565999990002')
            deliver_reply(self.db,'delivery','5565999990002')
            self.assertEqual(sender.call_count,1)
        self.assertEqual(self.db.query(WhatsAppConversa).one().etapa_atual,'SELECIONAR_DATA')

    def test_additive_migration_upgrade_downgrade(self):
        self.db.close()
        with self.engine.begin() as conn:
            conn.execute(text('DROP TABLE whatsapp_mensagens'))
            conn.execute(text('ALTER TABLE whatsapp_conversas DROP COLUMN care_line'))
            conn.execute(text("INSERT INTO whatsapp_conversas (responsavel_id,telefone,etapa_atual,respostas_json) VALUES (1,'synthetic','SONO','{}')"))
            spec=importlib.util.spec_from_file_location('wa_migration','alembic/versions/8c01a0d1a004_whatsapp_ingress.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
                self.assertEqual(conn.execute(text('SELECT care_line FROM whatsapp_conversas')).scalar(),'NEURO')
                self.assertTrue(inspect(conn).has_table('whatsapp_mensagens'))
                module.downgrade()
                self.assertFalse(inspect(conn).has_table('whatsapp_mensagens'))
                self.assertEqual(conn.execute(text('SELECT count(*) FROM whatsapp_conversas')).scalar(),1)
