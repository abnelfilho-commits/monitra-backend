"""Real PostgreSQL interleavings, not timing-only duplicate tests."""
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import test_whatsapp_postgres as fixture


@unittest.skipUnless(os.getenv('WHATSAPP_TEST_POSTGRES_URL'), 'Requires disposable PostgreSQL')
class DailyRecordConcurrencyTests(unittest.TestCase):
    setUp = fixture.WhatsAppPostgresTests.setUp
    tearDown = fixture.WhatsAppPostgresTests.tearDown

    def test_legacy_inverted_lock_fk_cycle_is_reproducible(self):
        barrier = threading.Barrier(2)
        def worker(channel):
            with self.engine.connect() as c:
                tx = c.begin()
                try:
                    c.execute(text("SET LOCAL deadlock_timeout='100ms'"))
                    c.execute(text("SET LOCAL lock_timeout='5s'"))
                    if channel == 'APP':
                        c.execute(text('SELECT id FROM pacientes WHERE id=1 FOR UPDATE'))
                    else:
                        c.execute(text('SELECT id FROM responsaveis WHERE id=1 FOR UPDATE'))
                    barrier.wait(timeout=5)
                    if channel == 'APP':
                        c.execute(text("INSERT INTO registros_longitudinais (paciente_id,modulo_id,formulario_id,origem,data_registro,criado_por_responsavel_id) VALUES (1,1,2,'RESPONSAVEL_APP',CURRENT_DATE,1)"))
                    else:
                        c.execute(text('SELECT id FROM pacientes WHERE id=1 FOR UPDATE'))
                    return 'completed'
                except OperationalError as exc:
                    return exc.orig.pgcode
                finally:
                    tx.rollback()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(worker, ('APP','WHATSAPP')))
        self.assertEqual(sorted(outcomes), ['40P01','completed'])
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM registros_longitudinais')).scalar(),0)

    def _portal_user(self):
        from app.models import Usuario
        user = self.db.query(Usuario).filter_by(id=50).first()
        if user is None:
            user = Usuario(id=50,nome='Synthetic',email='portal@example.invalid',senha_hash='unused',
                           perfil='ADMIN_CLINICA',clinica_id=1,ativo=True)
            self.db.add(user)
            self.db.commit()
        return user.id

    def _clear_records(self):
        self.db.rollback()
        self.db.execute(text('DELETE FROM respostas_registro'))
        self.db.execute(text('DELETE FROM registros_longitudinais'))
        self.db.commit()

    def _race(self, specs):
        from datetime import date
        from sqlalchemy.orm import Session
        from app.models import Usuario, Responsavel, CampoFormulario, RegistroLongitudinal, RespostaRegistro
        from app.routers import cardiometabolico, registros_longitudinais, responsavel_registros, responsavel_cardio
        from app.schemas.cardiometabolico import RegistroDiarioCardio
        from app.schemas.registro import RegistroDiarioResponsavelCreate
        from app.schemas.responsavel_cardio import RegistroCardioResponsavelCreate
        from app.schemas.registros_longitudinais import RegistroLongitudinalCreate
        from app.services.whatsapp_daily_record import create_record
        from fastapi import HTTPException
        self._portal_user()
        barrier = threading.Barrier(len(specs))
        def worker(spec):
            channel, line, patient, responsible = spec
            with Session(self.engine) as db:
                db.execute(text("SET LOCAL lock_timeout='8s'"))
                barrier.wait(timeout=8)
                try:
                    if channel == 'APP':
                        actor = db.query(Responsavel).filter_by(id=responsible).one()
                        if line == 'NEURO':
                            responsavel_registros.criar_registro_meu_paciente(patient,
                                RegistroDiarioResponsavelCreate(data=date.today(),sono_qualidade=4),db,actor)
                        else:
                            responsavel_cardio.criar_registro_cardio_responsavel(patient,
                                RegistroCardioResponsavelCreate(data=date.today(),peso=85),db,actor)
                    elif channel == 'WHATSAPP':
                        values = {'sono_qualidade':4} if line == 'NEURO' else {'peso':85}
                        create_record(db,responsible,patient,line,date.today(),values)
                        db.commit()
                    else:
                        user = db.query(Usuario).filter_by(id=50).one()
                        if line == 'CARDIO':
                            cardiometabolico.criar_registro_diario(RegistroDiarioCardio(paciente_id=patient,peso=85),db,user)
                        else:
                            field = db.query(CampoFormulario).filter_by(formulario_id=2,nome_campo='sono_qualidade').one()
                            payload = RegistroLongitudinalCreate(paciente_id=patient,modulo_id=1,formulario_id=2,
                                data_registro=date.today(),origem='PROFISSIONAL',respostas=[{'campo_id':field.id,'valor':4}])
                            registros_longitudinais.criar_registro(payload,db,user)
                    return ('ok',spec)
                except (ValueError,HTTPException) as exc:
                    detail = str(getattr(exc,'detail',exc)).lower()
                    # Only the existing duplicate outcome is allowed as a loser.
                    if 'já' not in detail:
                        raise
                    db.rollback()
                    return ('duplicate',spec)
        with ThreadPoolExecutor(max_workers=len(specs)) as pool:
            results = list(pool.map(worker,specs))
        self.db.expire_all()
        rows = self.db.query(RegistroLongitudinal).all()
        winners = [s for result,s in results if result=='ok']
        self.assertEqual(len(rows),len(winners))
        actual = sorted((r.origem,r.modulo_id,r.paciente_id,r.criado_por_responsavel_id or 0,r.criado_por_usuario_id or 0) for r in rows)
        expected = sorted(({'PORTAL':'PROFISSIONAL','APP':'RESPONSAVEL_APP','WHATSAPP':'RESPONSAVEL_WHATSAPP'}[c],
                           1 if line=='NEURO' else 2,p,0 if c=='PORTAL' else resp,50 if c=='PORTAL' else 0)
                          for c,line,p,resp in winners)
        self.assertEqual(actual,expected)
        # No orphan/partial answers survive any losing transaction.
        self.assertEqual(self.db.query(RespostaRegistro).filter(~RespostaRegistro.registro_id.in_([r.id for r in rows])).count(),0)
        self.assertTrue(all(self.db.query(RespostaRegistro).filter_by(registro_id=r.id).count()>0 for r in rows))
        return results

    def _matrix(self,line,patient):
        pairs = [('APP','WHATSAPP'),('APP','APP'),('WHATSAPP','WHATSAPP'),
                 ('PORTAL','APP'),('PORTAL','WHATSAPP'),('PORTAL','PORTAL')]
        for repeat in range(3):
            for channels in pairs:
                with self.subTest(line=line,channels=channels,repeat=repeat):
                    self._clear_records()
                    results=self._race([(channel,line,patient,patient) for channel in channels])
                    # Professional and responsible observations remain separate;
                    # no new per-day restriction is imposed on the Portal.
                    expected=2 if 'PORTAL' in channels else 1
                    self.assertEqual(sum(r=='ok' for r,_ in results),expected)

    def test_neuro_all_channel_pairs_repeated(self):
        self._matrix('NEURO',1)

    def test_cardio_all_channel_pairs_repeated(self):
        self._matrix('CARDIO',2)

    def test_multiline_patient_isolation_repeated(self):
        for repeat in range(3):
            for channels in [('APP','WHATSAPP'),('PORTAL','APP'),('PORTAL','WHATSAPP')]:
                with self.subTest(repeat=repeat,channels=channels):
                    self._clear_records()
                    result=self._race([(channels[0],'NEURO',3,3),(channels[1],'CARDIO',3,3)])
                    self.assertTrue(all(status=='ok' for status,_ in result))

    def test_distinct_responsibles_preserve_line_specific_duplicate_scope(self):
        from app.models import Responsavel, ResponsavelPaciente
        self.db.add(Responsavel(id=4,nome='Synthetic',email='4@example.invalid',senha_hash='unused',
                                telefone='5565999990004',ativo=True,clinica_id=1))
        self.db.flush()
        for patient in (1,2):
            self.db.add(ResponsavelPaciente(responsavel_id=4,paciente_id=patient,ativo=True))
        self.db.commit()
        for line,patient,expected in [('NEURO',1,1),('CARDIO',2,2)]:
            self._clear_records()
            results=self._race([('APP',line,patient,patient),('WHATSAPP',line,patient,4)])
            self.assertEqual(sum(r=='ok' for r,_ in results),expected)

    def test_same_message_concurrently_commits_record_receipt_and_conversation_once(self):
        from sqlalchemy.orm import Session
        from app.services.whatsapp_ingress import process_message
        from app.models import RegistroLongitudinal
        from app.models.whatsapp_mensagem import WhatsAppMensagem
        from app.models.whatsapp_conversa import WhatsAppConversa
        # Real conversation to final confirmation, no outbound Meta calls.
        send = lambda content: fixture.WhatsAppPostgresTests.send(self,content)
        send('oi')
        for content in ('1','180','140','90','85','synthetic'):
            send(content)
        self.db.rollback()
        barrier=threading.Barrier(2)
        def worker(_):
            with Session(self.engine) as db:
                db.execute(text("SET LOCAL lock_timeout='8s'"))
                barrier.wait(timeout=8)
                return process_message(db,'same-final-message','12345','5565999990002','1')
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies=list(pool.map(worker,range(2)))
        self.assertEqual(replies[0],replies[1])
        self.db.expire_all()
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),1)
        row=self.db.query(RegistroLongitudinal).one()
        self.assertEqual((row.origem,row.criado_por_responsavel_id,row.modulo_id),('RESPONSAVEL_WHATSAPP',2,2))
        self.assertEqual(self.db.query(WhatsAppMensagem).filter_by(message_id='same-final-message').count(),1)
        self.assertEqual(self.db.query(WhatsAppConversa).one().etapa_atual,'INICIO')

    def test_direct_institutional_service_serializes_before_provider_dedup(self):
        from datetime import date
        from sqlalchemy.orm import Session
        from app.services.daily_record import DailyRecordService, DailyRecordSubmission, ActorRef, ActorType
        from app.services.daily_record.exceptions import DuplicateDailyRecord
        from app.models import RegistroLongitudinal
        for line,patient in [('NEURO',1),('CARDIO',2)]:
            self._clear_records()
            barrier=threading.Barrier(2)
            def worker(channel):
                with Session(self.engine) as db:
                    db.execute(text("SET LOCAL lock_timeout='8s'"))
                    barrier.wait(timeout=8)
                    try:
                        DailyRecordService().create(db,DailyRecordSubmission(patient,line,date.today(),channel,
                            ActorRef(ActorType.RESPONSIBLE,patient),
                            {'sono_qualidade':4} if line=='NEURO' else {'peso':85}))
                        return 'ok'
                    except DuplicateDailyRecord:
                        # Service owns rollback when commit=True.
                        self.assertFalse(db.in_transaction())
                        return 'duplicate'
            with ThreadPoolExecutor(max_workers=2) as pool:
                result=list(pool.map(worker,('RESPONSAVEL_APP','RESPONSAVEL_WHATSAPP')))
            self.assertEqual(sorted(result),['duplicate','ok'])
            self.assertEqual(self.db.query(RegistroLongitudinal).count(),1)

    def test_portal_edit_concurrent_with_responsible_creation(self):
        from datetime import date
        from sqlalchemy.orm import Session
        from app.models import Usuario, CampoFormulario, RegistroLongitudinal, Responsavel
        from app.schemas.registros_longitudinais import RegistroLongitudinalUpdate
        from app.schemas.registro import RegistroDiarioResponsavelCreate
        from app.routers import registros_longitudinais, responsavel_registros
        self._race([('PORTAL','NEURO',1,1)])
        record_id=self.db.query(RegistroLongitudinal.id).scalar()
        field_id=self.db.query(CampoFormulario.id).filter_by(formulario_id=2,nome_campo='sono_qualidade').scalar()
        self.db.rollback()
        barrier=threading.Barrier(2)
        def worker(channel):
            with Session(self.engine) as db:
                db.execute(text("SET LOCAL lock_timeout='8s'"))
                barrier.wait(timeout=8)
                if channel=='PORTAL':
                    payload=RegistroLongitudinalUpdate(paciente_id=1,modulo_id=1,formulario_id=2,
                        data_registro=date.today(),origem='PROFISSIONAL',respostas=[{'campo_id':field_id,'valor':3}])
                    registros_longitudinais.atualizar_registro(record_id,payload,db,db.query(Usuario).filter_by(id=50).one())
                else:
                    responsavel_registros.criar_registro_meu_paciente(1,
                        RegistroDiarioResponsavelCreate(data=date.today(),sono_qualidade=4),db,
                        db.query(Responsavel).filter_by(id=1).one())
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(worker,('PORTAL','APP')))
        self.db.expire_all()
        rows=self.db.query(RegistroLongitudinal).all()
        self.assertEqual(sorted(r.origem for r in rows),['PROFISSIONAL','RESPONSAVEL_APP'])
        self.assertEqual(self.db.execute(text('SELECT valor_numero FROM respostas_registro WHERE registro_id=:r AND campo_id=:f'),{'r':record_id,'f':field_id}).scalar(),3)
