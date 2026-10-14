"""Restricted operational aggregates; small-group residual inference is accepted, not anonymity."""
import json
import os
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import text, event
import test_cockpit_mental as foundation
from app.core.deps import get_usuario_atual
from app.services.cockpit_gestao_mental import (
    CockpitGestaoMentalService, closed_weeks, ManagementPeriodInvalid,
)

DAY = date(2026, 10, 13)
START, END = date(2026, 10, 5), date(2026, 10, 11)
PATH = '/saude-mental/cockpit/gestao'


class PeriodTests(unittest.TestCase):
    def test_complete_week_windows_and_rollover(self):
        for weeks in (4,8,12):
            start,end=closed_weeks(weeks,DAY)
            self.assertEqual(start.weekday(),0)
            self.assertEqual(end,END)
            self.assertEqual((end-start).days+1,7*weeks)
            self.assertEqual(closed_weeks(weeks,date(2026,10,12)),(start,end))
            self.assertEqual(closed_weeks(weeks,date(2026,10,19)),(start+timedelta(days=7),end+timedelta(days=7)))

    def test_invalid_periods(self):
        for weeks in (0,1,5,13,None,True,'4'):
            with self.subTest(weeks=weeks), self.assertRaises(ManagementPeriodInvalid):
                closed_weeks(weeks,DAY)


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class ManagementTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(foundation.CockpitTests.setUpClass.__func__)
    tearDownClass=classmethod(foundation.CockpitTests.tearDownClass.__func__)
    tearDown=foundation.CockpitTests.tearDown
    command_grant=foundation.CockpitTests.command_grant
    path=foundation.CockpitTests.path
    request=foundation.CockpitTests.request
    create=foundation.CockpitTests.create
    session=foundation.CockpitTests.session
    wellbeing=foundation.CockpitTests.wellbeing
    second_institution=foundation.CockpitTests.second_institution

    def setUp(self):
        foundation.CockpitTests.setUp(self)
        self.day=DAY
        self.s=CockpitGestaoMentalService()
        self.db.execute(text('UPDATE pacientes SET ativo=true WHERE id=:p'),dict(p=self.patient))
        self.db.execute(text("UPDATE usuario_instituicao_acessos SET perfil_institucional='GESTOR' WHERE id=:r"),dict(r=self.roots[0]))
        self.db.commit()

    def get(self, actor=None, **params):
        self.app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=actor or self.actor)
        with patch('app.services.cockpit_gestao_mental.today_local',return_value=DAY):
            return self.client.get(PATH,params=params)

    def test_admin_explicit_global_and_inactive_denied(self):
        response=self.get(actor=self.platform_admin)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['metadados']['escopo'],'GLOBAL')
        self.assertIn(self.institutions[1],response.json()['metadados']['instituicao_ids'])
        self.db.execute(text('UPDATE usuarios SET ativo=false WHERE id=:u'),dict(u=self.platform_admin));self.db.commit()
        self.assertEqual(self.get(actor=self.platform_admin).status_code,403)

    def test_authentication_required(self):
        self.app.dependency_overrides.pop(get_usuario_atual)
        self.assertEqual(self.client.get(PATH).status_code,401)

    def test_manager_explicit_roots_no_hierarchy_inheritance(self):
        self.db.execute(text('UPDATE instituicoes SET instituicao_pai_id=:p WHERE id=:i'),dict(p=self.institution,i=self.institutions[1]));self.db.commit()
        r=self.get();self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['metadados']['instituicao_ids'],[self.institution])
        denied=self.get(instituicao_id=self.institutions[1])
        missing=self.get(instituicao_id=2147483647)
        self.assertEqual((denied.status_code,denied.json()),(missing.status_code,missing.json()))
        self.assertEqual(denied.status_code,403)
        self.db.execute(text("UPDATE usuario_instituicao_acessos SET ativo=true,perfil_institucional='GESTOR' WHERE id=:r"),dict(r=self.roots[1]));self.db.commit()
        self.assertEqual(self.get().json()['metadados']['instituicao_ids'],sorted(self.institutions[:2]))
        self.assertEqual(self.get(instituicao_id=self.institutions[1]).json()['metadados']['instituicao_ids'],[self.institutions[1]])

    def test_professional_support_and_global_manager_not_automatic(self):
        for role in ('PROFISSIONAL','SUPORTE'):
            self.db.execute(text('UPDATE usuario_instituicao_acessos SET perfil_institucional=:p WHERE id=:r'),dict(p=role,r=self.roots[0]))
            self.db.execute(text("UPDATE usuarios SET perfil='GESTOR' WHERE id=:u"),dict(u=self.actor));self.db.commit()
            self.assertEqual(self.get().status_code,403)

    def test_inactive_root_person_institution(self):
        for sql, identity in [('UPDATE usuario_instituicao_acessos SET ativo=false WHERE id=:i',self.roots[0]),
                              ('UPDATE pessoas SET ativo=false WHERE id=(SELECT pessoa_id FROM usuarios WHERE id=:i)',self.actor),
                              ('UPDATE instituicoes SET ativo=false WHERE id=:i',self.institution)]:
            self.db.execute(text(sql),dict(i=identity))
            self.assertEqual(self.get(instituicao_id=self.institution).status_code,403)
            self.db.rollback()

    def test_read_only_authorization_first_no_clinical_payload(self):
        statements=[]
        def before(conn,cursor,statement,parameters,context,many): statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',before)
        try:
            with patch.object(self.db,'commit',side_effect=AssertionError('GET commit')), patch.object(self.db,'flush',side_effect=AssertionError('GET flush')):
                self.assertEqual(self.get().status_code,200)
            self.assertTrue(all(s.lstrip().upper().startswith(('SELECT','WITH')) for s in statements))
            for statement in statements:
                self.assertNotRegex(statement.upper(),r'\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP)\b')
            self.assertFalse(any('respostas_registro' in s for s in statements))
            with patch.object(CockpitGestaoMentalService,'_aggregate',side_effect=AssertionError('aggregate before authorization')):
                self.assertEqual(self.get(instituicao_id=2147483647).status_code,403)
        finally:
            event.remove(self.engine,'before_cursor_execute',before)

    def output(self, **params):
        r=self.get(**params)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def test_windows_http_and_arbitrary_dates_rejected(self):
        for weeks in (4,8,12):
            r=self.output(semanas=weeks)
            self.assertEqual(len(r['evolucao_atendimentos']),weeks)
            self.assertEqual(len(r['atendimentos_programados_realizados']),weeks)
            self.assertEqual(r['metadados']['data_inicio'],str(closed_weeks(weeks,DAY)[0]))
        for params in (dict(semanas=5),dict(semanas=0),dict(semanas='x'),dict(data_inicio=str(START)),dict(data_fim=str(END))):
            self.assertEqual(self.get(**params).status_code,422)

    def test_known_sessions_canonical_dates_and_reused_evolution(self):
        self.session(-7,'AGENDADA')
        self.session(-6,'CONFIRMADA')
        self.session(-5,'EM_ANDAMENTO')
        self.session(-4,'FALTOU')
        self.session(-3,'REALIZADA',END)
        self.session(-7,'CANCELADA')
        self.session(-7,'REAGENDADA')
        self.session(-35,'REALIZADA',START)  # realization belongs, scheduling does not
        self.session(-14,'REALIZADA',date(2026,10,12)) # scheduling belongs, realization does not
        self.session(1)
        r=self.output()
        self.assertEqual(r['indicadores']['atendimentos_programados'],6)
        self.assertEqual(r['indicadores']['atendimentos_realizados'],2)
        series=r['atendimentos_programados_realizados']
        self.assertEqual(series[-1]['programados'],5)
        self.assertEqual(series[-1]['realizados'],2)
        self.assertEqual(sum(x['programados'] for x in series),6)
        self.assertEqual(r['evolucao_atendimentos'],[dict(semana=x['semana'],realizados=x['realizados']) for x in series])

    def test_missing_realization_and_updated_at_do_not_create_realizations(self):
        self.session(-7,'REALIZADA')
        self.session(-7,'REALIZADA',DAY+timedelta(days=1))
        self.session(-7,'AGENDADA',START)
        r=self.output()['indicadores']
        self.assertEqual(r['atendimentos_programados'],3)
        self.assertEqual(r['atendimentos_realizados'],0)

    def test_closed_context_line_and_link_preserve_history(self):
        self.session(-7,'REALIZADA',START)
        self.db.execute(text('UPDATE contextos_assistenciais SET data_fim=:d,ativo=false WHERE id=:c'),dict(d=END,c=self.open))
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c'),dict(c=self.open))
        self.db.execute(text('UPDATE paciente_instituicoes SET ativo=false WHERE id=(SELECT paciente_instituicao_id FROM contextos_assistenciais WHERE id=:c)'),dict(c=self.open))
        self.db.commit()
        self.assertEqual(self.output()['indicadores']['atendimentos_realizados'],1)

    def test_legacy_other_line_and_inconsistent_executor_excluded(self):
        session=self.session(-7,'REALIZADA',START)
        self.assertEqual(self.output()['indicadores']['atendimentos_realizados'],1)
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,1,true)'),dict(c=self.open));self.db.commit()
        for sql,params in [
            ('UPDATE pts SET contexto_assistencial_id=NULL WHERE id=:i',dict(i=self.plan)),
            ('UPDATE pts SET modulo_id=1 WHERE id=:i',dict(i=self.plan)),
            ('UPDATE sessoes_assistenciais SET profissional_id=NULL WHERE id=:i',dict(i=session))]:
            self.db.execute(text(sql),params)
            self.assertEqual(self.output()['indicadores']['atendimentos_realizados'],0)
            self.db.rollback()

    def test_institutions_and_professionals_are_current_administrative_counts(self):
        self.db.execute(text("UPDATE profissional_instituicoes SET data_inicio='2020-01-01',data_fim=NULL,ativo=true"))
        self.db.execute(text('UPDATE profissionais SET ativo=true WHERE id=:p'),dict(p=self.executor))
        self.db.execute(text('UPDATE pessoas SET ativo=true WHERE id=(SELECT pessoa_id FROM profissionais WHERE id=:p)'),dict(p=self.executor))
        self.db.commit()
        self.db.execute(text('UPDATE profissional_instituicoes SET ativo=false WHERE profissional_id<>:p'),dict(p=self.executor));self.db.commit()
        # One professional, multiple institutions and occupations: one count.
        occupation=self.db.scalar(text("INSERT INTO ocupacoes_profissionais(nome) VALUES ('Synthetic second occupation') RETURNING id"))
        self.db.execute(text("INSERT INTO profissional_instituicoes(profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (:p,:i,:o,'2020-01-01')"),dict(p=self.executor,i=self.institution,o=occupation))
        self.db.commit()
        r=self.output(actor=self.platform_admin)
        self.assertEqual(r['indicadores']['instituicoes_ativas'],len(r['metadados']['instituicao_ids']))
        self.assertEqual(r['indicadores']['profissionais_vinculados'],1)
        for sql in [
            'UPDATE profissional_instituicoes SET ativo=false',
            "UPDATE profissional_instituicoes SET data_fim='2026-10-12'",
            "UPDATE profissional_instituicoes SET data_inicio='2026-10-14'",
            'UPDATE profissionais SET ativo=false',
            'UPDATE pessoas SET ativo=false WHERE id IN (SELECT pessoa_id FROM profissionais)']:
            self.db.execute(text(sql))
            self.assertEqual(self.output(actor=self.platform_admin)['indicadores']['profissionais_vinculados'],0)
            self.db.rollback()
        self.db.execute(text('UPDATE instituicoes SET ativo=false WHERE id=:i'),dict(i=self.institutions[1]))
        other=self.output(actor=self.platform_admin)
        self.assertEqual(other['indicadores']['instituicoes_ativas'],r['indicadores']['instituicoes_ativas']-1)

    def test_small_counts_visible_without_individual_or_clinical_data(self):
        self.session(-7,'REALIZADA',START)
        r=self.output()
        self.assertEqual(r['indicadores']['atendimentos_realizados'],1)
        self.assertEqual(set(r['indicadores']),{'instituicoes_ativas','profissionais_vinculados','atendimentos_programados','atendimentos_realizados'})
        self.assertTrue(any('inferência residual' in x for x in r['metadados']['limitacoes']))
        for forbidden in ('pessoa_id','paciente_id','profissional_id','contexto_assistencial_id','narrativa','respostas','checkins','taxa_realizacao','PROTEGIDO'):
            self.assertNotIn(forbidden,json.dumps(r))

    def test_authorization_revocation_precedes_aggregation(self):
        self.db.execute(text('UPDATE usuario_instituicao_acessos SET ativo=false WHERE id=:i'),dict(i=self.roots[0]));self.db.commit()
        with patch.object(self.s,'_aggregate',side_effect=AssertionError('unauthorized aggregation')):
            from app.services.cockpit_gestao_mental import ManagementDenied
            with self.assertRaises(ManagementDenied):
                self.s.compose(self.db,actor_id=self.actor)

    def test_institutional_isolation_and_zero_without_sessions(self):
        self.assertEqual(self.output()['indicadores']['atendimentos_programados'],0)
        before=self.output(actor=self.platform_admin)['indicadores']['atendimentos_realizados']
        self.session(-7,'REALIZADA',START)
        other=self.output(actor=self.platform_admin,instituicao_id=self.institutions[1])
        self.assertEqual(other['indicadores']['atendimentos_realizados'],0)
        self.assertEqual(self.output(actor=self.platform_admin)['indicadores']['atendimentos_realizados'],before+1)

    def test_window_boundaries_and_longer_windows(self):
        start,end=closed_weeks(4,DAY)
        for day in (start-timedelta(days=1),start,end,end+timedelta(days=1)):
            self.session((day-DAY).days,'REALIZADA',day)
        r=self.output()['indicadores']
        self.assertEqual((r['atendimentos_programados'],r['atendimentos_realizados']),(2,2))
        r=self.output(semanas=8)['indicadores']
        self.assertEqual((r['atendimentos_programados'],r['atendimentos_realizados']),(3,3))
