"""Authorized contextual CBI HTTP, on real disposable PostgreSQL."""
import json
import os
import unittest
from urllib.parse import urlsplit, parse_qsl
from unittest.mock import patch
from sqlalchemy import text
import test_checkin_bem_estar as foundation
from app.services.cbi_contract import FIELDS, DOMAINS


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class CBITests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(foundation.CheckinTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.CheckinTests.tearDownClass.__func__)
    command_grant = foundation.CheckinTests.command_grant
    setUp = foundation.CheckinTests.setUp
    tearDown = foundation.CheckinTests.tearDown
    path = foundation.CheckinTests.path

    def post(self, changes=None, **scope):
        u = urlsplit(self.path(**scope))
        payload = dict(respostas={name:'1' for name,_,_ in FIELDS})
        payload.update(changes or {})
        return self.client.request('POST', u.path + '/cbi', params=dict(parse_qsl(u.query)),
                                   body=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})

    def test_persistence_framework_authorship_and_repeated_assessment(self):
        before=self.client.get(self.path()).json()
        r=self.post()
        self.assertEqual(r.status_code,201,r.text)
        d=r.json()
        self.assertNotIn('score',d['resultado'])
        self.assertEqual([x['score'] for x in d['resultado']['dominios']],[25,32.14,25])
        self.assertEqual(self.db.execute(text('SELECT score FROM avaliacoes_clinicas WHERE id=:i'),dict(i=d['id'])).scalar(),None)
        self.assertEqual(d['registrador_usuario_id'],self.actor)
        self.assertEqual(self.client.get(self.path()).json()['cbi']['itens'],[d])
        self.assertEqual(self.db.execute(text("SELECT count(*) FROM respostas_registro WHERE registro_id=:r"),dict(r=d['registro_id'])).scalar(),19)
        self.assertEqual(self.db.execute(text("SELECT contexto_assistencial_id FROM registros_longitudinais WHERE id=:r"),dict(r=d['registro_id'])).scalar(),self.open)
        from app.services.clinical_engine.assessment_builder import AssessmentBuilder
        with self.assertRaisesRegex(ValueError, 'não encontrado'):
            AssessmentBuilder.from_registro(self.db,d['registro_id'],'CBI')
        self.assertEqual(self.post().status_code,201)
        after=self.client.get(self.path()).json()
        self.assertEqual(len(after['cbi']['itens']),2)
        for key in ('clinical_reading','bem_estar','diagnosticos','intervencoes','phq9','gad7'):
            if key == 'clinical_reading':
                from copy import deepcopy
                old,new=deepcopy(before[key]),deepcopy(after[key])
                old['evidence'].pop('assessments');new['evidence'].pop('assessments')
                self.assertEqual(old,new)
            else:self.assertEqual(before[key],after[key])

    def test_generic_paths_cannot_create_or_relabel_cbi_without_context(self):
        from app.services.registros_longitudinais import criar_registro_longitudinal, atualizar_registro_longitudinal
        from app.schemas.registros_longitudinais import RegistroLongitudinalCreate
        from fastapi import HTTPException
        form=self.client.get(self.path()).json()['cbi']['formulario']
        patient=self.db.execute(text('SELECT paciente_id FROM contextos_assistenciais WHERE id=:c'),dict(c=self.open)).scalar_one()
        legacy_form=self.db.execute(text("SELECT id FROM formularios_modulo WHERE codigo='BEM_ESTAR_V1'")).scalar_one()
        legacy=self.db.execute(text("INSERT INTO registros_longitudinais(paciente_id,modulo_id,formulario_id,data_registro,origem) VALUES (:p,3,:f,'2026-01-01','PROFISSIONAL') RETURNING id"),dict(p=patient,f=legacy_form)).scalar_one()
        self.db.commit()
        before=self.db.execute(text('SELECT count(*) FROM registros_longitudinais')).scalar()
        payload=RegistroLongitudinalCreate(paciente_id=patient,modulo_id=3,formulario_id=form['id'],data_registro='2026-01-01',origem='PROFISSIONAL',respostas=[])
        for operation in (lambda:criar_registro_longitudinal(self.db,payload),lambda:atualizar_registro_longitudinal(self.db,legacy,payload)):
            with self.assertRaises(HTTPException) as error:operation()
            self.assertEqual(error.exception.status_code,403)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM registros_longitudinais')).scalar(),before)

    def test_scope_denied(self):
        other_person = self.db.execute(text("INSERT INTO pessoas(nome_completo) VALUES ('Synthetic other person') RETURNING id")).scalar_one()
        self.db.commit()
        self.assertEqual(self.post(person=other_person).status_code, 403)
        for change in (dict(person=self.person+100000),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.post(**change).status_code,403)

    def test_admin_no_bypass_and_no_grant(self):
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:u"),dict(u=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:g'),dict(g=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']))
        self.assertEqual(self.post().status_code,403)

    def test_read_permission_and_invalid_payload(self):
        for values in ({'pessoa_id':self.person},{'registrador_usuario_id':self.actor},{'respostas':{}},
                       {'respostas':{name:'5' for name,_,_ in FIELDS}},
                       {'respostas':{name:1 for name,_,_ in FIELDS}}):
            self.assertEqual(self.post(values).status_code,422)
        self.assertEqual(self.post().status_code,201)
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:g'),dict(g=self.grant_ids[self.open,'ASSISTENCIAL_LER']))
        self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)

    def test_rollback_after_record_and_answers(self):
        before=self.db.execute(text("SELECT count(*) FROM avaliacoes_clinicas WHERE instrumento='CBI'")).scalar()
        with patch('app.services.cbi.executar_avaliacao_clinica',side_effect=RuntimeError('synthetic')):
            self.assertEqual(self.post().status_code,500)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM registros_longitudinais WHERE contexto_assistencial_id=:c'),dict(c=self.open)).scalar(),0)
        self.assertEqual(self.db.execute(text("SELECT count(*) FROM avaliacoes_clinicas WHERE instrumento='CBI'")).scalar(),before)

    def test_catalog_and_history_protected(self):
        from alembic import command
        from test_m0_baseline import config
        form=self.client.get(self.path()).json()['cbi']['formulario']
        self.assertEqual(len(form['campos']),19)
        self.assertEqual(self.post().status_code,201)
        self.db.rollback()
        with self.assertRaisesRegex(RuntimeError,'CBI_HISTORY_PRESENT'):
            with self.engine.begin() as c:
                command.downgrade(config(c),'w3_gad7_v1')
        self.assertEqual(len(self.client.get(self.path()).json()['cbi']['itens']),1)

    def test_get_never_commits(self):
        self.assertEqual(self.post().status_code,201)
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'flush',wraps=self.db.flush) as flush:
            self.assertEqual(self.client.get(self.path()).status_code,200)
            commit.assert_not_called()
            flush.assert_not_called()

    def test_concurrent_revocation_prevents_write(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from sqlalchemy.orm import Session
        from app.schemas.cbi import CBICreate
        from app.services.cbi import CBIService, CBIDenied
        payload = CBICreate(respostas={name:'0' for name,_,_ in FIELDS})
        self.db.rollback()
        self.commands.revoke(self.db,dict(instituicao_id=self.institution,id=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR'],motivo='Synthetic race'),actor_id=self.target)
        started = Event()
        def worker():
            with Session(self.engine) as db:
                started.set()
                try:
                    CBIService().create(db,payload,actor=self.actor,institution=self.institution,person=self.person,context=self.open)
                except CBIDenied:
                    db.rollback()
                    return 'DENIED'
                db.rollback()
                return 'UNEXPECTED'
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(worker)
            self.assertTrue(started.wait(2))
            self.db.commit()
            self.assertEqual(future.result(timeout=8),'DENIED')

    def test_inactive_line_blocks_write(self):
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c AND modulo_id=3'), dict(c=self.open))
        self.db.commit()
        self.assertEqual(self.post().status_code, 403)

    def test_closed_context_blocks_write(self):
        self.db.execute(text("UPDATE contextos_assistenciais SET data_fim=CURRENT_DATE-1 WHERE id=:c"), dict(c=self.open))
        self.db.commit()
        self.assertEqual(self.post().status_code, 403)

    def test_context_and_author_dependencies_rechecked(self):
        cases = [('UPDATE usuarios SET ativo=false WHERE id=:i', self.actor),
                 ('UPDATE pessoas SET ativo=false WHERE id=:i', self.person),
                 ('UPDATE profissional_instituicoes SET ativo=false WHERE id=:i', self.links[0]),
                 ('DELETE FROM contexto_profissionais WHERE id=:i', self.participations[self.open])]
        for sql, identity in cases:
            with self.subTest(sql=sql):
                self.db.execute(text(sql), dict(i=identity))
                self.assertEqual(self.post().status_code, 403)
                self.db.rollback()

    def test_migration_roundtrip_preserves_phq9_and_all_existing_catalog(self):
        from alembic import command
        from sqlalchemy import create_engine
        from uuid import uuid4
        from test_m0_baseline import config
        name='cbi_migration_'+uuid4().hex
        with self.admin.connect() as c:c.exec_driver_sql('CREATE DATABASE '+name)
        engine=create_engine(self.engine.url.set(database=name))
        try:
            with engine.begin() as c:
                command.upgrade(config(c),'w3_gad7_v1')
                before=c.execute(text('SELECT to_jsonb(f) FROM campos_formulario f ORDER BY id')).scalars().all()
                command.upgrade(config(c),'w3_cbi_v1')
                after=c.execute(text("SELECT to_jsonb(f) FROM campos_formulario f WHERE formulario_id NOT IN (SELECT id FROM formularios_modulo WHERE codigo='CBI') ORDER BY id")).scalars().all()
                self.assertEqual(before,after)
                self.assertEqual(c.execute(text("SELECT count(*) FROM campos_formulario WHERE formulario_id IN (SELECT id FROM formularios_modulo WHERE codigo='CBI')")).scalar(),19)
                command.downgrade(config(c),'w3_gad7_v1')
                self.assertEqual(c.execute(text('SELECT to_jsonb(f) FROM campos_formulario f ORDER BY id')).scalars().all(),before)
                command.upgrade(config(c),'w3_cbi_v1')
                self.assertEqual(c.execute(text("SELECT count(*) FROM formularios_modulo WHERE codigo='CBI'")).scalar(),1)
        finally:
            engine.dispose()
            with self.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+name)

    def test_phq9_and_cbi_remain_separate_within_same_journey(self):
        u=urlsplit(self.path())
        r=self.client.request('POST',u.path+'/phq9',params=dict(parse_qsl(u.query)),body=json.dumps({'respostas':{f'phq9_{i}':'2' for i in range(1,10)}}).encode(),headers={'Content-Type':'application/json'})
        self.assertEqual(r.status_code,201,r.text)
        g=self.client.request('POST',u.path+'/gad7',params=dict(parse_qsl(u.query)),body=json.dumps({'respostas':{f'gad7_{i}':'2' for i in range(1,8)}}).encode(),headers={'Content-Type':'application/json'})
        self.assertEqual(g.status_code,201,g.text)
        before=self.client.get(self.path()).json()
        self.assertEqual(self.post().status_code,201)
        after=self.client.get(self.path()).json()
        for key in ('phq9','gad7','bem_estar','clinical_reading','diagnosticos','intervencoes'):
            if key == 'clinical_reading':
                from copy import deepcopy
                old,new=deepcopy(before[key]),deepcopy(after[key])
                old['evidence'].pop('assessments');new['evidence'].pop('assessments')
                self.assertEqual(old,new)
            else:self.assertEqual(before[key],after[key])
        self.assertEqual(after['phq9']['itens'][0]['resultado']['score'],18)
        self.assertEqual([x['score'] for x in after['cbi']['itens'][0]['resultado']['dominios']],[25,32.14,25])
        self.assertTrue(all(key.startswith('cbi_') for key in after['cbi']['itens'][0]['resultado']['metadata']['respostas']))


class CBIEngineTests(unittest.TestCase):
    def evaluate(self, answers):
        from app.services.clinical_engine.assessment_service import executar_avaliacao_clinica
        from app.services.clinical_engine.context import AssessmentContext
        return executar_avaliacao_clinica(AssessmentContext(registro_id=1,instrumento='CBI',respostas=answers,modulo_id=3,metadata={'contexto_assistencial_id':1}))

    def test_catalog_domains_and_scales(self):
        self.assertEqual(len(FIELDS),19)
        self.assertEqual([len(d['itens']) for d in DOMAINS],[6,7,6])
        self.assertEqual([k for d in DOMAINS for k in d['itens']],[k for k,_,_ in FIELDS])
        for key,_,options in FIELDS:
            self.assertEqual([v for v,_ in options],['4','3','2','1','0'])
            degree=key in {'cbi_wb5','cbi_wb6','cbi_wb7','cbi_cb1','cbi_cb2','cbi_cb3','cbi_cb4'}
            self.assertEqual(options[0][1],'Em um grau muito alto' if degree else 'Sempre')
        self.assertIn('energia suficiente',dict((k,label) for k,label,_ in FIELDS)['cbi_wb4'])

    def test_all_item_conversions_reverse_and_independent_means(self):
        for key,_,_ in FIELDS:
            for value in range(5):
                answers={name:'0' for name,_,_ in FIELDS};answers['cbi_wb4']='4'
                answers[key]=str(value)
                result=self.evaluate(answers)
                expected=100-value*25 if key=='cbi_wb4' else value*25
                self.assertEqual(result['metadata']['pontuacoes_itens'][key],expected)
                for domain in result['dominios']:
                    self.assertEqual(domain['soma'],expected if key in domain['itens'] else 0)
                    self.assertAlmostEqual(domain['score'],domain['soma']/domain['quantidade_itens'],places=2)
                for absent in ('score','classificacao','classificacao_codigo'):
                    self.assertNotIn(absent,result)
        for maximum in (False,True):
            answers={k:('4' if maximum else '0') for k,_,_ in FIELDS};answers['cbi_wb4']='0' if maximum else '4'
            self.assertEqual([d['score'] for d in self.evaluate(answers)['dominios']],[100 if maximum else 0]*3)

    def test_validation_requires_exact_19_and_context(self):
        from app.schemas.cbi import CBICreate
        from pydantic import ValidationError
        from app.services.clinical_engine.context import AssessmentContext
        from app.services.clinical_engine.assessments.cbi_engine import CBIEngine
        answers={k:'2' for k,_,_ in FIELDS}
        for invalid in ({},dict(answers,extra='0'),dict(answers,cbi_pb1=True),dict(answers,cbi_pb1='5'),{f'gad7_{i}':'0' for i in range(1,8)}):
            with self.assertRaises(ValidationError):CBICreate(respostas=invalid)
        for domain in DOMAINS:
            incomplete=dict(answers);del incomplete[domain['itens'][0]]
            with self.assertRaises(ValidationError):CBICreate(respostas=incomplete)
        with self.assertRaisesRegex(ValueError,'CBI_REQUIRES_CONTEXT'):
            CBIEngine().executar(AssessmentContext(registro_id=1,instrumento='CBI',respostas=answers,modulo_id=3))
