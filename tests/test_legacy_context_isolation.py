"""P0-12: mixed legacy/contextual evidence on disposable PostgreSQL 18."""
import importlib
import os
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from alembic import command
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException
import test_contextual_clinical_schema as physical
from test_m0_baseline import config
from app.services.care_lines import CareLineRegistry
from app.services.timeline import sources


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class IsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        physical.PhysicalTests.setUpClass.__func__(cls)
        with cls.engine.begin() as c: command.upgrade(config(c), 'head')

    tearDownClass = classmethod(physical.PhysicalTests.tearDownClass.__func__)
    seed = physical.PhysicalTests.seed
    insert = physical.PhysicalTests.insert

    def setUp(self):
        with self.engine.begin() as c:
            self.seed(c)
            c.execute(text("UPDATE pacientes SET ativo=true WHERE id=:p"), {"p":self.patient})
            c.execute(text("UPDATE formularios_modulo SET tipo='REGISTRO_DIARIO' WHERE id=:id"), {'id':self.form})
            self.legacy = {t:self.insert(c,t,contextual=False) for t in physical.ROOTS}
            self.contextual = {t:self.insert(c,t) for t in physical.ROOTS}
            c.execute(text("UPDATE registros_longitudinais SET data_registro='2099-01-01' WHERE id=:id"), {'id':self.contextual['registros_longitudinais']})
        self.db=Session(self.engine)
        self.user=SimpleNamespace(id=self.actor, perfil='ADMIN', clinica_id=None)

    def tearDown(self): self.db.close()

    def absent(self, fn, *args, **kwargs):
        with self.assertRaises(HTTPException) as error: fn(*args, **kwargs)
        self.assertEqual(error.exception.status_code,404)

    def test_longitudinal_get_patch_and_assessment_execute(self):
        from app.services.registros_longitudinais import obter_registro_longitudinal, atualizar_registro_longitudinal
        from app.services.clinical_engine.assessment_builder import AssessmentBuilder
        self.assertEqual(obter_registro_longitudinal(self.db,self.legacy['registros_longitudinais'])['id'],self.legacy['registros_longitudinais'])
        identity=self.contextual['registros_longitudinais']
        for fn,args in ((obter_registro_longitudinal,()),(atualizar_registro_longitudinal,(None,))):
            self.absent(fn,self.db,identity,*args)
        with self.assertRaises(ValueError): AssessmentBuilder.from_registro(self.db,identity,'MCHAT')
        self.assertEqual(self.db.execute(text('SELECT data_registro FROM registros_longitudinais WHERE id=:id'),{'id':identity}).scalar(),date(2099,1,1))

    def test_diagnosis_details_commands_and_report(self):
        from app.services.diagnostico_service import DiagnosticoService as Service
        self.assertEqual([r.id for r in Service.listar_por_paciente(self.db,self.patient)], [self.legacy['diagnosticos']])
        identity=self.contextual['diagnosticos']
        for fn,args in ((Service.buscar_por_id,()),(Service.atualizar,(None,)),(Service.cancelar,()),(Service.revisar,())):
            self.absent(fn,self.db,identity,*args)
        self.assertEqual(self.db.execute(text('SELECT status FROM diagnosticos WHERE id=:id'),{'id':identity}).scalar(),'ATIVO')

    def test_independent_router_acquisitions_do_not_delegate_contextual(self):
        from app.routers import registros_longitudinais as records,diagnosticos as diagnoses
        for fn,args in ((records.obter_registro,(self.contextual['registros_longitudinais'],)),
                        (records.atualizar_registro,(self.contextual['registros_longitudinais'],None))):
            with patch.object(records,'authorized_patient',side_effect=AssertionError('must not acquire contextual')):
                self.absent(fn,*args,db=self.db,usuario=self.user)
        with patch.object(diagnoses,'authorized_patient',side_effect=AssertionError('must not acquire contextual')):
            self.absent(diagnoses.scoped_record,self.db,self.user,self.contextual['diagnosticos'],'NEURO',True)

    def test_responsible_neuro_list_detail_and_neuro_engine(self):
        from app.routers import responsavel_registros as router
        from app.services.neuro_engine import obter_registros_neuro_pacientes
        self.db.execute(text("UPDATE registros_longitudinais SET origem='RESPONSAVEL_APP' WHERE paciente_id=:p"),dict(p=self.patient));self.db.commit()
        with patch.object(router,'MODULO_NEURO_ID',self.modules[0]),patch.object(router,'FORMULARIO_REGISTRO_NEURO_ID',self.form),patch.object(router,'validar_vinculo_ativo',return_value=True):
            rows=router.listar_registros_meu_paciente(self.patient,self.db,self.user)
            self.assertEqual([r['id'] for r in rows],[self.legacy['registros_longitudinais']])
            self.absent(router.obter_registro,self.contextual['registros_longitudinais'],self.db,self.user)
        # Neuro's independent batch query retains only the legacy row.
        with patch('app.services.neuro_engine.MODULO_NEURO_ID',self.modules[0],create=True):
            rows=obter_registros_neuro_pacientes(self.db,[self.patient])
        self.assertEqual([r.id for r in rows],[self.legacy['registros_longitudinais']])

    def test_report_uses_only_legacy_diagnosis(self):
        from app.services.report_engine.providers.diagnosis_provider import DiagnosisProvider
        result=DiagnosisProvider().collect(SimpleNamespace(db=self.db,subject_id=self.patient,
            care_line=SimpleNamespace(module_id=self.modules[0]),
            period_start=date(2026,1,1),period_end=date(2026,12,31)))
        self.assertEqual(result.data['total_diagnosticos'],1)
        self.assertEqual(result.data['historico'][0]['id'],self.legacy['diagnosticos'])

    def test_daily_conflict_whatsapp_create_and_contextual_update(self):
        from dataclasses import replace
        from app.services.care_lines import NEURO,CARDIO,CareOrigin
        from app.services.daily_record import DailyRecordService,DailyRecordSubmission,ActorRef
        from app.services.daily_record.exceptions import DailyRecordNotFound,DuplicateDailyRecord
        from app.services.daily_record.providers.neuro import NeuroDailyRecordProvider,FIELDS
        from app.services.daily_record.providers.cardio import CardioDailyRecordProvider
        from app.services.whatsapp_daily_record import record_exists
        from app.models.modular import RegistroLongitudinal
        self.db.execute(text("UPDATE formularios_modulo SET ativo=true WHERE id=:id"),dict(id=self.form))
        for name in FIELDS:
            self.db.execute(text("INSERT INTO campos_formulario(formulario_id,nome_campo,label,tipo_campo,ativo) VALUES (:f,:n,:n,'texto',true)"),dict(f=self.form,n=name))
        responsible=self.db.execute(text("INSERT INTO responsaveis(nome,email,senha_hash) VALUES ('Synthetic',:e,'test') RETURNING id"),dict(e=str(self.patient)+'@example.invalid')).scalar()
        self.db.execute(text("UPDATE registros_longitudinais SET data_registro=:d,origem='RESPONSAVEL_APP',criado_por_responsavel_id=:r WHERE id=:id"),dict(d=date.today(),r=responsible,id=self.contextual['registros_longitudinais']))
        self.db.commit()
        for base,provider in ((NEURO,NeuroDailyRecordProvider()),(CARDIO,CardioDailyRecordProvider())):
            line=replace(base,module_id=self.modules[0])
            submission=DailyRecordSubmission(self.patient,line.code,date.today(),CareOrigin.RESPONSAVEL_APP,ActorRef('RESPONSIBLE',responsible),{})
            self.assertFalse(record_exists(self.db,self.patient,line,date.today(),responsible))
            provider.prepare(self.db,line,submission)  # Contextual observation is not a legacy duplicate.
            service=DailyRecordService(resolver=SimpleNamespace(resolve=lambda *args:line))
            with self.assertRaises(DailyRecordNotFound):service.update(self.db,self.contextual['registros_longitudinais'],submission)
            created=service.create(self.db,submission)
            self.assertIsNone(self.db.get(RegistroLongitudinal,created.record_id).contexto_assistencial_id)
            self.assertTrue(record_exists(self.db,self.patient,line,date.today(),responsible))
            with self.assertRaises(DuplicateDailyRecord):provider.prepare(self.db,line,submission)
            self.db.execute(text('DELETE FROM respostas_registro WHERE registro_id=:id'),dict(id=created.record_id))
            self.db.execute(text('DELETE FROM registros_longitudinais WHERE id=:id'),dict(id=created.record_id));self.db.commit()

    def test_legacy_diagnosis_and_intervention_creation_remain_null(self):
        from datetime import datetime
        from app.schemas.diagnostico import DiagnosticoCreate
        from app.services.diagnostico_service import DiagnosticoService
        from app.services.interventions.adapters import GenericAdapter
        payload=DiagnosticoCreate(paciente_id=self.patient,care_line='NEURO',descricao_clinica='Synthetic',medico_nome='Synthetic',data_diagnostico=date.today())
        diagnosis=DiagnosticoService.criar(self.db,payload,self.modules[0])
        self.assertIsNone(diagnosis.contexto_assistencial_id)
        intervention=GenericAdapter().create(self.db,SimpleNamespace(reference_datetime=datetime.now(),payload={},type='Synthetic',narrative='Synthetic'),SimpleNamespace(module_id=self.modules[0]),self.user,SimpleNamespace(id=self.patient))
        self.assertIsNone(intervention.contexto_assistencial_id)

    def test_responsible_cardio_and_alert_aggregation(self):
        from app.routers import responsavel_cardio as router,cardiometabolico
        self.db.execute(text("INSERT INTO modulos_clinicos(id,nome,slug) VALUES (2,'Cardio','cardiometabolico') ON CONFLICT (id) DO UPDATE SET slug='cardiometabolico'"))
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id) VALUES (:c,2) ON CONFLICT DO NOTHING'),dict(c=self.contexts[0]))
        self.db.execute(text('UPDATE formularios_modulo SET modulo_id=2 WHERE id=:id'),dict(id=self.form))
        field=self.db.execute(text("INSERT INTO campos_formulario(formulario_id,nome_campo,label,tipo_campo) VALUES (:f,'glicemia_jejum','Synthetic','numero') RETURNING id"),dict(f=self.form)).scalar()
        for identity,value in ((self.legacy['registros_longitudinais'],90),(self.contextual['registros_longitudinais'],999)):
            self.db.execute(text("UPDATE registros_longitudinais SET modulo_id=2,origem='RESPONSAVEL_APP' WHERE id=:id"),dict(id=identity))
            self.db.execute(text('INSERT INTO respostas_registro(registro_id,campo_id,valor_numero) VALUES (:r,:f,:v)'),dict(r=identity,f=field,v=value))
        self.db.commit()
        with patch.object(router,'validar_vinculo_ativo',return_value=True):
            rows=router.listar_registros_cardio_responsavel(self.patient,self.db,self.user)
        self.assertEqual([r['id'] for r in rows],[self.legacy['registros_longitudinais']])
        self.assertEqual(rows[0]['glicemia_jejum'],90)
        self.assertFalse([r for r in cardiometabolico.alertas_cardiometabolico(self.db)['alertas'] if r['paciente_id']==self.patient])

    def test_recalculator_does_not_select_or_update_contextual(self):
        import runpy
        self.db.execute(text("INSERT INTO modulos_clinicos(id,nome,slug) VALUES (2,'Script fixture','script-fixture') ON CONFLICT (id) DO NOTHING"))
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id) VALUES (:c,2) ON CONFLICT DO NOTHING'),dict(c=self.contexts[0]))
        for identity in (self.legacy['registros_longitudinais'],self.contextual['registros_longitudinais']):
            self.db.execute(text('UPDATE registros_longitudinais SET modulo_id=2,score_clinico=1001 WHERE id=:id'),dict(id=identity))
        self.db.commit()
        expected=self.db.execute(text('SELECT count(*) FROM registros_longitudinais WHERE modulo_id=2 AND contexto_assistencial_id IS NULL')).scalar()
        with patch('app.database.SessionLocal',return_value=self.db), patch('app.services.cardiometabolico_engine.calcular_score',return_value=42) as calculate:
            runpy.run_path(str(Path(__file__).resolve().parents[1]/'app/scripts/recalcular_scores_cardio.py'))
        self.assertEqual(calculate.call_count,expected)
        for identity,score in ((self.legacy['registros_longitudinais'],42),(self.contextual['registros_longitudinais'],1001)):
            self.assertEqual(self.db.execute(text('SELECT score_clinico FROM registros_longitudinais WHERE id=:id'),dict(id=identity)).scalar(),score)

    def test_generic_interventions_and_legacy_detail(self):
        from app.services.interventions.adapters import GenericAdapter
        from app.services.longitudinal.adapters.intervencao import IntervencaoAdapter
        adapter=GenericAdapter()
        self.assertIsNone(adapter.get(self.db,self.contextual['intervencoes'],lock=True))
        self.assertEqual([r.id for r in adapter.list_for_patient(self.db,self.patient)],[self.legacy['intervencoes']])
        self.absent(IntervencaoAdapter().build_response,self.db,self.contextual['intervencoes'])
        from app.services.interventions.service import InterventionService
        from app.services.interventions.models import SourceType
        from app.services.interventions.exceptions import InterventionNotFound
        service=InterventionService()
        for operation in (lambda:service.update(self.db,SourceType.GENERIC_INTERVENTION,self.contextual['intervencoes'],None,user=self.user),
                          lambda:service.delete(self.db,SourceType.GENERIC_INTERVENTION,self.contextual['intervencoes'],user=self.user)):
            with self.assertRaises(InterventionNotFound):operation()
        self.assertEqual(self.db.execute(text('SELECT tipo FROM intervencoes WHERE id=:id'),dict(id=self.contextual['intervencoes'])).scalar(),'Synthetic')

    def test_pts_commands_conflicts_and_creation(self):
        from app.services.care_plan_service import CarePlanService
        from app.services.pts_service import PTSService
        service=CarePlanService()
        self.assertEqual([r.id for r in service.list_plans(self.db,self.patient,self.user)],[self.legacy['pts']])
        self.assertEqual([r.id for r in PTSService.get_patient_pts(self.db,self.patient)],[self.legacy['pts']])
        for closed in (True,False): self.absent(service.set_closed,self.db,self.contextual['pts'],self.user,closed)
        self.db.execute(text("UPDATE pts SET status='ENCERRADO' WHERE id=:id"),{'id':self.legacy['pts']});self.db.commit()
        service.conflict(self.db,self.patient,self.modules[0])  # Contextual ATIVO is irrelevant.
        service.resolver=SimpleNamespace(resolve=lambda *args:SimpleNamespace(module_id=self.modules[0]))
        created=service.create(self.db,SimpleNamespace(paciente_id=self.patient,modulo_id=self.modules[0],data_inicio=date.today(),objetivo_geral='Synthetic',observacoes=None),self.user)
        self.assertIsNone(created.contexto_assistencial_id)

    def test_sources_limit_ranking_and_ancestral_assessments(self):
        for table,fn in [('registros_longitudinais',sources.daily_records),('diagnosticos',sources.diagnoses),('intervencoes',sources.generic_interventions)]:
            with self.subTest(table=table):
                rows=fn(self.db,self.patient,CareLineRegistry(),limit=1)
                self.assertEqual([r.source_id for r in rows],[self.legacy[table]])
        from app.services.cardio_evolution import evolution
        self.assertEqual([r['record_id'] for r in evolution(self.db,[self.patient],self.modules[0],latest_only=True)],[self.legacy['registros_longitudinais']])
        from app.services.clinical_reading.providers.cardio import read_cardio, read_cardio_many
        from app.services.care_lines import CARDIO
        from dataclasses import replace
        line=replace(CARDIO,module_id=self.modules[0])
        self.assertEqual(read_cardio(self.db,self.patient,line),read_cardio_many(self.db,[self.patient],line)[self.patient])
        self.assertNotIn('2099',str(read_cardio(self.db,self.patient,line)))

    def test_assessment_orphans_and_mismatched_patient_cannot_hide_context(self):
        from app.routers.assessments import listar_assessments_paciente, obter_assessment, obter_assessment_por_registro
        from app.services.longitudinal.adapters.mchat import MChatAdapter
        ids=[]
        for record in (self.legacy['registros_longitudinais'],self.contextual['registros_longitudinais'],2147483647):
            ids.append(self.db.execute(text("INSERT INTO avaliacoes_clinicas(paciente_id,modulo_id,registro_id,instrumento) VALUES (:p,:m,:r,'MCHAT') RETURNING id"),dict(p=self.patient,m=self.modules[0],r=record)).scalar())
        self.db.commit()
        self.assertEqual({r['id'] for r in listar_assessments_paciente(self.patient,self.db)},{ids[0],ids[2]})
        for fn,args in ((obter_assessment,(ids[1],)),(obter_assessment_por_registro,(self.contextual['registros_longitudinais'],))): self.absent(fn,*args,db=self.db)
        self.absent(MChatAdapter().build_response,self.db,ids[1])
        self.assertEqual({e.source_id for e in sources.assessments(self.db,self.patient,CareLineRegistry())},{ids[0],ids[2]})
        self.db.execute(text('UPDATE avaliacoes_clinicas SET paciente_id=:p WHERE id=:id'),dict(p=self.other,id=ids[1]));self.db.commit()
        self.assertEqual(sources.assessments(self.db,self.other,CareLineRegistry()),[])

    def test_cockpit_counts_and_context_only_patient_preserved(self):
        from app.services.cockpit_gestao_service import CockpitGestaoService as Cockpit
        counts=Cockpit.obter_contadores_por_paciente(self.db,self.user)
        self.assertEqual(counts[self.patient]['total_intervencoes'],1)
        self.db.execute(text('DELETE FROM intervencoes WHERE id=:id'),{'id':self.legacy['intervencoes']})
        self.db.execute(text('DELETE FROM registros_longitudinais WHERE id=:id'),{'id':self.legacy['registros_longitudinais']});self.db.commit()
        counts=Cockpit.obter_contadores_por_paciente(self.db,self.user)
        self.assertIn(self.patient,counts)
        self.assertEqual(counts[self.patient],dict(total_registros=0,total_intervencoes=0))

    def test_timeline_own_acquisitions(self):
        from app.services.timeline_service import TimelineService
        self.assertEqual(len(TimelineService.get_daily_records(self.db,self.patient)),1)
        self.assertEqual(len(TimelineService.get_interventions(self.db,self.patient)),1)

    def test_view_upgrade_downgrade_reupgrade_and_legacy_equivalence(self):
        migration=importlib.import_module('alembic_canonical.versions.w1c_isolamento_legado_v1')
        # Only metadata/fixtures in an isolated, rolled-back transaction.
        with self.engine.connect() as c:
            tx=c.begin()
            try:
                c.execute(text("INSERT INTO registros_diarios(paciente_id,data,sono_qualidade,irritabilidade,crise_sensorial) VALUES (:p,'2026-02-01','BOA','BAIXA',true)"),dict(p=self.patient))
                c.exec_driver_sql('CREATE VIEW public.vw_timeline_paciente AS '+migration.TIMELINE)
                command.downgrade(config(c),'w1c_contexto_clinico_v1')
                old=c.execute(text("SELECT * FROM vw_timeline_paciente WHERE paciente_id=:p AND NOT (id=:id AND tipo_evento='INTERVENCAO') ORDER BY tipo_evento,id"),dict(p=self.patient,id=self.contextual['intervencoes'])).all()
                command.upgrade(config(c),'head')
                rows=c.execute(text("SELECT * FROM vw_timeline_paciente WHERE paciente_id=:p ORDER BY tipo_evento,id"),dict(p=self.patient)).all()
                self.assertEqual(rows,old)
                columns=c.exec_driver_sql("SELECT attname,format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid='vw_timeline_paciente'::regclass AND attnum>0 ORDER BY attnum").all()
                self.assertEqual(columns,[('id','integer'),('paciente_id','integer'),
                    ('tipo_evento','character varying'),('data','timestamp without time zone'),
                    ('descricao','text'),('usuario_id','integer'),('origem','character varying'),
                    ('sono_qualidade','character varying'),('irritabilidade','character varying'),('crise_sensorial','boolean')])
                dependencies=c.exec_driver_sql("SELECT DISTINCT cl.relname FROM pg_rewrite r JOIN pg_depend d ON d.objid=r.oid JOIN pg_class cl ON cl.oid=d.refobjid WHERE r.ev_class='vw_timeline_paciente'::regclass AND d.refclassid='pg_class'::regclass AND cl.oid<>r.ev_class").scalars().all()
                self.assertEqual(set(dependencies),{'registros_diarios','intervencoes'})
                command.downgrade(config(c),'w1c_contexto_clinico_v1')
                self.assertEqual(c.execute(text('SELECT count(*) FROM vw_timeline_paciente WHERE paciente_id=:p'),dict(p=self.patient)).scalar(),3)
                command.upgrade(config(c),'head')
                self.assertEqual(c.execute(text('SELECT count(*) FROM vw_timeline_paciente WHERE paciente_id=:p'),dict(p=self.patient)).scalar(),2)
            finally: tx.rollback()


import test_sessions_attendance as attendance


class DescendantIsolationTests(unittest.TestCase):
    setUp = attendance.SessionFixture.setUp
    tearDown = attendance.SessionFixture.tearDown
    create = attendance.SessionFixture.create
    agenda = attendance.SessionFixture.agenda
    sessions = attendance.SessionFixture.sessions
    observation_session = attendance.SessionFixture.observation_session

    def test_contextual_tree_absent_from_lists_and_commands(self):
        from app.models import PTS, AgendaCuidado, PTSObjetivo, SessaoAssistencial
        from app.services.session_service import SessionService
        from app.services.pts_service import PTSService
        from app.routers.sessoes_assistenciais import buscar_sessao
        legacy=self.observation_session()
        legacy_agenda=self.db.get(AgendaCuidado,legacy.agenda_cuidado_id)
        self.db.get(PTS,legacy_agenda.pts_id).status='ENCERRADO';self.db.commit()
        contextual=self.observation_session()
        agenda=self.db.get(AgendaCuidado,contextual.agenda_cuidado_id)
        self.db.get(PTS,agenda.pts_id).contexto_assistencial_id=42
        self.db.commit()
        service=SessionService()
        self.assertEqual([s.id for s in service.patient_sessions(self.db,10,self.user)],[legacy.id])
        self.assertEqual(PTSService.get_care_plans(self.db,agenda.pts_id),[])
        calls=[lambda:buscar_sessao(contextual.id,self.db),
               lambda:self.service.plan(self.db,agenda.pts_id,self.user),
               lambda:self.service.objective(self.db,agenda.objetivo_id,self.user),
               lambda:self.service.agenda(self.db,agenda.id,self.user),
               lambda:service.transition(self.db,contextual.id,self.user,'finalizar')]
        for call in calls:
            with self.assertRaises(HTTPException) as error:call()
            self.assertEqual(error.exception.status_code,404)
        self.assertEqual(self.db.get(SessaoAssistencial,contextual.id).status,'EM_ANDAMENTO')
        self.assertIsNone(self.db.get(PTS,legacy_agenda.pts_id).contexto_assistencial_id)

    def test_session_recent_interventions_filtered_before_limit(self):
        from app.models import Intervencao, AvaliacaoClinica
        from app.services.assistential_session_service import AssistentialSessionService
        from datetime import datetime
        session=self.observation_session()
        for model in (Intervencao,AvaliacaoClinica):model.__table__.create(self.engine,checkfirst=True)
        for identity in range(1,8):
            self.db.add(Intervencao(id=identity,paciente_id=10,modulo_id=1,tipo='Synthetic',
                data_intervencao=datetime(2026,1,identity),contexto_assistencial_id=42 if identity>5 else None))
        self.db.commit()
        result=AssistentialSessionService.get_session_details(self.db,session.id)
        self.assertEqual([i['id'] for i in result['intervencoes']], [5,4,3,2,1])


import test_financeiro_projection as financial


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class FinancialAndViewIsolationTests(unittest.TestCase):
    setUpClass=classmethod(financial.ProjectionPostgresTests.setUpClass.__func__)
    tearDownClass=classmethod(financial.ProjectionPostgresTests.tearDownClass.__func__)
    setUp=financial.ProjectionPostgresTests.setUp
    tearDown=financial.ProjectionPostgresTests.tearDown
    session=financial.ProjectionPostgresTests.session
    request=financial.ProjectionPostgresTests.request
    preview=financial.ProjectionPostgresTests.preview

    def contextual_agenda(self):
        with self.engine.begin() as c:
            params=dict(p=self.patient,i=self.owner,u=self.actor,a=self.agenda)
            link=c.execute(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,'OUTRO','2020-01-01') RETURNING id"),params).scalar()
            params['link']=link
            ctx=c.execute(text("INSERT INTO contextos_assistenciais(paciente_instituicao_id,paciente_id,instituicao_id,data_inicio,criado_por_usuario_id) VALUES (:link,:p,:i,'2020-01-01',:u) RETURNING id"),params).scalar()
            c.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id) VALUES (:c,1)'),dict(c=ctx))
            plan=c.execute(text('INSERT INTO pts(paciente_id,modulo_id,contexto_assistencial_id) VALUES (:p,1,:c) RETURNING id'),dict(p=self.patient,c=ctx)).scalar()
            obj=c.execute(text("INSERT INTO pts_objetivos(pts_id,descricao) VALUES (:p,'Contextual') RETURNING id"),dict(p=plan)).scalar()
            return c.execute(text('''INSERT INTO agenda_cuidados(pts_id,objetivo_id,atividade_id,ocupacao_id,frequencia_semanal,duracao_minutos,data_inicio)
                SELECT :p,:o,atividade_id,ocupacao_id,99,duracao_minutos,data_inicio FROM agenda_cuidados WHERE id=:a RETURNING id'''),dict(p=plan,o=obj,a=self.agenda)).scalar()

    def view_rows(self):
        with self.engine.connect() as c:
            return {name:c.exec_driver_sql('SELECT * FROM '+name+' ORDER BY modulo_id,ocupacao_id').all()
                    for name in ('vw_dimensionamento_ocupacao','vw_demanda_capacidade')}

    def test_financial_sessions_gaps_and_dimensions_are_identical(self):
        before=self.preview()
        agenda=self.contextual_agenda()
        self.assertEqual(self.preview(),before)  # No contextual gap.
        self.session(self.start,agenda=agenda)
        self.assertEqual(self.preview(),before)  # No contextual quantity or pending price.

    def test_dimension_and_demand_unchanged_by_contextual_plan(self):
        before=self.view_rows()
        self.contextual_agenda()
        self.assertEqual(self.view_rows(),before)
        with self.engine.connect() as c:
            tx=c.begin()
            try:
                command.downgrade(config(c),'w1c_contexto_clinico_v1')
                raw=c.exec_driver_sql('SELECT sum(total_planejamentos) FROM vw_dimensionamento_ocupacao').scalar()
                self.assertEqual(raw,2)
                command.upgrade(config(c),'head')
                self.assertEqual(c.exec_driver_sql('SELECT sum(total_planejamentos) FROM vw_dimensionamento_ocupacao').scalar(),1)
            finally:tx.rollback()
