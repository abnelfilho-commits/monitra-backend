"""G2.B.1 domain, migration and concurrency on isolated real PostgreSQL 18."""
import os
import unittest
from datetime import date
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
from alembic import command
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from app.models.institucional import Instituicao, PacienteInstituicao as PI, ProfissionalInstituicao as PRI, PacienteProfissional as PP
from app.models.institucional_operacao import InstitucionalOperacao as Audit
from app.models import Pessoa, Usuario, Paciente, Profissional
from app.models.atividade_terapeutica import OcupacaoProfissional
from app.schemas.institucional import PacienteProfissionalCreate, PacienteInstituicaoCreate
from app.services.institucional import InstitucionalService, InstitucionalErro
from test_m0_baseline import config

URL = os.getenv('G2B1_TEST_POSTGRES_URL')
START = date(2026, 1, 1)
END = date(2026, 2, 1)
LATER = date(2026, 3, 1)
HEAD = 'g2b1_institucional_v1'


class InstitutionalContractTests(unittest.TestCase):
    def test_context_required_and_no_extra_keys_or_invalidated_create(self):
        with self.assertRaises(ValidationError):
            PacienteProfissionalCreate(paciente_id=1, profissional_instituicao_id=1, data_inicio=START)
        for extra in ({'clinica_id': 1}, {'ativo': False}):
            with self.assertRaises(ValidationError):
                PacienteInstituicaoCreate(paciente_id=1, instituicao_id=1, tipo_vinculo='OUTRO', data_inicio=START, **extra)

    def test_four_states_inclusive(self):
        row = SimpleNamespace(ativo=True, data_inicio=START, data_fim=END)
        s = InstitucionalService()
        self.assertEqual(s.state(row, date(2025, 12, 31)), 'FUTURO')
        for d in (START, END): self.assertEqual(s.state(row, d), 'VIGENTE')
        self.assertEqual(s.state(row, LATER), 'ENCERRADO')
        row.ativo = False
        self.assertEqual(s.state(row, START), 'INVALIDADO')


@unittest.skipUnless(URL, 'Requires explicitly disposable PostgreSQL 18')
class InstitutionalLinksPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host != '127.0.0.1' or url.database != 'm0_baseline':
            raise RuntimeError('Dedicated disposable local database required')
        cls.admin = create_engine(url, isolation_level='AUTOCOMMIT')
        cls.name = 'g2b1_' + uuid4().hex
        with cls.admin.connect() as c:
            if int(c.execute(text('SHOW server_version_num')).scalar()) // 10000 != 18:
                raise RuntimeError('PG18 required')
            c.execute(text('CREATE DATABASE ' + cls.name))
        cls.engine = create_engine(url.set(database=cls.name), connect_args={'options': '-c lock_timeout=5000 -c statement_timeout=15000'})
        with cls.engine.begin() as c: command.upgrade(config(c), HEAD)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as c: c.execute(text('DROP DATABASE ' + cls.name))
        cls.admin.dispose()

    def setUp(self):
        self.s = InstitucionalService()
        with Session(self.engine) as db, db.begin():
            person = Pessoa(nome_completo='Synthetic', cpf='52998224725')
            db.add(person); db.flush()
            p = Paciente(nome='Synthetic', pessoa_id=person.id, ativo=False)
            p2 = Paciente(nome='Other synthetic', ativo=False)
            pr = Profissional(nome='Synthetic', pessoa_id=person.id, ativo=False)
            actor = Usuario(nome='Synthetic admin', email='admin@example.invalid', senha_hash='synthetic-existing', perfil='ADMIN', ativo=True)
            a = Instituicao(razao_social='X', tipo_instituicao='OUTRO')
            b = Instituicao(razao_social='Y', tipo_instituicao='OUTRO')
            oc = OcupacaoProfissional(nome='One', ativo=True)
            oc2 = OcupacaoProfissional(nome='Two', ativo=True)
            db.add_all([p, p2, pr, actor, a, b, oc, oc2]); db.flush()
            self.p, self.p2, self.pr, self.actor, self.a, self.b, self.oc, self.oc2 = [v.id for v in (p,p2,pr,actor,a,b,oc,oc2)]
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.rollback(); self.db.close()
        with self.engine.begin() as c:
            c.execute(text('TRUNCATE institucional_operacoes, paciente_profissionais, paciente_instituicoes, profissional_instituicoes, instituicoes, pacientes, profissionais, usuarios, pessoas, ocupacoes_profissionais CASCADE'))

    def create(self, model, db=None, **kw):
        data = dict(data_inicio=START)
        if model is PI: data.update(paciente_id=self.p, instituicao_id=self.a, tipo_vinculo='ASSISTENCIAL')
        if model is PRI: data.update(profissional_id=self.pr, instituicao_id=self.a, ocupacao_id=self.oc)
        data.update(kw)
        return self.s.create(db or self.db, model, data, actor_id=self.actor, motivo='Synthetic operation')

    def close(self, model, identity, end=END, db=None):
        return self.s.close(db or self.db, model, identity, end, actor_id=self.actor, motivo='Explicit close')

    def invalidate(self, model, identity, db=None):
        return self.s.invalidate(db or self.db, model, identity, actor_id=self.actor, motivo='Administrative invalidation')

    def team(self, pi=None, pri=None, **kw):
        pi = pi or self.create(PI)
        pri = pri or self.create(PRI)
        return self.create(PP, paciente_id=self.p, paciente_instituicao_id=pi.id, profissional_instituicao_id=pri.id, **kw)

    def legacy(self, pri, **kw):
        args = dict(paciente_id=self.p, profissional_instituicao_id=pri.id, data_inicio=START, ativo=True)
        args.update(kw)
        row = PP(**args); self.db.add(row); self.db.flush()
        return row

    def test_person_two_roles_multiple_institutions_and_occupations(self):
        a = self.create(PI); b = self.create(PI, instituicao_id=self.b)
        x = self.create(PRI); y = self.create(PRI, instituicao_id=self.b)
        z = self.create(PRI, ocupacao_id=self.oc2)
        self.assertEqual(self.db.get(Paciente,self.p).pessoa_id, self.db.get(Profissional,self.pr).pessoa_id)
        self.assertEqual(len({a.id,b.id}),2)
        self.assertEqual(len({x.id,y.id,z.id}),3)
        self.assertIsNone(self.db.get(Profissional,self.pr).ocupacao_id)
        self.assertIsNone(self.db.get(Profissional,self.pr).clinica_id)
        self.assertIsNone(self.db.get(Paciente,self.p).clinica_id)
        self.assertEqual(self.db.query(Usuario).count(),1)
        self.assertIsNone(self.db.get(Usuario,self.actor).pessoa_id)
        for table in ('profissional_modulos','paciente_modulos','responsavel_paciente','responsaveis','vinculos'):
            self.assertEqual(self.db.execute(text('SELECT count(*) FROM '+table)).scalar(),0)

    def test_idempotent_create_and_semantic_conflict_without_overwrite(self):
        first = self.create(PI, identificador_externo='institution-reference')
        second = self.create(PI, identificador_externo='institution-reference')
        self.assertEqual(first.id,second.id)
        self.assertEqual(self.db.query(Audit).count(),1)
        with self.assertRaisesRegex(InstitucionalErro,'PERIOD_CONFLICT'):
            self.create(PI, identificador_externo='different')
        self.assertEqual(self.db.query(PI).count(),1)
        self.assertEqual(first.identificador_externo,'institution-reference')

    def test_closed_return_and_inclusive_boundary_for_both_roles(self):
        for model in (PI,PRI):
            first = self.create(model)
            self.close(model,first.id)
            self.assertTrue(first.ativo)
            self.assertEqual(self.close(model,first.id).id,first.id)
            with self.assertRaisesRegex(InstitucionalErro,'PERIOD_CONFLICT'):
                self.create(model,data_inicio=END)
            second = self.create(model,data_inicio=date(2026,2,2))
            self.assertNotEqual(first.id,second.id)
            with self.assertRaisesRegex(InstitucionalErro,'CLOSE_CONFLICT'):
                self.close(model,first.id,LATER)

    def test_team_requires_patient_and_institution_consistency(self):
        pi = self.create(PI)
        pri = self.create(PRI, instituicao_id=self.b)
        with self.assertRaisesRegex(InstitucionalErro,'INSTITUTION_MISMATCH'): self.team(pi,pri)
        other = self.create(PI,paciente_id=self.p2,instituicao_id=self.b)
        with self.assertRaisesRegex(InstitucionalErro,'PATIENT_MISMATCH'): self.team(other,pri)
        self.assertEqual(self.db.query(PP).count(),0)

    def test_team_period_intersection_open_and_closed(self):
        pi = self.create(PI, data_fim=END)
        pri = self.create(PRI, data_fim=LATER)
        for bounds in ({}, {'data_inicio':date(2025,12,31),'data_fim':END}, {'data_fim':LATER}):
            with self.assertRaisesRegex(InstitucionalErro,'PARENT_PERIOD_OR_STATE_CONFLICT'):
                self.team(pi,pri,**bounds)
        child = self.team(pi,pri,data_fim=END)
        self.assertEqual(child.paciente_instituicao_id,pi.id)
        # Same institution but another explicit patient membership is not idempotent.
        second = self.create(PI,tipo_vinculo='OUTRO',data_fim=END)
        with self.assertRaisesRegex(InstitucionalErro,'PERIOD_CONFLICT'): self.team(second,pri,data_fim=END)

    def test_professional_period_and_invalidated_parents(self):
        pi = self.create(PI)
        pri = self.create(PRI,data_fim=END)
        with self.assertRaisesRegex(InstitucionalErro,'PARENT_PERIOD_OR_STATE_CONFLICT'):
            self.team(pi,pri,data_fim=LATER)
        self.invalidate(PRI,pri.id)
        with self.assertRaisesRegex(InstitucionalErro,'PARENT_PERIOD_OR_STATE_CONFLICT'):
            self.team(pi,pri,data_fim=END)

    def test_parent_close_and_invalidate_reject_atomically(self):
        pi = self.create(PI); pri = self.create(PRI); child = self.team(pi,pri)
        before = self.db.query(Audit).count()
        for model,row in ((PI,pi),(PRI,pri)):
            for action in (self.close,self.invalidate):
                with self.assertRaisesRegex(InstitucionalErro,'DEPENDENT_LINK_CONFLICT'): action(model,row.id)
                self.assertIsNone(row.data_fim); self.assertTrue(row.ativo)
        self.assertEqual(self.db.query(Audit).count(),before)
        self.assertIsNone(child.data_fim)
        self.close(PP,child.id)
        self.close(PI,pi.id); self.close(PRI,pri.id)
        self.assertTrue(pi.ativo and pri.ativo and child.ativo)

    def test_invalidation_reason_idempotence_and_child_first(self):
        pi = self.create(PI); pri = self.create(PRI); child = self.team(pi,pri)
        with self.assertRaisesRegex(InstitucionalErro,'REASON_REQUIRED'):
            self.s.invalidate(self.db,PP,child.id,actor_id=self.actor,motivo=' ')
        self.invalidate(PP,child.id)
        n = self.db.query(Audit).count()
        self.invalidate(PP,child.id)
        self.assertEqual(self.db.query(Audit).count(),n)
        self.invalidate(PI,pi.id); self.invalidate(PRI,pri.id)
        self.assertFalse(pi.ativo or pri.ativo or child.ativo)
        with self.assertRaisesRegex(InstitucionalErro,'LINK_INVALIDATED'): self.close(PP,child.id)

    def test_d2_blocks_single_candidate_and_professional_explicit_fk(self):
        pi=self.create(PI); pri=self.create(PRI); child=self.legacy(pri)
        for action in (self.close,self.invalidate):
            with self.assertRaisesRegex(InstitucionalErro,'LEGACY_CONTEXT_UNRESOLVED'): action(PI,pi.id)
            with self.assertRaisesRegex(InstitucionalErro,'DEPENDENT_LINK_CONFLICT'): action(PRI,pri.id)
        self.assertIsNone(pi.data_fim); self.assertTrue(pi.ativo)
        self.assertIsNone(child.paciente_instituicao_id)
        self.assertEqual(self.db.query(Audit).count(),2)

    def test_d2_negative_cases_and_inclusive_affected_period(self):
        pi=self.create(PI); pri=self.create(PRI)
        other=self.create(PRI,instituicao_id=self.b)
        cases = [
            (pri, {'paciente_id':self.p2}),
            (other, {}),
            (pri, {'ativo':False}),
            (pri, {'data_fim':END}),  # Closing on END does not remove that day.
        ]
        for professional,attrs in cases:
            with self.subTest(attrs=attrs,professional=professional.id):
                save=self.db.begin_nested()
                try:
                    child=self.legacy(professional,**attrs)
                    self.close(PI,pi.id)
                    self.assertIsNone(child.paciente_instituicao_id)
                finally: save.rollback()
        # INVALIDATE: disjoint dates do not imply potential dependency.
        bounded=self.create(PI,tipo_vinculo='OUTRO',data_fim=END)
        for dates in ({'data_inicio':date(2026,2,2)}, {'data_inicio':date(2025,1,1),'data_fim':date(2025,12,31)}):
            save=self.db.begin_nested()
            try:
                self.legacy(pri,**dates); self.invalidate(PI,bounded.id)
            finally: save.rollback()
        save=self.db.begin_nested()
        try:
            self.legacy(pri,data_inicio=END,data_fim=END)
            with self.assertRaisesRegex(InstitucionalErro,'LEGACY_CONTEXT_UNRESOLVED'): self.invalidate(PI,bounded.id)
        finally: save.rollback()

    def test_canonical_dependency_uses_only_explicit_patient_fk(self):
        pi=self.create(PI)
        other=self.create(PI,tipo_vinculo='OUTRO')
        pri=self.create(PRI); child=self.team(other,pri)
        self.close(PI,pi.id)
        self.assertEqual(child.paciente_instituicao_id,other.id)
        self.assertIsNone(child.data_fim)

    def test_get_list_and_admin_without_human_membership(self):
        row=self.create(PI)
        self.assertEqual(self.s.get(self.db,PI,row.id,actor_id=self.actor).id,row.id)
        self.assertEqual([r.id for r in self.s.list(self.db,PI,instituicao_id=self.a,actor_id=self.actor)],[row.id])
        self.assertEqual(self.s.list(self.db,PI,instituicao_id=self.b,actor_id=self.actor),[])
        child=self.team(row)
        self.assertEqual([r.id for r in self.s.list(self.db,PP,instituicao_id=self.a,actor_id=self.actor)],[child.id])
        with self.assertRaisesRegex(InstitucionalErro,'EXPLICIT_INSTITUTION_REQUIRED'):
            self.s.list(self.db,PI,instituicao_id=None,actor_id=self.actor)
        with self.assertRaisesRegex(InstitucionalErro,'ADMIN_REQUIRED'):
            self.s.get(self.db,PI,row.id,actor_id=-1)

    def test_savepoint_rolls_back_link_and_audit_failure(self):
        original=self.s._audit
        def fail(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('synthetic audit failure')
        with patch.object(self.s,'_audit',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'synthetic'): self.create(PI)
        self.assertEqual(self.db.query(PI).count(),0)
        self.assertEqual(self.db.query(Audit).count(),0)
        row=self.create(PI)
        with patch.object(self.s,'_audit',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'synthetic'): self.close(PI,row.id)
        self.assertIsNone(self.s.get(self.db,PI,row.id,actor_id=self.actor).data_fim)
        self.assertEqual(self.db.query(Audit).count(),1)
        self.db.rollback()
        with Session(self.engine) as observer:
            self.assertEqual(observer.query(PI).count(),0)
            self.assertEqual(observer.query(Audit).count(),0)

    def test_service_does_not_commit_and_preserves_clinical_denial(self):
        from app.core.acl import assert_clinica_access
        from fastapi import HTTPException
        self.team()
        with Session(self.engine) as observer: self.assertEqual(observer.query(PI).count(),0)
        with self.assertRaises(HTTPException):
            assert_clinica_access(SimpleNamespace(perfil='PROFISSIONAL',clinica_id=1),2)

    def race(self, functions):
        self.db.commit()
        barrier=Barrier(len(functions))
        def run(fn):
            try:
                with Session(self.engine) as db, db.begin():
                    barrier.wait(timeout=5)
                    result=fn(db)
                    return ('ok',result.id)
            except InstitucionalErro as exc: return (exc.code,None)
        with ThreadPoolExecutor(max_workers=len(functions)) as pool: return list(pool.map(run,functions))

    def test_real_concurrent_identical_create(self):
        results=self.race([lambda db:self.create(PI,db=db)]*2)
        self.assertEqual(results[0],results[1]); self.assertEqual(results[0][0],'ok')
        self.assertEqual(self.db.query(PI).count(),1); self.assertEqual(self.db.query(Audit).count(),1)

    def test_real_concurrent_conflicting_create(self):
        results=self.race([lambda db:self.create(PI,db=db),lambda db:self.create(PI,db=db,data_fim=END)])
        self.assertCountEqual([r[0] for r in results],['ok','PERIOD_CONFLICT'])
        self.assertEqual(self.db.query(PI).count(),1)

    def test_real_concurrent_close_identical_and_conflicting(self):
        row=self.create(PI); identity=row.id
        results=self.race([lambda db:self.close(PI,identity,db=db)]*2)
        self.assertEqual(results[0],results[1])
        self.assertEqual(self.db.query(Audit).filter_by(operacao='CLOSE_LINK').count(),1)
        new=self.create(PRI); identity=new.id
        results=self.race([lambda db:self.close(PRI,identity,END,db=db),lambda db:self.close(PRI,identity,LATER,db=db)])
        self.assertCountEqual([r[0] for r in results],['ok','CLOSE_CONFLICT'])

    def test_real_concurrent_child_create_vs_parent_close(self):
        pi=self.create(PI); pri=self.create(PRI); pi_id,pri_id=pi.id,pri.id
        results=self.race([
            lambda db:self.create(PP,db=db,paciente_id=self.p,paciente_instituicao_id=pi_id,profissional_instituicao_id=pri_id),
            lambda db:self.close(PI,pi_id,db=db)])
        self.assertEqual(sum(r[0]=='ok' for r in results),1)
        self.assertTrue(any(r[0] in ('DEPENDENT_LINK_CONFLICT','PARENT_PERIOD_OR_STATE_CONFLICT') for r in results))

    def test_real_concurrent_child_create_vs_parent_invalidate(self):
        pi=self.create(PI); pri=self.create(PRI); pi_id,pri_id=pi.id,pri.id
        results=self.race([
            lambda db:self.create(PP,db=db,paciente_id=self.p,paciente_instituicao_id=pi_id,profissional_instituicao_id=pri_id),
            lambda db:self.invalidate(PRI,pri_id,db=db)])
        self.assertEqual(sum(r[0]=='ok' for r in results),1)
        self.assertTrue(any(r[0] in ('DEPENDENT_LINK_CONFLICT','PARENT_PERIOD_OR_STATE_CONFLICT') for r in results))

    def test_physical_fk_and_exclusion_still_protect_direct_writes(self):
        pi=self.create(PI)
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():
                self.db.add(PI(paciente_id=self.p,instituicao_id=self.a,tipo_vinculo='ASSISTENCIAL',data_inicio=END));self.db.flush()
        pri=self.create(PRI)
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():
                self.db.add(PP(paciente_id=self.p,profissional_instituicao_id=pri.id,paciente_instituicao_id=-1,data_inicio=START));self.db.flush()
        self.assertTrue(pi.ativo)

    def test_requires_read_committed(self):
        self.db.rollback()
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn, conn.begin():
            with Session(conn) as db:
                with self.assertRaisesRegex(InstitucionalErro,'READ_COMMITTED_REQUIRED'): self.create(PI,db=db)


@unittest.skipUnless(URL, 'Requires explicitly disposable PostgreSQL 18')
class InstitutionalMigrationTests(unittest.TestCase):
    def setUp(self):
        url=make_url(URL)
        if url.host!='127.0.0.1' or url.database!='m0_baseline': raise RuntimeError('Disposable local database only')
        self.admin=create_engine(url,isolation_level='AUTOCOMMIT')
        self.name='g2b1_migration_'+uuid4().hex
        with self.admin.connect() as c:
            self.assertEqual(int(c.execute(text('SHOW server_version_num')).scalar())//10000,18)
            c.execute(text('CREATE DATABASE '+self.name))
        self.engine=create_engine(url.set(database=self.name))
        with self.engine.begin() as c:
            command.upgrade(config(c),'g2a3_identidade_v1')
            c.execute(text("INSERT INTO pacientes(id,nome) VALUES (1,'Synthetic')"))
            c.execute(text("INSERT INTO profissionais(id,nome) VALUES (1,'Synthetic')"))
            c.execute(text("INSERT INTO ocupacoes_profissionais(id,nome) VALUES (1,'Synthetic')"))
            c.execute(text("INSERT INTO instituicoes(id,razao_social,tipo_instituicao) VALUES (1,'Synthetic','OUTRO')"))
            c.execute(text("INSERT INTO paciente_instituicoes(id,paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (1,1,1,'OUTRO','2026-01-01')"))
            c.execute(text("INSERT INTO profissional_instituicoes(id,profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (1,1,1,1,'2026-01-01')"))
            c.execute(text("INSERT INTO paciente_profissionais(id,paciente_id,profissional_instituicao_id,data_inicio) VALUES (1,1,1,'2026-01-01')"))

    def tearDown(self):
        self.engine.dispose()
        with self.admin.connect() as c:c.execute(text('DROP DATABASE '+self.name))
        self.admin.dispose()

    def upgrade(self):
        with self.engine.begin() as c:command.upgrade(config(c),HEAD)

    def test_incremental_exact_catalogue_and_no_backfill(self):
        with self.engine.connect() as c:
            old=c.execute(text('SELECT to_jsonb(p) FROM paciente_profissionais p')).scalar()
            excluded=c.execute(text("SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE contype='x' ORDER BY conname")).all()
            views=c.execute(text("SELECT viewname,definition FROM pg_views WHERE schemaname='public' ORDER BY viewname")).all()
        self.upgrade()
        i=inspect(self.engine)
        col=next(x for x in i.get_columns('paciente_profissionais') if x['name']=='paciente_instituicao_id')
        self.assertTrue(col['nullable']);self.assertIsNone(col['default']);self.assertEqual(str(col['type']),'INTEGER')
        fk=next(x for x in i.get_foreign_keys('paciente_profissionais') if x['constrained_columns']==['paciente_instituicao_id'])
        self.assertEqual(fk['referred_table'],'paciente_instituicoes');self.assertEqual(fk['referred_columns'],['id']);self.assertEqual(fk['options']['ondelete'],'RESTRICT')
        idx=next(x for x in i.get_indexes('paciente_profissionais') if x['column_names']==['paciente_instituicao_id'])
        self.assertFalse(idx['unique'])
        self.assertEqual({c['name'] for c in i.get_columns('institucional_operacoes')},set(Audit.__table__.columns.keys()))
        self.assertEqual(len(i.get_foreign_keys('institucional_operacoes')),5)
        self.assertEqual({x['name'] for x in i.get_check_constraints('institucional_operacoes')},{x.name for x in Audit.__table__.constraints if x.__class__.__name__=='CheckConstraint'})
        for table,model in (('institucional_operacoes',Audit),):
            for actual in i.get_columns(table):
                expected=model.__table__.c[actual['name']]
                self.assertEqual(actual['nullable'],expected.nullable)
        with self.engine.connect() as c:
            new=c.execute(text('SELECT to_jsonb(p) FROM paciente_profissionais p')).scalar()
            self.assertIsNone(new.pop('paciente_instituicao_id'));self.assertEqual(old,new)
            self.assertEqual(c.execute(text("SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE contype='x' ORDER BY conname")).all(),excluded)
            self.assertEqual(c.execute(text("SELECT viewname,definition FROM pg_views WHERE schemaname='public' ORDER BY viewname")).all(),views)
            self.assertEqual(c.execute(text('SELECT count(*) FROM pessoas')).scalar(),0)
            self.assertEqual(c.execute(text('SELECT count(*) FROM institucional_operacoes')).scalar(),0)
            self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),HEAD)

    def test_safe_downgrade_preserves_legacy_and_reupgrade(self):
        self.upgrade()
        with self.engine.begin() as c:command.downgrade(config(c),'g2a3_identidade_v1')
        self.assertNotIn('paciente_instituicao_id',[x['name'] for x in inspect(self.engine).get_columns('paciente_profissionais')])
        with self.engine.connect() as c:self.assertEqual(c.execute(text('SELECT count(*) FROM paciente_profissionais')).scalar(),1)
        self.upgrade()

    def test_downgrade_rejects_explicit_context_even_without_audit(self):
        self.upgrade()
        with self.engine.begin() as c:c.execute(text('UPDATE paciente_profissionais SET paciente_instituicao_id=1'))
        with self.assertRaisesRegex(RuntimeError,'DOWNGRADE_BLOCKED'):
            with self.engine.begin() as c:command.downgrade(config(c),'g2a3_identidade_v1')
        with self.engine.connect() as c:self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),HEAD)

    def test_downgrade_rejects_provenance_without_patient_context(self):
        self.upgrade()
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO usuarios(id,nome,email,senha_hash) VALUES (1,'Synthetic','s@example.invalid','test')"))
            c.execute(text("INSERT INTO institucional_operacoes(ator_usuario_id,instituicao_id,operacao,tipo_alvo,paciente_instituicao_id,motivo,resultado,estado_final) VALUES (1,1,'CREATE_LINK','PACIENTE_INSTITUICAO',1,'Synthetic','CREATED','{}')"))
        with self.assertRaisesRegex(RuntimeError,'DOWNGRADE_BLOCKED'):
            with self.engine.begin() as c:command.downgrade(config(c),'g2a3_identidade_v1')

    def test_preflight_stops_on_partial_structure(self):
        with self.engine.begin() as c:c.execute(text('ALTER TABLE paciente_profissionais ADD COLUMN paciente_instituicao_id integer'))
        with self.assertRaisesRegex(RuntimeError,'STOP_PREEXISTING_OBJECT'):self.upgrade()
        self.assertNotIn('institucional_operacoes',inspect(self.engine).get_table_names())
        with self.engine.connect() as c:self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'g2a3_identidade_v1')

    def test_migration_rollback_leaves_no_partial_structure(self):
        with self.assertRaisesRegex(RuntimeError,'synthetic'):
            with self.engine.begin() as c:
                command.upgrade(config(c),HEAD)
                raise RuntimeError('synthetic precommit abort')
        self.assertNotIn('institucional_operacoes',inspect(self.engine).get_table_names())
        self.assertNotIn('paciente_instituicao_id',[x['name'] for x in inspect(self.engine).get_columns('paciente_profissionais')])
