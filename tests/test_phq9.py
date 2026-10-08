"""Authorized contextual intervention HTTP, on real disposable PostgreSQL."""
import json
import os
import unittest
from urllib.parse import urlsplit, parse_qsl
from unittest.mock import patch
from sqlalchemy import text
import test_checkin_bem_estar as foundation


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class PHQ9Tests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(foundation.CheckinTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.CheckinTests.tearDownClass.__func__)
    command_grant = foundation.CheckinTests.command_grant
    setUp = foundation.CheckinTests.setUp
    tearDown = foundation.CheckinTests.tearDown
    path = foundation.CheckinTests.path

    def post(self, changes=None, **scope):
        u = urlsplit(self.path(**scope))
        payload = dict(respostas={f'phq9_{i}':'1' for i in range(1,10)})
        payload.update(changes or {})
        return self.client.request('POST', u.path + '/phq9', params=dict(parse_qsl(u.query)),
                                   body=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})

    def test_persistence_framework_authorship_and_repeated_assessment(self):
        before=self.client.get(self.path()).json()
        r=self.post()
        self.assertEqual(r.status_code,201,r.text)
        d=r.json()
        self.assertEqual(d['resultado']['score'],9)
        self.assertEqual(d['registrador_usuario_id'],self.actor)
        self.assertEqual(self.client.get(self.path()).json()['phq9']['itens'],[d])
        self.assertEqual(self.db.execute(text("SELECT count(*) FROM respostas_registro WHERE registro_id=:r"),dict(r=d['registro_id'])).scalar(),9)
        self.assertEqual(self.db.execute(text("SELECT contexto_assistencial_id FROM registros_longitudinais WHERE id=:r"),dict(r=d['registro_id'])).scalar(),self.open)
        from app.services.clinical_engine.assessment_builder import AssessmentBuilder
        with self.assertRaisesRegex(ValueError, 'não encontrado'):
            AssessmentBuilder.from_registro(self.db,d['registro_id'],'PHQ9')
        self.assertEqual(self.post().status_code,201)
        after=self.client.get(self.path()).json()
        self.assertEqual(len(after['phq9']['itens']),2)
        for key in ('clinical_reading','bem_estar','diagnosticos','intervencoes'):
            if key == 'clinical_reading':
                from copy import deepcopy
                old,new=deepcopy(before[key]),deepcopy(after[key])
                old['evidence'].pop('assessments');new['evidence'].pop('assessments')
                old.pop('summary');new.pop('summary')
                old['metadata'].pop('summary_sources');new['metadata'].pop('summary_sources')
                self.assertEqual(old,new)
            else:self.assertEqual(before[key],after[key])

    def test_generic_paths_cannot_create_or_relabel_phq9_without_context(self):
        from app.services.registros_longitudinais import criar_registro_longitudinal, atualizar_registro_longitudinal
        from app.schemas.registros_longitudinais import RegistroLongitudinalCreate
        from fastapi import HTTPException
        form=self.client.get(self.path()).json()['phq9']['formulario']
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
                       {'respostas':{f'phq9_{i}':'4' for i in range(1,10)}},
                       {'respostas':{f'phq9_{i}':1 for i in range(1,10)}}):
            self.assertEqual(self.post(values).status_code,422)
        self.assertEqual(self.post().status_code,201)
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:g'),dict(g=self.grant_ids[self.open,'ASSISTENCIAL_LER']))
        self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)

    def test_rollback_after_record_and_answers(self):
        before=self.db.execute(text("SELECT count(*) FROM avaliacoes_clinicas WHERE instrumento='PHQ9'")).scalar()
        with patch('app.services.phq9.executar_avaliacao_clinica',side_effect=RuntimeError('synthetic')):
            self.assertEqual(self.post().status_code,500)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM registros_longitudinais WHERE contexto_assistencial_id=:c'),dict(c=self.open)).scalar(),0)
        self.assertEqual(self.db.execute(text("SELECT count(*) FROM avaliacoes_clinicas WHERE instrumento='PHQ9'")).scalar(),before)

    def test_catalog_and_history_protected(self):
        from alembic import command
        from test_m0_baseline import config
        form=self.client.get(self.path()).json()['phq9']['formulario']
        self.assertEqual(len(form['campos']),9)
        self.assertEqual(self.post().status_code,201)
        self.db.rollback()
        with self.assertRaisesRegex(RuntimeError,'PHQ9_HISTORY_PRESENT'):
            with self.engine.begin() as c:
                command.downgrade(config(c),'w3_intervencao_autoria_v1')
        self.assertEqual(len(self.client.get(self.path()).json()['phq9']['itens']),1)

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
        from app.schemas.phq9 import PHQ9Create
        from app.services.phq9 import PHQ9Service, PHQ9Denied
        payload = PHQ9Create(respostas={f'phq9_{i}':'0' for i in range(1,10)})
        self.db.rollback()
        self.commands.revoke(self.db,dict(instituicao_id=self.institution,id=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR'],motivo='Synthetic race'),actor_id=self.target)
        started = Event()
        def worker():
            with Session(self.engine) as db:
                started.set()
                try:
                    PHQ9Service().create(db,payload,actor=self.actor,institution=self.institution,person=self.person,context=self.open)
                except PHQ9Denied:
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

    def test_migration_roundtrip_preserves_existing_catalog_and_guards_long_labels(self):
        from alembic import command
        from sqlalchemy import create_engine
        from uuid import uuid4
        from test_m0_baseline import config
        name='phq9_migration_'+uuid4().hex
        with self.admin.connect() as c:c.exec_driver_sql('CREATE DATABASE '+name)
        engine=create_engine(self.engine.url.set(database=name))
        try:
            with engine.begin() as c:
                command.upgrade(config(c),'w3_intervencao_autoria_v1')
                before=c.execute(text('SELECT to_jsonb(f) FROM campos_formulario f ORDER BY id')).scalars().all()
                command.upgrade(config(c),'w3_phq9_v1')
                after=c.execute(text("SELECT to_jsonb(f) FROM campos_formulario f WHERE formulario_id NOT IN (SELECT id FROM formularios_modulo WHERE codigo='PHQ9') ORDER BY id")).scalars().all()
                self.assertEqual(before,after)
                self.assertEqual(c.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='campos_formulario' AND column_name='label'")).scalar(),'text')
                self.assertEqual(c.execute(text("SELECT count(*) FROM campos_formulario WHERE formulario_id IN (SELECT id FROM formularios_modulo WHERE codigo='PHQ9')")).scalar(),9)
                command.downgrade(config(c),'w3_intervencao_autoria_v1')
                self.assertEqual(c.execute(text('SELECT to_jsonb(f) FROM campos_formulario f ORDER BY id')).scalars().all(),before)
                command.upgrade(config(c),'w3_phq9_v1')
                c.execute(text("UPDATE campos_formulario SET label=:label WHERE id=(SELECT min(id) FROM campos_formulario)"),dict(label='x'*201))
            with self.assertRaisesRegex(RuntimeError,'LONG_QUESTION_LABEL_PRESENT'):
                with engine.begin() as c:command.downgrade(config(c),'w3_intervencao_autoria_v1')
            with engine.connect() as c:
                self.assertEqual(c.execute(text("SELECT count(*) FROM formularios_modulo WHERE codigo='PHQ9'")).scalar(),1)
        finally:
            engine.dispose()
            with self.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+name)


class PHQ9EngineTests(unittest.TestCase):
    def test_all_standard_boundaries_and_item9(self):
        from app.services.clinical_engine.assessment_service import executar_avaliacao_clinica
        from app.services.clinical_engine.context import AssessmentContext
        for score,code in [(0,'MINIMA'),(4,'MINIMA'),(5,'LEVE'),(9,'LEVE'),(10,'MODERADA'),(14,'MODERADA'),(15,'MODERADAMENTE_GRAVE'),(19,'MODERADAMENTE_GRAVE'),(20,'GRAVE'),(27,'GRAVE')]:
            remaining=score
            answers={}
            for i in range(1,10):
                answers[f'phq9_{i}']=str(min(3,remaining));remaining=max(0,remaining-3)
            context=AssessmentContext(registro_id=1,instrumento='PHQ9',respostas=answers,modulo_id=3,metadata={'contexto_assistencial_id':1})
            result=executar_avaliacao_clinica(context)
            self.assertEqual((result['score'],result['classificacao_codigo']),(score,code))
            self.assertIn('não estabelece diagnóstico',result['interpretacao'])
            self.assertEqual(bool(result['alertas']),answers['phq9_9']!='0')
        context.respostas={f'phq9_{i}': '1' if i==9 else '0' for i in range(1,10)}
        result=executar_avaliacao_clinica(context)
        self.assertEqual(result['score'],1)
        self.assertTrue(result['alertas'])
        context.metadata={}
        with self.assertRaisesRegex(ValueError,'PHQ9_REQUIRES_CONTEXT'):
            executar_avaliacao_clinica(context)

    def test_payload_requires_exact_nine_questions(self):
        from app.schemas.phq9 import PHQ9Create
        from pydantic import ValidationError
        answers={f'phq9_{i}':'0' for i in range(1,10)}
        for invalid in ({},dict(answers,extra='0'),dict(answers,phq9_1=True),dict(answers,phq9_1='4')):
            with self.assertRaises(ValidationError):PHQ9Create(respostas=invalid)
