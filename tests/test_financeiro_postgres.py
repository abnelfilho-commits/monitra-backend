"""Gate A physical/service/race tests on PostgreSQL 18 disposable databases only."""
import os
import unittest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
from threading import Barrier, Event
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.dialects.postgresql import dialect
from app.models.financeiro import (ServicoEconomico, TabelaPreco, TabelaPrecoVersao, PrecoServico,
    ContratoFinanceiro, PacienteContrato, MapeamentoAgendaServico)
from app.services.financeiro.configuracao import FinanceiroConfiguracaoService, FinanceiroErro
from test_m0_baseline import config

URL=os.getenv('M0_TEST_POSTGRES_URL')
MODELS=(ServicoEconomico,TabelaPreco,TabelaPrecoVersao,PrecoServico,ContratoFinanceiro,PacienteContrato,MapeamentoAgendaServico)


@unittest.skipUnless(URL,'Requires disposable PostgreSQL 18')
class FinancialPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url=make_url(URL)
        if url.host!='127.0.0.1' or url.database!='m0_baseline':raise RuntimeError('Disposable database required')
        cls.url=url;cls.admin=create_engine(url,isolation_level='AUTOCOMMIT');cls.template='f1a_template_'+uuid4().hex
        with cls.admin.connect() as c:
            if int(c.exec_driver_sql('SHOW server_version_num').scalar())//10000!=18:raise RuntimeError('PG18 required')
            c.exec_driver_sql('CREATE DATABASE '+cls.template)
        e=create_engine(url.set(database=cls.template))
        with e.begin() as c:command.upgrade(config(c),'f1_economia_v1')
        e.dispose()

    @classmethod
    def tearDownClass(cls):
        with cls.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+cls.template)
        cls.admin.dispose()

    def setUp(self):
        self.name='f1a_'+uuid4().hex
        with self.admin.connect() as c:c.exec_driver_sql('CREATE DATABASE '+self.name+' TEMPLATE '+self.template)
        self.engine=create_engine(self.url.set(database=self.name));self.service=FinanceiroConfiguracaoService()
        with self.engine.begin() as c:
            self.actor=c.exec_driver_sql("INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) VALUES ('Synthetic','synthetic@example.invalid','existing-synthetic','ADMIN',true) RETURNING id").scalar()
            self.owner=c.exec_driver_sql("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('A','OPERADORA_SAUDE') RETURNING id").scalar()
            self.other=c.exec_driver_sql("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('B','EMPRESA') RETURNING id").scalar()
            self.occupation=c.exec_driver_sql("INSERT INTO ocupacoes_profissionais(nome) VALUES ('Synthetic') RETURNING id").scalar()
            self.patient=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Synthetic') RETURNING id").scalar()
            module=c.exec_driver_sql("INSERT INTO modulos_clinicos(nome,slug) VALUES ('Synthetic','test-f1') RETURNING id").scalar()
            pts=c.execute(text('INSERT INTO pts(paciente_id,modulo_id) VALUES (:p,:m) RETURNING id'),dict(p=self.patient,m=module)).scalar()
            obj=c.execute(text("INSERT INTO pts_objetivos(pts_id,descricao) VALUES (:p,'Synthetic') RETURNING id"),dict(p=pts)).scalar()
            activity=c.execute(text("INSERT INTO atividades_terapeuticas(nome,modulo_id) VALUES ('Synthetic',:m) RETURNING id"),dict(m=module)).scalar()
            self.agenda=c.execute(text('INSERT INTO agenda_cuidados(pts_id,objetivo_id,atividade_id,ocupacao_id,frequencia_semanal,duracao_minutos,data_inicio) VALUES (:p,:o,:a,:c,2,45,CURRENT_DATE) RETURNING id'),dict(p=pts,o=obj,a=activity,c=self.occupation)).scalar()
            self.today=c.exec_driver_sql("SELECT (clock_timestamp() AT TIME ZONE 'UTC')::date").scalar()
        self.db=Session(self.engine)
        self.s=self.service.create(self.db,ServicoEconomico,dict(codigo='S',descricao='Session',ocupacao_id=self.occupation,duracao_minutos=45))
        self.t=self.service.create(self.db,TabelaPreco,dict(proprietario_instituicao_id=self.owner,codigo='T',nome='Table'))
        self.v=self.service.create(self.db,TabelaPrecoVersao,dict(tabela_id=self.t.id,numero=1,vigente_desde=self.today))
        self.c=self.service.create(self.db,ContratoFinanceiro,dict(pagador_instituicao_id=self.owner,codigo='C',edicao=1,tabela_preco_id=self.t.id,inicio=self.today))
        self.db.commit()
        self.sid,self.tid,self.vid,self.cid=self.s.id,self.t.id,self.v.id,self.c.id
        self.db.rollback()

    def tearDown(self):
        self.db.close();self.engine.dispose()
        with self.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+self.name+' WITH (FORCE)')

    def reject_sql(self,sql,params=None):
        with self.engine.connect() as c:
            tx=c.begin()
            try:
                with self.assertRaises(DBAPIError):c.execute(text(sql),params or {})
            finally:tx.rollback()

    def price(self,value='10.00',version=None,service=None,external=None):
        return self.service.create(self.db,PrecoServico,dict(versao_id=version or self.vid,servico_id=service or self.sid,valor_base=value,codigo_externo=external))

    def publish(self):
        result=self.service.publish_version(self.db,self.vid,actor_id=self.actor);self.db.commit();return result

    def test_catalogue_types_nullability_defaults_identity_and_foreign_keys(self):
        i=inspect(self.engine)
        for model in MODELS:
            name=model.__tablename__;cols={x['name']:x for x in i.get_columns(name)}
            self.assertEqual(set(cols),set(model.__table__.c.keys()))
            self.assertFalse(cols['id']['identity']['always'])
            self.assertEqual(i.get_pk_constraint(name)['constrained_columns'],['id'])
            for col in model.__table__.c:
                self.assertEqual(cols[col.name]['nullable'],col.nullable,(name,col.name))
                self.assertEqual(str(cols[col.name]['type'].compile(dialect=dialect())),str(col.type.compile(dialect=dialect())),(name,col.name))
                if col.name!='id':
                    actual=cols[col.name]['default'];expected=str(col.server_default.arg) if col.server_default else None
                    if expected is None:self.assertIsNone(actual,(name,col.name))
                    else:self.assertEqual(actual.split('::')[0],expected,(name,col.name))
            expected={(tuple([col.name]),fk.column.table.name,tuple([fk.column.name]),fk.ondelete) for col in model.__table__.c for fk in col.foreign_keys}
            actual={(tuple(x['constrained_columns']),x['referred_table'],tuple(x['referred_columns']),x['options']['ondelete']) for x in i.get_foreign_keys(name)}
            self.assertEqual(actual,expected)
        with self.engine.connect() as c:
            self.assertTrue(c.exec_driver_sql("SELECT EXISTS(SELECT FROM pg_extension WHERE extname='btree_gist')").scalar())
            self.assertEqual(c.exec_driver_sql("SELECT count(*) FROM pg_trigger WHERE tgname='f1_no_truncate'").scalar(),7)
            self.assertEqual(c.exec_driver_sql("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'f1_guard_%%'").scalar(),6)
            self.assertEqual(c.exec_driver_sql("SELECT count(*) FROM pg_constraint WHERE conname='ex_paciente_contrato_periodo' AND contype='x'").scalar(),1)
        self.assertEqual(ScriptDirectory.from_config(config()).get_heads(),['f1_economia_v1'])

    def test_indexes_uniques_checks(self):
        i=inspect(self.engine)
        for model in MODELS:
            name=model.__tablename__
            actual={x['name'] for x in i.get_check_constraints(name)}
            expected={x.name for x in model.__table__.constraints if x.__class__.__name__=='CheckConstraint'}
            self.assertEqual(actual,expected)
            actual={x['name']:tuple(x['column_names']) for x in i.get_unique_constraints(name)}
            expected={x.name:tuple(c.name for c in x.columns) for x in model.__table__.constraints if x.__class__.__name__=='UniqueConstraint'}
            self.assertEqual(actual,expected)
            actual={x['name']:x for x in i.get_indexes(name)}
            for idx in model.__table__.indexes:
                self.assertIn(idx.name,actual)
                self.assertEqual(actual[idx.name]['unique'],idx.unique)
                self.assertEqual(actual[idx.name]['column_names'],[c.name for c in idx.columns])
        with self.engine.connect() as c:
            partial=c.exec_driver_sql("SELECT indexdef FROM pg_indexes WHERE indexname IN ('uq_preco_servico_externo','uq_tabela_preco_versao_vigencia') ORDER BY indexname").scalars().all()
            self.assertEqual(len(partial),2)
            self.assertTrue(all('WHERE' in x and 'UNIQUE' in x for x in partial))

    def test_zero_is_real_price_and_absence_is_no_row(self):
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM precos_servico').scalar(),0)
        p=self.price('0.00');self.db.commit();self.assertEqual(p.valor_base,Decimal('0.00'))
        for value in ('-1','NaN','Infinity','-Infinity'):
            self.reject_sql('UPDATE precos_servico SET valor_base=CAST(:v AS numeric) WHERE id=:id',dict(v=value,id=p.id))
        self.reject_sql('UPDATE precos_servico SET valor_base=NULL WHERE id=:id',dict(id=p.id))

    def test_service_semantics_before_after_use_and_deactivation(self):
        payload=dict(codigo='S2',descricao='Session',ocupacao_id=self.occupation,duracao_minutos=30)
        row=self.service.update_service(self.db,self.sid,payload);self.db.commit();self.assertEqual(row.duracao_minutos,30)
        self.price();self.db.commit()
        with self.assertRaises(FinanceiroErro):self.service.update_service(self.db,self.sid,dict(payload,duracao_minutos=60))
        self.reject_sql('UPDATE servicos_economicos SET duracao_minutos=60 WHERE id=:id',dict(id=self.sid))
        row=self.service.update_service(self.db,self.sid,dict(payload,ativo=False));self.db.commit();self.assertFalse(row.ativo)
        self.reject_sql('DELETE FROM servicos_economicos WHERE id=:id',dict(id=self.sid))

    def test_service_and_currency_physical_checks(self):
        for assignment in ("duracao_minutos=0","tipo_atendimento='GRUPO'","unidade='HORA'","codigo=' '"):
            self.reject_sql('UPDATE servicos_economicos SET '+assignment+' WHERE id=:id',dict(id=self.sid))
        self.reject_sql("UPDATE tabelas_preco SET moeda='USD' WHERE id=:id",dict(id=self.tid))
        with self.assertRaises(IntegrityError):self.service.create(self.db,ServicoEconomico,dict(codigo='S',descricao='Dup',ocupacao_id=self.occupation,duracao_minutos=45))

    def test_version_publication_utc_and_immutability(self):
        self.price();self.db.commit()
        self.db.execute(text("SET TIME ZONE 'Pacific/Kiritimati'"))
        result=self.publish();self.assertEqual(result.estado,'PUBLISHED');self.assertIsNotNone(result.publicado_em)
        for sql in ('UPDATE tabela_preco_versoes SET numero=2 WHERE id=:id',"UPDATE tabela_preco_versoes SET estado='DRAFT',publicado_em=NULL,publicado_por_usuario_id=NULL WHERE id=:id",'DELETE FROM tabela_preco_versoes WHERE id=:id'):
            self.reject_sql(sql,dict(id=self.vid))
        with self.assertRaises(FinanceiroErro):self.service.publish_version(self.db,self.vid,actor_id=self.actor)

    def test_retroactive_service_and_physical_publication(self):
        self.service.update_draft(self.db,TabelaPrecoVersao,self.vid,dict(tabela_id=self.tid,numero=1,vigente_desde=self.today-timedelta(days=1)));self.db.commit()
        self.db.execute(text("SET TIME ZONE 'Etc/GMT+12'"))
        with self.assertRaises(FinanceiroErro):self.service.publish_version(self.db,self.vid,actor_id=self.actor)
        self.reject_sql("UPDATE tabela_preco_versoes SET estado='PUBLISHED',publicado_em=now(),publicado_por_usuario_id=:u WHERE id=:v",dict(u=self.actor,v=self.vid))

    def test_price_crud_draft_and_both_versions_protected(self):
        p=self.price(external='EXT');self.db.commit();pid=p.id
        v2=self.service.create(self.db,TabelaPrecoVersao,dict(tabela_id=self.tid,numero=2,vigente_desde=self.today+timedelta(days=1)));self.db.commit();v2id=v2.id
        self.service.update_price(self.db,pid,dict(versao_id=v2id,servico_id=self.sid,valor_base='20'));self.db.commit()
        self.publish()
        with self.assertRaises(FinanceiroErro):self.service.update_price(self.db,pid,dict(versao_id=self.vid,servico_id=self.sid,valor_base='20'))
        self.reject_sql('UPDATE precos_servico SET versao_id=:v WHERE id=:p',dict(v=self.vid,p=pid))
        self.service.publish_version(self.db,v2id,actor_id=self.actor);self.db.commit()
        for sql in ('DELETE FROM precos_servico WHERE id=:p','UPDATE precos_servico SET valor_base=1 WHERE id=:p'):
            self.reject_sql(sql,dict(p=pid))
        self.reject_sql('INSERT INTO precos_servico(versao_id,servico_id,valor_base) VALUES (:v,:s,1)',dict(v=self.vid,s=self.sid))
        with self.assertRaises(FinanceiroErro):self.service.delete_price(self.db,pid)

    def test_external_code_unique_and_draft_delete(self):
        p=self.price(external='X');self.db.commit()
        second=self.service.create(self.db,ServicoEconomico,dict(codigo='S2',descricao='Other',ocupacao_id=self.occupation,duracao_minutos=45));self.db.commit()
        with self.assertRaises(IntegrityError):self.price(service=second.id,external='X')
        self.service.delete_price(self.db,p.id);self.db.commit()
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM precos_servico').scalar(),0)

    def test_contract_payer_period_editions_publication(self):
        with self.assertRaises(FinanceiroErro):self.service.create(self.db,ContratoFinanceiro,dict(pagador_instituicao_id=self.other,codigo='C',edicao=1,tabela_preco_id=self.tid,inicio=self.today))
        self.reject_sql('UPDATE contratos_financeiros SET pagador_instituicao_id=:p WHERE id=:i',dict(p=self.other,i=self.cid))
        self.reject_sql('UPDATE tabelas_preco SET proprietario_instituicao_id=:p WHERE id=:i',dict(p=self.other,i=self.tid))
        self.reject_sql('UPDATE contratos_financeiros SET fim=inicio-1 WHERE id=:i',dict(i=self.cid))
        self.service.create(self.db,ContratoFinanceiro,dict(pagador_instituicao_id=self.owner,codigo='C',edicao=2,tabela_preco_id=self.tid,inicio=self.today))
        self.service.publish_contract(self.db,self.cid,actor_id=self.actor);self.db.commit()
        for sql in ('UPDATE contratos_financeiros SET edicao=3 WHERE id=:i','DELETE FROM contratos_financeiros WHERE id=:i'):
            self.reject_sql(sql,dict(i=self.cid))

    def test_inclusive_patient_periods_and_distinct_contracts(self):
        data=dict(paciente_id=self.patient,contrato_id=self.cid,inicio=self.today,fim=self.today+timedelta(days=7))
        self.service.create(self.db,PacienteContrato,data);self.db.commit()
        with self.assertRaises(IntegrityError):self.service.create(self.db,PacienteContrato,dict(data,inicio=data['fim']))
        self.service.create(self.db,PacienteContrato,dict(data,inicio=data['fim']+timedelta(days=1),fim=None));self.db.commit()
        other=self.service.create(self.db,ContratoFinanceiro,dict(pagador_instituicao_id=self.owner,codigo='OTHER',edicao=1,tabela_preco_id=self.tid,inicio=self.today));self.db.commit()
        self.service.create(self.db,PacienteContrato,dict(data,contrato_id=other.id));self.db.commit()
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM paciente_instituicoes').scalar(),0)

    def test_mapping_idempotence_explicit_change_restrict(self):
        data=dict(agenda_cuidado_id=self.agenda,servico_id=self.sid)
        row=self.service.create(self.db,MapeamentoAgendaServico,data);self.db.commit();mid=row.id
        self.assertEqual(self.service.create(self.db,MapeamentoAgendaServico,data).id,mid);self.db.commit()
        second=self.service.create(self.db,ServicoEconomico,dict(codigo='S2',descricao='Other',ocupacao_id=self.occupation,duracao_minutos=45));self.db.commit()
        with self.assertRaises(FinanceiroErro):self.service.create(self.db,MapeamentoAgendaServico,dict(data,servico_id=second.id))
        self.service.change_mapping(self.db,mid,servico_id=second.id);self.db.commit()
        self.reject_sql('DELETE FROM agenda_cuidados WHERE id=:i',dict(i=self.agenda))

    def test_outer_rollback_and_no_clinical_writes(self):
        tables=('pacientes','usuarios','pts','pts_objetivos','agenda_cuidados','sessoes_assistenciais','paciente_instituicoes','profissional_instituicoes','usuario_instituicao_acessos')
        def snapshot():
            with self.engine.connect() as c:return {t:c.exec_driver_sql('SELECT row_to_json(t)::text FROM '+t+' t ORDER BY 1').scalars().all() for t in tables}
        before=snapshot();self.price('0')
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM precos_servico').scalar(),0)
        self.db.rollback()
        self.price();self.service.publish_version(self.db,self.vid,actor_id=self.actor);self.db.rollback()
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM precos_servico').scalar(),0)
            self.assertEqual(c.execute(text('SELECT estado FROM tabela_preco_versoes WHERE id=:i'),dict(i=self.vid)).scalar(),'DRAFT')
        self.assertEqual(before,snapshot())

    def test_truncate_cannot_bypass_guards(self):
        for model in MODELS:self.reject_sql('TRUNCATE '+model.__tablename__+' CASCADE')

    def test_downgrade_blocks_any_economic_data(self):
        with self.engine.connect() as c:
            tx=c.begin()
            with self.assertRaisesRegex(RuntimeError,'F1_DOWNGRADE_BLOCKED_DATA'):command.downgrade(config(c),'g2c1_autorizacao_v1')
            tx.rollback()
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'f1_economia_v1')

    def test_empty_downgrade_and_incremental_upgrade(self):
        e=create_engine(self.url.set(database=self.template))
        try:
            with e.begin() as c:command.downgrade(config(c),'g2c1_autorizacao_v1')
            with e.begin() as c:
                self.assertIsNone(c.exec_driver_sql("SELECT to_regclass('public.servicos_economicos')").scalar())
                command.upgrade(config(c),'f1_economia_v1')
                self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM servicos_economicos').scalar(),0)
        finally:e.dispose()

    def race(self, callback):
        barrier=Barrier(2)
        def worker(n):
            with Session(self.engine) as db:
                barrier.wait(timeout=10)
                try:
                    result=callback(db,n);db.commit();return ('ok',result)
                except (IntegrityError,FinanceiroErro) as exc:
                    db.rollback();return ('conflict',type(exc).__name__)
        with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(worker,[0,1]))

    def test_concurrent_mapping_identical(self):
        results=self.race(lambda db,n:self.service.create(db,MapeamentoAgendaServico,dict(agenda_cuidado_id=self.agenda,servico_id=self.sid)).id)
        self.assertEqual([x[0] for x in results],['ok','ok']);self.assertEqual(results[0][1],results[1][1])

    def test_concurrent_mapping_conflicting(self):
        other=self.service.create(self.db,ServicoEconomico,dict(codigo='S2',descricao='Other',ocupacao_id=self.occupation,duracao_minutos=45));self.db.commit();sid=other.id
        results=self.race(lambda db,n:self.service.create(db,MapeamentoAgendaServico,dict(agenda_cuidado_id=self.agenda,servico_id=[self.sid,sid][n])).id)
        self.assertEqual(sorted(x[0] for x in results),['conflict','ok'])

    def test_concurrent_patient_overlap(self):
        results=self.race(lambda db,n:self.service.create(db,PacienteContrato,dict(paciente_id=self.patient,contrato_id=self.cid,inicio=self.today)).id)
        self.assertEqual(sorted(x[0] for x in results),['conflict','ok'])

    def test_concurrent_publications_same_effective_date(self):
        v2=self.service.create(self.db,TabelaPrecoVersao,dict(tabela_id=self.tid,numero=2,vigente_desde=self.today));self.db.commit();vid=v2.id
        results=self.race(lambda db,n:self.service.publish_version(db,[self.vid,vid][n],actor_id=self.actor).id)
        self.assertEqual(sorted(x[0] for x in results),['conflict','ok'])

    def test_price_and_publication_serialize_both_orders(self):
        for publish_first in (False,True):
            version=self.service.create(self.db,TabelaPrecoVersao,dict(tabela_id=self.tid,numero=10+int(publish_first),vigente_desde=self.today+timedelta(days=10+int(publish_first))));self.db.commit();vid=version.id
            with Session(self.engine) as first:
                if publish_first:self.service.publish_version(first,vid,actor_id=self.actor)
                else:self.service.create(first,PrecoServico,dict(versao_id=vid,servico_id=self.sid,valor_base='1'))
                started=Event()
                def second():
                    with Session(self.engine) as db:
                        started.set()
                        try:
                            if publish_first:self.service.create(db,PrecoServico,dict(versao_id=vid,servico_id=self.sid,valor_base='2'))
                            else:self.service.publish_version(db,vid,actor_id=self.actor)
                            db.commit();return 'ok'
                        except FinanceiroErro:
                            db.rollback();return 'blocked'
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(second);self.assertTrue(started.wait(5))
                    first.commit();self.assertEqual(future.result(timeout=10),'blocked' if publish_first else 'ok')
            with self.engine.connect() as c:
                self.assertEqual(c.execute(text('SELECT count(*) FROM precos_servico WHERE versao_id=:v'),dict(v=vid)).scalar(),0 if publish_first else 1)

    def test_failure_rolls_back_complete_caller_transaction(self):
        try:
            self.price('0')
            self.service.publish_version(self.db,self.vid,actor_id=self.actor)
            self.service.create(self.db,PacienteContrato,dict(paciente_id=self.patient,contrato_id=self.cid,inicio=self.today))
            self.service.create(self.db,PacienteContrato,dict(paciente_id=self.patient,contrato_id=self.cid,inicio=self.today))
            self.fail('Expected overlap failure')
        except IntegrityError:
            self.db.rollback()
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM precos_servico').scalar(),0)
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM paciente_contratos').scalar(),0)
            self.assertEqual(c.execute(text('SELECT estado FROM tabela_preco_versoes WHERE id=:v'),dict(v=self.vid)).scalar(),'DRAFT')

    def test_physical_price_publication_lock_without_service(self):
        with self.engine.connect() as first:
            transaction=first.begin()
            first.execute(text("UPDATE tabela_preco_versoes SET estado='PUBLISHED', publicado_por_usuario_id=:a WHERE id=:v"),dict(a=self.actor,v=self.vid))
            started=Event()
            def insert_price():
                with self.engine.connect() as second:
                    tx=second.begin();started.set()
                    try:
                        second.execute(text('INSERT INTO precos_servico(versao_id,servico_id,valor_base) VALUES (:v,:s,1)'),dict(v=self.vid,s=self.sid))
                        tx.commit();return 'unexpected'
                    except IntegrityError as error:
                        tx.rollback();return error.orig.diag.constraint_name
            with ThreadPoolExecutor(max_workers=1) as pool:
                result=pool.submit(insert_price);self.assertTrue(started.wait(5))
                transaction.commit()
                self.assertEqual(result.result(timeout=10),'f1_price_immutable')
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM precos_servico').scalar(),0)
