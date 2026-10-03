"""W1B-D decisions/list equivalence against current, disposable PostgreSQL 18."""
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from app.models.contexto_assistencial import ContextoAssistencial as Contexto
from app.models.permissao_assistencial import ContextoProfissional as Participation, ConcessaoAssistencial as Grant
from app.models.usuario import Usuario
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Root
from app.services.autorizacao_contextual import AutorizacaoContextualService as Evaluator
from app.services.autorizacao_institucional import AutorizacaoInstitucionalService as Roots
import test_permissao_assistencial as foundation

CAPS = ('ASSISTENCIAL_LER', 'ASSISTENCIAL_REGISTRAR', 'CONTEXTO_ADMINISTRAR')
URL = os.getenv('M0_TEST_POSTGRES_URL')


@unittest.skipUnless(URL, 'Requires disposable PostgreSQL 18')
class EvaluatorTests(unittest.TestCase):
    setUpClass = classmethod(foundation.PhysicalTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.PhysicalTests.tearDownClass.__func__)

    def setUp(self):
        foundation.CommandTests.setUp(self)
        self.commands = self.s
        self.s = Evaluator()
        self.today = datetime.now(timezone.utc).date()
        self.closed = self.context
        self.open = self.db.execute(text("""INSERT INTO contextos_assistenciais
            (paciente_instituicao_id,paciente_id,instituicao_id,data_inicio,criado_por_usuario_id)
            SELECT paciente_instituicao_id,paciente_id,instituicao_id,'2021-01-01',criado_por_usuario_id
            FROM contextos_assistenciais WHERE id=:id RETURNING id"""),dict(id=self.closed)).scalar()
        self.authorities = self.commands.bootstrap(self.db,dict(instituicao_id=self.institution,
            usuario_instituicao_acesso_id=self.target_root, motivo='Synthetic bootstrap',
            envelopes=[dict(capacidade_delegavel=c,envelope_tipo='INSTITUICAO') for c in CAPS]),actor_id=self.platform_admin)
        self.grant_ids = {}
        self.participations = {}
        for context in (self.closed,self.open):
            for capability in CAPS[:2]:
                self.grant_ids[context,capability] = self.command_grant(context,capability).id
            row = Participation(instituicao_id=self.institution,contexto_assistencial_id=context,
                profissional_instituicao_id=self.links[0],data_inicio=self.today,
                criado_por_usuario_id=self.platform_admin,motivo_criacao='Current participation')
            self.db.add(row);self.db.flush();self.participations[context]=row.id
        self.grant_ids[self.open,CAPS[2]] = self.command_grant(self.open,CAPS[2]).id
        self.db.commit()

    def tearDown(self):
        self.db.rollback();self.db.close()

    def command_grant(self, context, capability, db=None):
        return self.commands.grant(db or self.db,dict(instituicao_id=self.institution,
            usuario_instituicao_acesso_id=self.roots[0],capacidade=capability,escopo_tipo='CONTEXTO',
            contexto_assistencial_id=context,motivo='Synthetic grant'),actor_id=self.target)

    def query(self, capability=CAPS[0], actor=None, institution=None):
        return self.s.authorized_context_query(actor_id=self.actor if actor is None else actor,
            capability=capability,instituicao_id=self.institution if institution is None else institution)

    def allowed(self, context=None, capability=CAPS[0], actor=None, institution=None, db=None):
        return self.s.authorize_resource(db or self.db,actor_id=self.actor if actor is None else actor,
            capability=capability,instituicao_id=self.institution if institution is None else institution,
            contexto_assistencial_id=self.open if context is None else context)

    def listed(self, capability=CAPS[0], actor=None, institution=None):
        return set(self.db.execute(self.query(capability,actor,institution)).scalars())

    def assert_boundary(self, capability, expected, actor=None, institution=None):
        self.assertEqual(self.listed(capability,actor,institution),set(expected))
        for context in (self.closed,self.open,self.contexts[1],2147483647):
            self.assertEqual(self.allowed(context,capability,actor,institution),context in expected)

    def test_read_write_and_context_administration(self):
        self.assert_boundary(CAPS[0],{self.closed,self.open})
        self.assert_boundary(CAPS[1],{self.open})
        self.assert_boundary(CAPS[2],{self.open})

    def test_historical_read_does_not_require_current_patient_membership(self):
        before=self.db.execute(text('SELECT row_to_json(c) FROM contextos_assistenciais c WHERE id=:i'),dict(i=self.closed)).scalar()
        self.db.execute(text("UPDATE paciente_instituicoes SET ativo=false,data_fim='2020-12-31' WHERE id=:i"),dict(i=before['paciente_instituicao_id']))
        self.assertTrue(self.allowed(self.closed))
        self.assertFalse(self.allowed(self.closed,CAPS[1]))
        self.assertEqual(self.db.execute(text('SELECT row_to_json(c) FROM contextos_assistenciais c WHERE id=:i'),dict(i=self.closed)).scalar(),before)
        row=self.db.get(Participation,self.participations[self.closed])
        self.assertEqual(row.data_inicio,self.today)

    def test_user_person_root_institution_denials_equivalent(self):
        cases=[('UPDATE usuarios SET ativo=false WHERE id=:i',self.actor),
               ('UPDATE usuarios SET pessoa_id=NULL WHERE id=:i',self.actor),
               ('UPDATE pessoas SET ativo=false WHERE id=(SELECT pessoa_id FROM usuarios WHERE id=:i)',self.actor),
               ('UPDATE usuario_instituicao_acessos SET ativo=false WHERE id=:i',self.roots[0]),
               ('UPDATE instituicoes SET ativo=false WHERE id=:i',self.institution)]
        for sql,identity in cases:
            with self.subTest(sql=sql):
                tx=self.db.begin_nested();self.db.execute(text(sql),dict(i=identity))
                for cap in CAPS:self.assert_boundary(cap,set())
                tx.rollback()

    def test_professional_and_link_denials_do_not_block_administration(self):
        cases=[('UPDATE profissionais SET pessoa_id=NULL WHERE id=(SELECT profissional_id FROM profissional_instituicoes WHERE id=:i)',self.links[0]),
               ('UPDATE profissionais SET ativo=false WHERE id=(SELECT profissional_id FROM profissional_instituicoes WHERE id=:i)',self.links[0]),
               ('UPDATE profissional_instituicoes SET ativo=false WHERE id=:i',self.links[0]),
               ("UPDATE profissional_instituicoes SET data_fim='2020-12-31' WHERE id=:i",self.links[0]),
               ("UPDATE profissional_instituicoes SET data_inicio='2099-01-01' WHERE id=:i",self.links[0])]
        for sql,identity in cases:
            with self.subTest(sql=sql):
                tx=self.db.begin_nested();self.db.execute(text(sql),dict(i=identity))
                for cap in CAPS[:2]:self.assert_boundary(cap,set())
                self.assert_boundary(CAPS[2],{self.open})
                tx.rollback()

    def test_canonical_person_mismatch_not_repaired_by_legacy_professional_id(self):
        self.db.execute(text('UPDATE usuarios SET profissional_id=(SELECT profissional_id FROM profissional_instituicoes WHERE id=:l) WHERE id=:u'),dict(l=self.links[0],u=self.actor))
        self.db.execute(text('UPDATE profissionais SET pessoa_id=(SELECT pessoa_id FROM usuarios WHERE id=:u) WHERE id=(SELECT profissional_id FROM profissional_instituicoes WHERE id=:l)'),dict(l=self.links[0],u=self.target))
        self.assert_boundary(CAPS[0],set());self.assert_boundary(CAPS[1],set())

    def test_no_professional_role_denies_clinical_not_administrative(self):
        # The active target account has a canonical person, but no professional role.
        for capability in CAPS:
            self.db.add(Grant(instituicao_id=self.institution,usuario_instituicao_acesso_id=self.target_root,
                capacidade=capability,escopo_tipo='CONTEXTO',contexto_assistencial_id=self.open,
                concedido_por_usuario_id=self.platform_admin,motivo_concessao='Synthetic existing'))
        self.db.flush()
        for cap in CAPS[:2]:self.assert_boundary(cap,set(),actor=self.target)
        self.assert_boundary(CAPS[2],{self.open},actor=self.target)

    def test_participation_absent_closed_invalid_and_out_of_period(self):
        cases=[('DELETE FROM contexto_profissionais WHERE id=:i',{}),
               ("UPDATE contexto_profissionais SET data_inicio='2099-01-01' WHERE id=:i",{}),
               ("UPDATE contexto_profissionais SET data_inicio='2020-01-01',data_fim='2020-12-31' WHERE id=:i",{}),
               ('UPDATE contexto_profissionais SET data_fim=:day,encerrado_em=now(),encerrado_por_usuario_id=:u,motivo_encerramento=\'Synthetic\' WHERE id=:i',dict(day=self.today,u=self.platform_admin)),
               ('UPDATE contexto_profissionais SET invalidado_em=now(),invalidado_por_usuario_id=:u,motivo_invalidacao=\'Synthetic\' WHERE id=:i',dict(u=self.platform_admin))]
        for sql,params in cases:
            with self.subTest(sql=sql):
                tx=self.db.begin_nested();self.db.execute(text(sql),dict(i=self.participations[self.open],**params))
                self.assert_boundary(CAPS[0],{self.closed});self.assert_boundary(CAPS[1],set())
                self.assert_boundary(CAPS[2],{self.open})
                tx.rollback()

    def test_current_period_inclusive_boundaries(self):
        self.db.execute(text('UPDATE contexto_profissionais SET data_fim=:d WHERE id=:i'),dict(d=self.today,i=self.participations[self.open]))
        self.db.execute(text('UPDATE profissional_instituicoes SET data_fim=:d WHERE id=:i'),dict(d=self.today,i=self.links[0]))
        self.assertTrue(self.allowed());self.assertTrue(self.allowed(capability=CAPS[1]))
        self.db.execute(text('UPDATE contexto_profissionais SET data_fim=:d,data_inicio=:d WHERE id=:i'),dict(d=self.today-timedelta(days=1),i=self.participations[self.open]))
        self.assertFalse(self.allowed())

    def test_invalidated_context_denies_all(self):
        self.db.execute(text('UPDATE contextos_assistenciais SET ativo=false WHERE id=:i'),dict(i=self.open))
        self.assert_boundary(CAPS[0],{self.closed})
        self.assert_boundary(CAPS[1],set());self.assert_boundary(CAPS[2],set())

    def test_closed_or_not_started_context_denies_writing(self):
        for values in (dict(end=self.today+timedelta(days=30),start=date(2021,1,1)),
                       dict(end=None,start=self.today+timedelta(days=1))):
            with self.subTest(values=values):
                tx=self.db.begin_nested()
                self.db.execute(text('UPDATE contextos_assistenciais SET data_fim=:end,data_inicio=:start WHERE id=:i'),dict(i=self.open,**values))
                self.assert_boundary(CAPS[1],set())
                tx.rollback()

    def test_absent_revoked_wrong_capability_and_exact_context(self):
        identity=self.grant_ids[self.open,CAPS[0]]
        self.commands.revoke(self.db,dict(instituicao_id=self.institution,id=identity,motivo='Synthetic'),actor_id=self.target)
        self.assert_boundary(CAPS[0],{self.closed})
        self.assert_boundary(CAPS[1],{self.open})
        self.assertTrue(self.allowed(self.closed))  # Does not authorize the other context.
        self.assertFalse(self.allowed(self.open))

    def test_read_does_not_imply_write(self):
        self.commands.revoke(self.db,dict(instituicao_id=self.institution,id=self.grant_ids[self.open,CAPS[1]],motivo='Synthetic'),actor_id=self.target)
        self.assert_boundary(CAPS[0],{self.closed,self.open});self.assert_boundary(CAPS[1],set())

    def test_institutional_admin_grant_no_clinical_implication(self):
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE usuario_instituicao_acesso_id=:r'),dict(r=self.roots[0]))
        self.db.execute(text('DELETE FROM contexto_profissionais WHERE instituicao_id=:i'),dict(i=self.institution))
        self.db.add(Grant(instituicao_id=self.institution,usuario_instituicao_acesso_id=self.roots[0],
            capacidade=CAPS[2],escopo_tipo='INSTITUICAO',concedido_por_usuario_id=self.platform_admin,motivo_concessao='Synthetic'))
        self.db.flush()
        self.assert_boundary(CAPS[2],{self.closed,self.open})
        for cap in CAPS[:2]:self.assert_boundary(cap,set())
        self.assert_boundary(CAPS[2],set(),institution=self.institutions[1])

    def test_global_profiles_and_clinic_never_supply_grant(self):
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE usuario_instituicao_acesso_id=:r'),dict(r=self.roots[0]))
        clinic=self.db.execute(text("INSERT INTO clinicas(nome) VALUES ('Synthetic') RETURNING id")).scalar()
        self.db.execute(text('UPDATE usuarios SET clinica_id=:c WHERE id=:i'),dict(c=clinic,i=self.actor))
        self.db.execute(text('UPDATE profissionais SET clinica_id=:c WHERE id=(SELECT profissional_id FROM profissional_instituicoes WHERE id=:i)'),dict(c=clinic,i=self.links[0]))
        for profile in ('ADMIN','ADMIN_CLINICA','PROFISSIONAL','SUPORTE','GESTOR'):
            self.db.execute(text('UPDATE usuarios SET perfil=:p WHERE id=:i'),dict(p=profile,i=self.actor))
            for cap in CAPS:self.assert_boundary(cap,set())
        for cap in CAPS:self.assert_boundary(cap,set(),actor=self.platform_admin)

    def test_admin_with_explicit_clinical_eligibility_uses_same_rules(self):
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:i"),dict(i=self.actor))
        self.assert_boundary(CAPS[0],{self.closed,self.open})
        self.assert_boundary(CAPS[1],{self.open})

    def test_invalid_inputs_and_unknown_context_uniform_deny(self):
        for value in (None,False,True,0,-1,'1',2147483648,[],{}):
            with self.subTest(value=value):
                self.assertFalse(self.s.authorize_resource(self.db,actor_id=value,capability=CAPS[0],instituicao_id=self.institution,contexto_assistencial_id=self.open))
                self.assertEqual(self.db.execute(self.s.authorized_context_query(actor_id=value,capability=CAPS[0],instituicao_id=self.institution)).scalars().all(),[])
                self.assertFalse(self.s.authorize_resource(self.db,actor_id=self.actor,capability=CAPS[0],instituicao_id=value,contexto_assistencial_id=self.open))
                self.assertFalse(self.s.authorize_resource(self.db,actor_id=self.actor,capability=CAPS[0],instituicao_id=self.institution,contexto_assistencial_id=value))
        for cap in (None,'PERMISSAO_DELEGAR','UNKNOWN','assistencial_ler',[]):
            self.assertFalse(self.allowed(capability=cap))
            self.assertEqual(self.listed(capability=cap),set())
        self.assertFalse(self.allowed(2147483647))
        self.assertFalse(self.allowed(actor=2147483647))
        self.assertFalse(self.allowed(institution=2147483647))

    def test_cross_institution_no_fallback(self):
        self.assertFalse(self.allowed(self.contexts[1]))
        for cap in CAPS:self.assert_boundary(cap,set(),institution=self.institutions[1])
        self.assertFalse(self.allowed(self.open,institution=self.institutions[1]))

    def test_root_deactivation_and_reactivation_new_grant_only(self):
        Roots().deactivate(self.db,self.actor,self.institution,actor_id=self.platform_admin)
        self.db.commit()
        for cap in CAPS:self.assert_boundary(cap,set())
        Roots().activate(self.db,self.actor,self.institution,actor_id=self.platform_admin)
        self.db.commit()
        for cap in CAPS:self.assert_boundary(cap,set())
        self.command_grant(self.open,CAPS[0]);self.db.commit()
        self.assert_boundary(CAPS[0],{self.open});self.assert_boundary(CAPS[1],set())

    def test_revoked_issuer_does_not_invalidate_issued_grants(self):
        for row in self.authorities:
            self.commands.revoke_authority(self.db,dict(instituicao_id=self.institution,id=row.id,motivo='Synthetic'),actor_id=self.platform_admin)
        self.db.commit()
        self.assert_boundary(CAPS[0],{self.closed,self.open})
        self.assert_boundary(CAPS[1],{self.open});self.assert_boundary(CAPS[2],{self.open})

    def test_new_read_committed_statement_observes_concurrent_revoke(self):
        cached=self.db.get(Grant,self.grant_ids[self.open,CAPS[0]])
        statement=self.query()
        self.assertTrue(self.allowed())
        with Session(self.engine) as other,other.begin():
            self.commands.revoke(other,dict(instituicao_id=self.institution,id=cached.id,motivo='Synthetic'),actor_id=self.target)
        self.assertIsNone(cached.revogado_em)  # Deliberately stale identity map.
        self.assertFalse(self.allowed())
        self.assertNotIn(self.open,set(self.db.execute(statement).scalars()))
        with Session(self.engine) as fresh:self.assertFalse(self.allowed(db=fresh))

    def test_new_evaluation_observes_concurrent_root_deactivation(self):
        cached=self.db.get(Root,self.roots[0])
        self.assertTrue(self.allowed())
        with Session(self.engine) as other,other.begin():
            Roots().deactivate(other,self.actor,self.institution,actor_id=self.platform_admin)
        self.assertTrue(cached.ativo)
        self.assert_boundary(CAPS[0],set())
        with Session(self.engine) as fresh:self.assertFalse(self.allowed(db=fresh))

    def test_repeatable_read_snapshot_ends_before_new_request(self):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            tx=c.begin()
            with Session(c) as snapshot:
                self.assertTrue(self.allowed(db=snapshot))
                with Session(self.engine) as other,other.begin():
                    self.commands.revoke(other,dict(instituicao_id=self.institution,id=self.grant_ids[self.open,CAPS[0]],motivo='Synthetic'),actor_id=self.target)
                self.assertTrue(self.allowed(db=snapshot))
            tx.rollback()
        with Session(self.engine) as fresh:self.assertFalse(self.allowed(db=fresh))

    def test_no_flush_commit_writes_or_orm_cache_decision(self):
        user=self.db.get(Usuario,self.actor)
        with Session(self.engine) as other,other.begin():
            other.execute(text('UPDATE usuarios SET ativo=false WHERE id=:i'),dict(i=self.actor))
        user.nome='Pending unsaved edit'
        statements=[]
        def observe(conn,cursor,statement,params,ctx,many):statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',observe)
        try:
            with patch.object(self.db,'flush',side_effect=AssertionError('Unexpected flush')),patch.object(self.db,'commit',side_effect=AssertionError('Unexpected commit')):
                self.assertFalse(self.allowed())
                self.assertEqual(self.listed(),set())
            self.assertIn(user,self.db.dirty)
            self.assertEqual(user.nome,'Pending unsaved edit')
            self.assertEqual(len(statements),2)
            self.assertTrue(all(s.lstrip().upper().startswith('SELECT') for s in statements))
        finally:event.remove(self.engine,'before_cursor_execute',observe)

    def test_sql_filter_precedes_pagination_and_has_no_duplicates_or_n_plus_one(self):
        # A second valid professional/occupation link and participation cannot
        # duplicate the authorized context (EXISTS, not a multiplying join).
        from uuid import uuid4
        occupation=self.db.execute(text('INSERT INTO ocupacoes_profissionais(nome) VALUES (:n) RETURNING id'),dict(n=uuid4().hex)).scalar()
        link=self.db.execute(text("""INSERT INTO profissional_instituicoes(profissional_id,instituicao_id,ocupacao_id,data_inicio)
            SELECT profissional_id,instituicao_id,:o,'2021-01-01'
            FROM profissional_instituicoes WHERE id=:i RETURNING id"""),dict(i=self.links[0],o=occupation)).scalar()
        self.db.add(Participation(instituicao_id=self.institution,contexto_assistencial_id=self.open,
            profissional_instituicao_id=link,data_inicio=self.today,
            criado_por_usuario_id=self.platform_admin,motivo_criacao='Another eligible link'))
        self.db.flush()
        self.assertEqual(self.db.execute(self.query()).scalars().all(),sorted([self.closed,self.open]))
        statements=[]
        def observe(conn,cursor,statement,params,ctx,many):statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',observe)
        try:
            result=self.db.execute(self.query().limit(1).offset(1)).scalars().all()
            self.assertEqual(result,[max(self.closed,self.open)])
            self.assertEqual(len(statements),1)
            self.assertIn('EXISTS',statements[0])
            self.assertIn('LIMIT',statements[0])
            self.assertTrue(self.allowed())
            self.assertEqual(len(statements),2)
        finally:event.remove(self.engine,'before_cursor_execute',observe)

    def test_actor_capability_context_equivalence_matrix(self):
        actors=(self.actor,self.target,self.platform_admin,2147483647)
        contexts=(self.closed,self.open,self.contexts[1],2147483647)
        for actor in actors:
            for institution in self.institutions:
                for cap in CAPS+('PERMISSAO_DELEGAR',):
                    listed=self.listed(cap,actor,institution)
                    for context in contexts:
                        with self.subTest(actor=actor,institution=institution,cap=cap,context=context):
                            self.assertEqual(self.allowed(context,cap,actor,institution),context in listed)
