"""HTTP contract for institutional financial context using disposable PostgreSQL 18."""

import os
import unittest
from types import SimpleNamespace
from uuid import uuid4

from alembic import command
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.deps import get_usuario_atual
from app.database import get_db
from app.routers import financeiro_institucional as api
from app.models.financeiro import ContratoFinanceiro, TabelaPreco
from app.services.financeiro.configuracao import FinanceiroConfiguracaoService
from test_m0_baseline import config
from test_whatsapp_security import LocalClient


URL = os.getenv("M0_TEST_POSTGRES_URL")


@unittest.skipUnless(URL, "Requires disposable PostgreSQL 18")
class InstitutionalContextPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host != "127.0.0.1" or url.database != "m0_baseline":
            raise RuntimeError("Disposable local database only")

        cls.url = url
        cls.admin = create_engine(url, isolation_level="AUTOCOMMIT")
        cls.template = "financial_context_template_" + uuid4().hex

        with cls.admin.connect() as c:
            if int(c.exec_driver_sql("SHOW server_version_num").scalar()) // 10000 != 18:
                raise RuntimeError("PostgreSQL 18 required")
            c.exec_driver_sql("CREATE DATABASE " + cls.template)

        engine = create_engine(url.set(database=cls.template))
        with engine.begin() as c:
            command.upgrade(config(c), "head")
        engine.dispose()

    @classmethod
    def tearDownClass(cls):
        with cls.admin.connect() as c:
            c.exec_driver_sql(
                "DROP DATABASE " + cls.template + " WITH (FORCE)"
            )
        cls.admin.dispose()

    def setUp(self):
        self.name = "financial_context_" + uuid4().hex

        with self.admin.connect() as c:
            c.exec_driver_sql(
                "CREATE DATABASE "
                + self.name
                + " TEMPLATE "
                + self.template
            )

        self.engine = create_engine(self.url.set(database=self.name))

        with self.engine.begin() as c:
            self.admin_id = c.execute(
                text(
                    "INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) "
                    "VALUES ('Admin','admin@example.invalid','x','ADMIN',true) "
                    "RETURNING id"
                )
            ).scalar()

            self.gestor_id = c.execute(
                text(
                    "INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) "
                    "VALUES ('Gestor','gestor@example.invalid','x','ADMIN_CLINICA',true) "
                    "RETURNING id"
                )
            ).scalar()

            self.allowed = c.execute(
                text(
                    "INSERT INTO instituicoes"
                    "(razao_social,nome_fantasia,tipo_instituicao,ativo) "
                    "VALUES ('Allowed Legal','Allowed','OUTRO',true) RETURNING id"
                )
            ).scalar()

            self.denied = c.execute(
                text(
                    "INSERT INTO instituicoes"
                    "(razao_social,nome_fantasia,tipo_instituicao,ativo) "
                    "VALUES ('Denied Legal','Denied','OUTRO',true) RETURNING id"
                )
            ).scalar()

            self.inactive = c.execute(
                text(
                    "INSERT INTO instituicoes"
                    "(razao_social,tipo_instituicao,ativo) "
                    "VALUES ('Inactive','OUTRO',false) RETURNING id"
                )
            ).scalar()

            c.execute(
                text(
                    "INSERT INTO usuario_instituicao_acessos"
                    "(usuario_id,instituicao_id,perfil_institucional,ativo) "
                    "VALUES (:u,:i,'GESTOR',true)"
                ),
                {"u": self.gestor_id, "i": self.allowed},
            )

        self.db = Session(self.engine)
        self.financeiro = FinanceiroConfiguracaoService()

        self.published_allowed = self._contract(
            None, self.allowed, "ALLOWED-PUBLISHED", "PUBLISHED"
        )
        self._contract(
            None, self.allowed, "ALLOWED-DRAFT", "DRAFT"
        )
        self.published_denied = self._contract(
            None, self.denied, "DENIED-PUBLISHED", "PUBLISHED"
        )
        self._contract(
            None, self.inactive, "INACTIVE-PUBLISHED", "PUBLISHED"
        )

        self.app = FastAPI()
        self.app.include_router(api.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = LocalClient(self.app)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

        with self.admin.connect() as c:
            c.exec_driver_sql(
                "DROP DATABASE " + self.name + " WITH (FORCE)"
            )


    def _contract(self, c, institution_id, code, state):
        table = self.financeiro.create(
            self.db,
            TabelaPreco,
            dict(
                proprietario_instituicao_id=institution_id,
                codigo=f"T-{code}",
                nome=f"Table {code}",
            ),
        )

        contract = self.financeiro.create(
            self.db,
            ContratoFinanceiro,
            dict(
                pagador_instituicao_id=institution_id,
                codigo=code,
                edicao=1,
                tabela_preco_id=table.id,
                inicio="2030-01-01",
            ),
        )

        self.db.commit()
        contract_id = contract.id

        if state == "PUBLISHED":
            self.financeiro.publish_contract(
                self.db,
                contract_id,
                actor_id=self.admin_id,
            )
            self.db.commit()

        return contract_id


    def get(self, user_id, profile, active=True):
        self.app.dependency_overrides[get_usuario_atual] = lambda: SimpleNamespace(
            id=user_id,
            perfil=profile,
            ativo=active,
        )
        return self.client.request(
            "GET",
            "/financeiro/institucional/contexto",
            b"",
            {},
            None,
        )

    def test_admin_sees_all_active_institutions_and_only_published_contracts(self):
        response = self.get(self.admin_id, "ADMIN")
        self.assertEqual(response.status_code, 200, response.text)

        body = response.json()
        self.assertEqual(
            {item["id"] for item in body["instituicoes"]},
            {self.allowed, self.denied},
        )
        self.assertEqual(
            {item["id"] for item in body["contratos"]},
            {self.published_allowed, self.published_denied},
        )

    def test_non_admin_sees_only_active_granted_institution_and_contract(self):
        response = self.get(self.gestor_id, "ADMIN_CLINICA")
        self.assertEqual(response.status_code, 200, response.text)

        body = response.json()
        self.assertEqual(
            [item["id"] for item in body["instituicoes"]],
            [self.allowed],
        )
        self.assertEqual(
            [item["id"] for item in body["contratos"]],
            [self.published_allowed],
        )
        self.assertEqual(body["instituicoes"][0]["nome"], "Allowed")

    def test_inactive_user_is_rejected(self):
        response = self.get(self.gestor_id, "ADMIN_CLINICA", active=False)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"], {"code": "USER_INACTIVE"})


if __name__ == "__main__":
    unittest.main()
