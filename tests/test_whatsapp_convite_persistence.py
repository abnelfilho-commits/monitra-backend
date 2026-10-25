"""D9.2-A: real PG18, only fresh owned databases on disposable port 55620."""
import os
import unittest
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from contextlib import ExitStack
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic import command

URL = os.getenv('M0_TEST_POSTGRES_URL')
if URL:
    u = make_url(URL)
    if (u.host != '127.0.0.1' or u.port != 55620 or u.database != 'm0_baseline'
            or u.get_backend_name() != 'postgresql' or u.query
            or make_url(os.environ.get('DATABASE_URL', 'sqlite://')) != u):
        raise RuntimeError('Matching explicit disposable PostgreSQL URLs required')

import test_checkin_bem_estar as fixture
from test_m0_baseline import config
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio, WhatsAppConviteStatusEvento as Evento
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation

HEAD = 'd92e12c_autorizacao_whatsapp'
NEW = {'whatsapp_autorizacoes_comunicacao', 'whatsapp_solicitacoes_manuais', 'whatsapp_convite_envios', 'whatsapp_convite_status_eventos'}


@unittest.skipUnless(URL, 'Explicit disposable PostgreSQL required')
class PersistenceTests(unittest.TestCase):
    command_grant = fixture.CheckinTests.command_grant
    path = fixture.CheckinTests.path

    @classmethod
    def setUpClass(cls):
        cls.admin = create_engine(make_url(URL), isolation_level='AUTOCOMMIT', hide_parameters=True)
        cls.name = 'd92a_' + uuid4().hex
        cls.engine = None
        cls.created = False
        cls.addClassCleanup(cls.cleanup)
        with cls.admin.connect() as c:
            if int(c.exec_driver_sql('SHOW server_version_num').scalar()) // 10000 != 18:
                raise RuntimeError('PostgreSQL 18 required')
            c.exec_driver_sql('CREATE DATABASE ' + cls.name)
            cls.created = True
        cls.engine = create_engine(make_url(URL).set(database=cls.name), hide_parameters=True)
        with cls.engine.begin() as c:
            command.upgrade(config(c), 'w3_whatsapp_mental_v1')

    @classmethod
    def cleanup(cls):
        if cls.engine is not None:
            cls.engine.dispose()
        if cls.created:
            with cls.admin.connect() as c:
                c.exec_driver_sql('DROP DATABASE ' + cls.name)
                assert not c.execute(text('SELECT 1 FROM pg_database WHERE datname=:n'), {'n': cls.name}).scalar()
            print('Discarded owned test database:', cls.name)
        cls.admin.dispose()

    def snapshot(self):
        with self.engine.connect() as c:
            names = set(inspect(c).get_table_names()) - NEW - {'alembic_version'}
            return {n: (inspect(c).get_columns(n), c.exec_driver_sql(
                'SELECT md5(coalesce(string_agg(row_to_json(t)::text, chr(10) ORDER BY row_to_json(t)::text),\'\')) FROM "'+n+'" t').scalar()) for n in names}

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch('requests.sessions.Session.request', side_effect=AssertionError('No external HTTP')))
        fixture.CheckinTests.setUp(self)
        self.addCleanup(self.db.close)
        self.now = datetime.now(timezone.utc)
        patient = self.db.execute(text('SELECT paciente_id FROM contextos_assistenciais WHERE id=:c'), {'c': self.open}).scalar_one()
        follow = Follow(contexto_assistencial_id=self.open, paciente_id=patient,
                        telefone='5511000000000', criado_por_usuario_id=self.actor)
        self.db.add(follow); self.db.flush()
        conversation = Conversation(acompanhamento_whatsapp_id=follow.id, contexto_assistencial_id=self.open,
                                    paciente_id=patient, telefone=follow.telefone, data_referencia=self.now.date(),
                                    expires_at=self.now+timedelta(hours=24), status='CONCLUIDA')
        self.db.add(conversation); self.db.commit()
        self.cid = conversation.id
        self.db.rollback()
        before = self.snapshot()
        with self.engine.begin() as c:
            command.upgrade(config(c), HEAD)
        after = self.snapshot()
        # Compare full rows and column definitions, excluding SQLAlchemy type object identity.
        self.assertEqual({k: ([(x['name'], str(x['type']), x['nullable'], x['default']) for x in v[0]], v[1]) for k,v in before.items()},
                         {k: ([(x['name'], str(x['type']), x['nullable'], x['default']) for x in v[0]], v[1]) for k,v in after.items()})

    def envio(self, **changes):
        data = dict(conversa_id=self.cid, tentativa=1, correlacao_id=str(uuid4()), phone_number_id='synthetic-emitter')
        data.update(changes)
        e = Envio(**data); self.db.add(e); self.db.flush(); return e

    def evento(self, envio=None, **changes):
        data = dict(envio_id=envio.id if envio else None, phone_number_id='synthetic-emitter',
                    wamid=envio.wamid if envio else 'unknown', status='sent', evento_em=self.now,
                    deduplicacao_chave=uuid4().hex+uuid4().hex)
        data.update(changes)
        e = Evento(**data); self.db.add(e); self.db.flush(); return e

    def rejected(self, operation):
        with self.assertRaises(IntegrityError), self.db.begin_nested():
            operation()

    def test_upgrade_preserves_existing_rows_and_schema(self):
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(), HEAD)
            self.assertTrue(NEW <= set(inspect(c).get_table_names()))
            self.assertEqual(c.execute(text('SELECT convite_enviado_em FROM whatsapp_conversas_contextuais WHERE id=:i'), {'i': self.cid}).scalar(), None)

    def test_persistence_and_context_relationship_new_connection(self):
        e = self.envio(wamid='persist-'+uuid4().hex, estado='ACEITO', confirmado_em=self.now)
        v = self.evento(e, status='failed', meta_error_code=131000, motivo_sanitizado='Synthetic failure')
        eid, vid = e.id, v.id
        self.db.commit()
        with Session(self.engine) as db:
            saved = db.get(Evento, vid)
            self.assertEqual(saved.envio.id, eid)
            self.assertEqual(saved.envio.conversa.contexto_assistencial_id, self.open)
            self.assertEqual(saved.evento_em, self.now)
            self.assertIsNotNone(saved.recebido_em)
            self.assertEqual(saved.meta_error_code, 131000)

    def test_attempt_and_correlation_uniqueness(self):
        e = self.envio()
        self.rejected(lambda: self.envio())
        self.rejected(lambda: self.envio(tentativa=2, correlacao_id=e.correlacao_id))
        self.envio(tentativa=2)  # No non-null wamid required for prepared attempts.

    def test_wamid_unique_per_emitter(self):
        self.envio(wamid='unique-'+str(self.cid))
        self.rejected(lambda: self.envio(tentativa=2, wamid='unique-'+str(self.cid)))
        self.envio(tentativa=2, phone_number_id='other-emitter', wamid='unique-'+str(self.cid))

    def test_dedup_and_distinct_statuses(self):
        e = self.envio(wamid='events-'+str(self.cid))
        v = self.evento(e)
        self.rejected(lambda: self.evento(e, deduplicacao_chave=v.deduplicacao_chave))
        for status in ('delivered','read','failed'):
            self.evento(e, status=status)

    def test_unknown_callback_and_later_binding(self):
        v = self.evento(wamid='early-'+str(self.cid))
        self.db.commit()
        e = self.envio(wamid=v.wamid)
        v.envio = e
        self.db.commit()
        with Session(self.engine) as db:
            self.assertEqual(db.get(Evento, v.id).envio_id, e.id)

    def test_wrong_emitter_wamid_or_missing_parent_rejected(self):
        e = self.envio(wamid='bound-'+str(self.cid))
        self.rejected(lambda: self.evento(e, phone_number_id='wrong'))
        self.rejected(lambda: self.evento(e, wamid='wrong'))
        self.rejected(lambda: self.evento(envio_id=2147483647))
        self.rejected(lambda: self.envio(conversa_id=2147483647))

    def test_constraints(self):
        for fields in ({'tentativa':0}, {'estado':'DELIVERED'}, {'estado':'ACEITO'},
                       {'phone_number_id':' '}, {'wamid':''}, {'graph_http_status':999}, {'meta_error_code':-1}):
            self.rejected(lambda f=fields: self.envio(**f))
        for fields in ({'status':'unknown'}, {'deduplicacao_chave':'short'}, {'meta_error_code':-1}):
            self.rejected(lambda f=fields: self.evento(**f))

    def test_restrict_delete(self):
        e = self.envio(wamid='delete-'+str(self.cid)); self.evento(e)
        self.rejected(lambda: self.db.execute(text('DELETE FROM whatsapp_convite_envios WHERE id=:i'), {'i':e.id}))
        self.rejected(lambda: self.db.execute(text('DELETE FROM whatsapp_conversas_contextuais WHERE id=:i'), {'i':self.cid}))

    def test_rollback_leaves_no_attempt(self):
        e = self.envio(); identity = e.id
        self.db.rollback()
        with Session(self.engine) as db:
            self.assertIsNone(db.get(Envio, identity))

    def test_model_columns_match_migration(self):
        for model in (Envio, Evento):
            physical = {c['name']:c for c in inspect(self.engine).get_columns(model.__tablename__)}
            self.assertEqual(set(physical), set(model.__table__.c.keys()))
            for column in model.__table__.c:
                self.assertEqual(column.nullable, physical[column.name]['nullable'])
                self.assertEqual(str(column.type.compile(dialect=self.engine.dialect)), str(physical[column.name]['type'].compile(dialect=self.engine.dialect)))
