"""D-FIN-01: canonical names, legacy fallback and unchanged economic identities.

Uses only the disposable PostgreSQL fixture; never HML data.
"""
import os
import unittest
from alembic import command
from sqlalchemy import text
from app.models.financeiro import PacienteContrato
import test_financeiro_postgres as fixtures
from test_m0_baseline import config


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class PatientNamesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.FinancialPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixtures.FinancialPostgresTests.tearDownClass.__func__(cls)

    def setUp(self):
        fixtures.FinancialPostgresTests.setUp(self)
        with self.engine.begin() as c:
            command.upgrade(config(c), 'w3_atendimento_mental_v1')
            person = c.exec_driver_sql("INSERT INTO pessoas(nome_completo) VALUES ('Antônio João') RETURNING id").scalar()
            c.execute(text("UPDATE pacientes SET pessoa_id=:person,nome='ZZZ legado' WHERE id=:id"), {'person': person, 'id': self.patient})
            self.legacy = c.exec_driver_sql("INSERT INTO pacientes(nome,ativo) VALUES ('Legacy',true) RETURNING id").scalar()
            c.execute(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio,ativo) VALUES (:p,:i,'BENEFICIARIO',CURRENT_DATE,true)"), {'p': self.legacy, 'i': self.owner})
            # A second agenda proves ordering uses the displayed name, not ZZZ.
            c.execute(text("INSERT INTO agenda_cuidados(pts_id,objetivo_id,atividade_id,ocupacao_id,frequencia_semanal,duracao_minutos,data_inicio) SELECT pts_id,objetivo_id,atividade_id,ocupacao_id,frequencia_semanal,duracao_minutos,data_inicio FROM agenda_cuidados WHERE id=:a"), {'a': self.agenda})

    def tearDown(self):
        fixtures.FinancialPostgresTests.tearDown(self)

    def test_candidates_canonical_legacy_order_and_payer_isolation(self):
        rows = self.service.list_beneficiary_candidates(self.db, self.cid)
        self.assertEqual([(r['paciente_id'], r['paciente_nome']) for r in rows], [(self.patient, 'Antônio João'), (self.legacy, 'Legacy')])
        self.db.rollback()
        with self.engine.begin() as c:
            c.execute(text('UPDATE paciente_instituicoes SET instituicao_id=:i WHERE paciente_id=:p'), {'i': self.other, 'p': self.patient})
        self.assertEqual([r['paciente_id'] for r in self.service.list_beneficiary_candidates(self.db, self.cid)], [self.legacy])

    def test_beneficiaries_list_and_detail_keep_ids_and_legacy_names(self):
        for patient in (self.legacy, self.patient):
            self.service.create(self.db, PacienteContrato, dict(paciente_id=patient, contrato_id=self.cid, inicio=self.today))
        self.db.commit()
        rows = self.service.list_beneficiaries(self.db, self.cid)
        self.assertEqual([r['paciente_nome'] for r in rows], ['Antônio João', 'Legacy'])
        for row in rows:
            self.assertEqual(self.service.get_beneficiary(self.db, row['id']), row)
        self.assertEqual(self.db.execute(text('SELECT nome FROM pacientes WHERE id=:p'), {'p': self.patient}).scalar(), 'ZZZ legado')

    def test_mapping_search_uses_canonical_name_and_legacy_fallback(self):
        rows = self.service.list_mapping_agendas(self.db, busca='Antônio João')
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['paciente_id'] == self.patient and r['paciente_nome'] == 'Antônio João' for r in rows))
        self.assertEqual([r['agenda_cuidado_id'] for r in rows], sorted(r['agenda_cuidado_id'] for r in rows))
        self.assertEqual(self.service.list_mapping_agendas(self.db, busca='ZZZ legado'), [])
        self.db.rollback()
        with self.engine.begin() as c:
            c.execute(text('UPDATE pacientes SET pessoa_id=NULL WHERE id=:p'), {'p': self.patient})
        self.assertEqual(len(self.service.list_mapping_agendas(self.db, busca='ZZZ legado')), 2)
        self.assertEqual(self.service.list_mapping_agendas(self.db, busca='Antônio João'), [])
