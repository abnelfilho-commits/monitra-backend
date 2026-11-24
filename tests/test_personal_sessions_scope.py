"""SEC-002: real route/ACL queries in disposable PostgreSQL; synthetic identities."""
import os
import unittest
from sqlalchemy import text, event
from app.core.deps import get_usuario_atual
from app.models import Usuario
import test_sessoes_mentais as base


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class PersonalScopeTests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(base.OperationalSessionTests.setUpClass.__func__)
    tearDownClass = classmethod(base.OperationalSessionTests.tearDownClass.__func__)
    tearDown = base.OperationalSessionTests.tearDown
    command_grant = base.OperationalSessionTests.command_grant
    path = base.OperationalSessionTests.path
    request = base.OperationalSessionTests.request
    create = base.OperationalSessionTests.create
    generate = base.OperationalSessionTests.generate
    shared = base.OperationalSessionTests.shared

    def setUp(self):
        base.OperationalSessionTests.setUp(self)
        self.app.dependency_overrides[get_usuario_atual] = lambda: self.db.get(Usuario, self.actor)

    def get(self, line=None):
        return self.client.request('GET', '/sessoes-assistenciais/minhas', params={} if line is None else {'care_line': line})

    def ids(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return [x['id'] for x in response.json()]

    def test_contextual_without_legacy_identity_and_default(self):
        self.generate()
        expected = self.ids(self.get())
        self.assertEqual(len(expected), 52)
        self.assertEqual(self.ids(self.get('SAUDE_MENTAL')), expected)
        self.assertEqual(self.ids(self.get('MENTAL_HEALTH')), expected)
        self.assertEqual(self.get('NEURO').status_code, 403)

    def test_authorized_context_no_sessions(self):
        self.assertEqual(self.ids(self.get('SAUDE_MENTAL')), [])

    def test_invalid_line(self):
        self.assertEqual(self.get('UNKNOWN').status_code, 422)

    def test_inactive_module(self):
        self.db.execute(text('UPDATE modulos_clinicos SET ativo=false WHERE id=3'))
        self.assertEqual(self.get('SAUDE_MENTAL').status_code, 400)

    def test_inactive_context_line(self):
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c'), dict(c=self.open))
        self.assertEqual(self.get('SAUDE_MENTAL').status_code, 403)

    def test_revoked_grant(self):
        self.generate()
        self.db.execute(text("UPDATE concessoes_assistenciais SET revogado_em=now(),revogado_por_usuario_id=:u,motivo_revogacao='Synthetic',revogacao_origem='MANUAL' WHERE id=:g"),
                        dict(u=self.actor,g=self.grant_ids[self.open,'ASSISTENCIAL_LER']))
        self.assertEqual(self.get('SAUDE_MENTAL').status_code, 403)
        self.assertEqual(self.ids(self.get()), [])

    def test_expired_participation(self):
        self.db.execute(text("UPDATE contexto_profissionais SET data_inicio=CURRENT_DATE-2,data_fim=CURRENT_DATE-1 WHERE id=:p"),dict(p=self.participations[self.open]))
        self.assertEqual(self.get('SAUDE_MENTAL').status_code,403)

    def test_expired_professional_membership(self):
        self.db.execute(text("UPDATE profissional_instituicoes SET data_inicio=CURRENT_DATE-2,data_fim=CURRENT_DATE-1 WHERE id=:p"),dict(p=self.links[0]))
        self.assertEqual(self.get('SAUDE_MENTAL').status_code,403)

    def test_institution_without_access(self):
        self.generate()
        self.db.execute(text('UPDATE usuario_instituicao_acessos SET ativo=false WHERE usuario_id=:u'),dict(u=self.actor))
        self.assertEqual(self.get('SAUDE_MENTAL').status_code,403)
        self.assertEqual(self.ids(self.get()),[])

    def test_other_professional_assignment(self):
        self.generate()
        self.db.execute(text('UPDATE sessoes_assistenciais SET profissional_id=NULL WHERE agenda_cuidado_id=:a'),dict(a=self.planning))
        self.assertEqual(self.ids(self.get('SAUDE_MENTAL')),[])

    def add_legacy(self):
        clinic=self.db.execute(text("INSERT INTO clinicas(nome) VALUES ('Synthetic clinic') RETURNING id")).scalar_one()
        self.db.execute(text("UPDATE usuarios SET perfil='PROFISSIONAL',clinica_id=:c,profissional_id=:p WHERE id=:u"),dict(c=clinic,p=self.executor,u=self.actor))
        self.db.execute(text('UPDATE profissionais SET clinica_id=:c WHERE id=:p'),dict(c=clinic,p=self.executor))
        self.db.execute(text('INSERT INTO profissional_modulos(profissional_id,modulo_id) VALUES (:p,1)'),dict(p=self.executor))
        patient=self.db.execute(text("INSERT INTO pacientes(nome,clinica_id,ativo) VALUES ('Synthetic',:c,true) RETURNING id"),dict(c=clinic)).scalar_one()
        self.db.execute(text('INSERT INTO paciente_modulos(paciente_id,modulo_id) VALUES (:p,1)'),dict(p=patient))
        plan=self.db.execute(text("INSERT INTO pts(paciente_id,modulo_id,data_inicio) VALUES (:p,1,'2026-11-01') RETURNING id"),dict(p=patient)).scalar_one()
        objective=self.db.execute(text("INSERT INTO pts_objetivos(pts_id,descricao) VALUES (:p,'Synthetic') RETURNING id"),dict(p=plan)).scalar_one()
        agenda=self.db.execute(text("INSERT INTO agenda_cuidados(pts_id,objetivo_id,atividade_id,ocupacao_id,profissional_id,frequencia_semanal,quantidade_sessoes,duracao_minutos,data_inicio) VALUES (:p,:o,:a,:c,:pr,1,1,50,'2026-11-01') RETURNING id"),
            dict(p=plan,o=objective,a=self.activity,c=self.occupation,pr=self.executor)).scalar_one()
        identity=self.db.execute(text("INSERT INTO sessoes_assistenciais(agenda_cuidado_id,paciente_id,profissional_id,numero_sessao,data_agendada,duracao_minutos,status) VALUES (:a,:p,:pr,1,'2026-11-01',50,'AGENDADA') RETURNING id"),dict(a=agenda,p=patient,pr=self.executor)).scalar_one()
        self.db.flush()
        self.db.expire_all()
        return identity,patient

    def test_hybrid_segregation_and_no_duplicates(self):
        mental=set(self.ids(self.get('SAUDE_MENTAL')))  # no sessions yet
        self.assertEqual(mental,set())
        self.generate()
        mental=set(self.ids(self.get('SAUDE_MENTAL')))
        identity,_=self.add_legacy()
        self.assertEqual(self.ids(self.get('NEURO')),[identity])
        self.assertEqual(set(self.ids(self.get('SAUDE_MENTAL'))),mental)
        shared=self.ids(self.get())
        self.assertEqual(set(shared),mental|{identity})
        self.assertEqual(len(shared),len(set(shared)))

    def test_exclusively_legacy_and_patient_default(self):
        identity,patient=self.add_legacy()
        self.db.execute(text('UPDATE usuarios SET pessoa_id=NULL WHERE id=:u'),dict(u=self.actor))
        self.db.expire_all()
        self.assertEqual(self.ids(self.get('NEURO')),[identity])
        self.assertEqual(self.ids(self.get()),[identity])
        self.assertEqual(self.get('SAUDE_MENTAL').status_code,403)
        self.assertEqual(self.ids(self.shared('GET',f'/paciente/{patient}')),[identity])

    def test_neuro_filter_does_not_materialize_contextual_sessions(self):
        self.generate()
        identity,_=self.add_legacy()
        statements=[]
        def capture(conn,cursor,statement,parameters,context,many):
            statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            self.assertEqual(self.ids(self.get('NEURO')),[identity])
        finally:
            event.remove(self.engine,'before_cursor_execute',capture)
        reads=[s for s in statements if s.lstrip().upper().startswith('SELECT') and 'FROM sessoes_assistenciais' in s]
        self.assertTrue(reads)
        self.assertIn('pts.modulo_id =', reads[0])
        # Subsequent ancestry checks may reload the already selected session by ID.
        self.assertTrue(all('pts.modulo_id =' in s or 'sessoes_assistenciais.id =' in s for s in reads))

    def test_legacy_line_revocation(self):
        self.add_legacy()
        self.db.execute(text('DELETE FROM profissional_modulos WHERE profissional_id=:p AND modulo_id=1'),dict(p=self.executor))
        self.assertEqual(self.get('NEURO').status_code,403)
