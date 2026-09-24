"""Synthetic Portal/APP convergence, access scope and canonical observations."""
import test_cardio_foundation as foundation
from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from sqlalchemy import text
from fastapi import HTTPException
from app.models import (FormularioModulo, CampoFormulario, RegistroLongitudinal,
                        RespostaRegistro, Responsavel, ResponsavelPaciente, PacienteModulo)
from app.routers.cardiometabolico import criar_registro_diario
from app.routers.responsavel_cardio import criar_registro_cardio_responsavel
from app.schemas.cardiometabolico import RegistroDiarioCardio
from app.schemas.responsavel_cardio import RegistroCardioResponsavelCreate
from app.services.daily_record.providers.cardio import NUMERIC, TEXT
from app.services import cardiometabolico_engine


class CardioChannelTests(unittest.TestCase):
    tearDown = foundation.FoundationTests.tearDown

    def setUp(self):
        foundation.FoundationTests.setUp(self)
        for model in (Responsavel, ResponsavelPaciente, FormularioModulo, CampoFormulario,
                      RegistroLongitudinal, RespostaRegistro):
            model.__table__.create(self.engine)
        self.db.add(Responsavel(id=9,nome='Synthetic',email='synthetic@example.invalid',senha_hash='unused',ativo=True))
        self.db.add(ResponsavelPaciente(responsavel_id=9,paciente_id=3,ativo=True))
        for module in (1,2):
            self.db.add(FormularioModulo(id=module*100,modulo_id=module,nome='Synthetic',tipo='REGISTRO_DIARIO',ativo=True))
            self.db.flush()
            for name in sorted(NUMERIC | TEXT):
                self.db.add(CampoFormulario(formulario_id=module*100,nome_campo=name,label=name,tipo_campo='texto',ativo=True))
        self.db.commit()
        with self.engine.begin() as conn:
            for name, kind in {'score_clinico':'NUMERIC', 'risco':'VARCHAR', 'protocolo':'VARCHAR',
                               'leitura_clinica':'TEXT'}.items():
                conn.execute(text('ALTER TABLE registros_longitudinais ADD COLUMN '+name+' '+kind))
        self.responsible = SimpleNamespace(id=9)

    def test_portal_and_app_share_exact_observations_and_engine_result(self):
        values = dict(glicemia_jejum=180,pressao_sistolica=140,pressao_diastolica=90,peso=85,
                      sono='regular',humor='estável',observacoes='  Complementary synthetic text\nsecond line  ')
        with patch.object(cardiometabolico_engine,'calcular_score',wraps=cardiometabolico_engine.calcular_score) as score:
            portal = criar_registro_diario(RegistroDiarioCardio(paciente_id=3,**values),self.db,self.user)
            app = criar_registro_cardio_responsavel(3,RegistroCardioResponsavelCreate(data=date.today(),**values),self.db,self.responsible)
            self.assertEqual(score.call_count,2)
            for call in score.call_args_list:
                self.assertNotIn('observacoes',call.args[0])
        rows = self.db.execute(text('''SELECT modulo_id,formulario_id,observacoes,score_clinico,risco,
            protocolo,leitura_clinica,origem,criado_por_usuario_id,criado_por_responsavel_id
            FROM registros_longitudinais ORDER BY id''')).all()
        self.assertEqual(tuple(rows[0][:7]),tuple(rows[1][:7]))
        self.assertEqual(rows[0][2],values['observacoes'])
        self.assertEqual(tuple(rows[0][7:]),('PROFISSIONAL',1,None))
        self.assertEqual(tuple(rows[1][7:]),('RESPONSAVEL_APP',None,9))
        self.assertEqual(app['score_clinico'],rows[1][3])
        for identity in (portal['registro_id'],app['registro_id']):
            fields = self.db.query(CampoFormulario).join(RespostaRegistro,RespostaRegistro.campo_id==CampoFormulario.id).filter(RespostaRegistro.registro_id==identity).all()
            self.assertTrue(fields)
            self.assertTrue(all(f.formulario_id==200 for f in fields))
            self.assertNotIn('observacoes',[f.nome_campo for f in fields])

    def test_app_observations_only_preserves_text_without_risk(self):
        result=criar_registro_cardio_responsavel(3,RegistroCardioResponsavelCreate(
            data=date.today(),observacoes='Only complementary text'),self.db,self.responsible)
        self.assertIsNone(result['risco'])
        self.assertIsNone(result['score_clinico'])
        self.assertEqual(self.db.execute(text('SELECT observacoes FROM registros_longitudinais')).scalar(),'Only complementary text')

    def test_app_duplicate_and_missing_line_do_not_write(self):
        payload=RegistroCardioResponsavelCreate(data=date.today(),peso=85,observacoes='Synthetic')
        criar_registro_cardio_responsavel(3,payload,self.db,self.responsible)
        with self.assertRaises(HTTPException):
            criar_registro_cardio_responsavel(3,payload,self.db,self.responsible)
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),1)
        self.db.rollback()
        self.db.query(PacienteModulo).filter_by(paciente_id=3,modulo_id=2).update({'ativo':False})
        self.db.commit()
        from datetime import timedelta
        with self.assertRaises(HTTPException):
            criar_registro_cardio_responsavel(3,RegistroCardioResponsavelCreate(
                data=date.today()-timedelta(days=1),observacoes='Synthetic'),self.db,self.responsible)
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),1)

    def test_portal_and_app_cannot_write_outside_authorized_patient(self):
        with self.assertRaises(HTTPException):
            criar_registro_diario(RegistroDiarioCardio(paciente_id=4,observacoes='Synthetic'),self.db,self.user)
        with self.assertRaises(HTTPException):
            criar_registro_cardio_responsavel(4,RegistroCardioResponsavelCreate(data=date.today(),observacoes='Synthetic'),self.db,self.responsible)
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),0)

    def test_projection_failure_rolls_back_all_app_data(self):
        with patch('app.services.daily_record.providers.cardio.CardioDailyRecordProvider.persist_projection',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                criar_registro_cardio_responsavel(3,RegistroCardioResponsavelCreate(data=date.today(),peso=85,observacoes='Synthetic'),self.db,self.responsible)
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),0)
        self.assertEqual(self.db.query(RespostaRegistro).count(),0)

    def test_app_history_reads_event_answers_and_preserves_snapshot(self):
        from datetime import timedelta
        from app.routers.responsavel_cardio import listar_registros_cardio_responsavel
        old=criar_registro_cardio_responsavel(3,RegistroCardioResponsavelCreate(
            data=date.today()-timedelta(days=1),glicemia_jejum=250,peso=140,
            pressao_sistolica=180,pressao_diastolica=120),self.db,self.responsible)
        criar_registro_cardio_responsavel(3,RegistroCardioResponsavelCreate(
            data=date.today(),peso=80),self.db,self.responsible)
        rows=listar_registros_cardio_responsavel(3,self.db,self.responsible)
        self.assertEqual(rows[0]['peso'],80)
        self.assertIsNone(rows[0]['glicemia_jejum'])
        self.assertEqual(rows[1]['peso'],140)
        self.assertEqual(rows[1]['glicemia_jejum'],250)
        self.assertEqual(rows[1]['pressao_sistolica'],180)
        self.assertEqual(rows[1]['pressao_diastolica'],120)
        self.assertEqual(rows[1]['risco'],old['risco'])
        self.assertEqual(rows[1]['leitura_clinica'],old['leitura_clinica'])
