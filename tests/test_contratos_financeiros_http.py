"""AE3: contracts and beneficiaries over real PostgreSQL, JWT and HTTP."""
import json
import os
import unittest
from datetime import timedelta

from fastapi import FastAPI
from sqlalchemy import text

from app.core.security import criar_access_token
from app.database import get_db
from app.main import app as main_app
from app.routers import contratos_financeiros as api
from test_whatsapp_security import LocalClient
import test_financeiro_postgres as fixtures


class RoutesTests(unittest.TestCase):
    def test_all_nine_routes_registered(self):
        paths = {
            (method, route.path)
            for route in main_app.routes
            for method in getattr(route, "methods", [])
        }

        for route in api.router.routes:
            for method in route.methods:
                self.assertIn((method, route.path), paths)

        self.assertEqual(len(api.router.routes), 9)


@unittest.skipUnless(
    os.getenv("M0_TEST_POSTGRES_URL"),
    "Disposable PostgreSQL 18 required",
)
class ContractsHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.FinancialPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixtures.FinancialPostgresTests.tearDownClass.__func__(cls)

    def setUp(self):
        fixtures.FinancialPostgresTests.setUp(self)

        self.app = FastAPI()
        self.app.include_router(api.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = LocalClient(self.app)

        self.users = {"ADMIN": self.actor}

        with self.engine.begin() as c:
            for role in ("ADMIN_CLINICA", "PROFISSIONAL", "SUPORTE", "GESTOR"):
                self.users[role] = c.execute(
                    text(
                        "INSERT INTO usuarios"
                        "(nome,email,senha_hash,perfil,ativo) "
                        "VALUES ('Synthetic',:e,'synthetic',:r,true) "
                        "RETURNING id"
                    ),
                    {"e": role + "@example.invalid", "r": role},
                ).scalar()

    def tearDown(self):
        fixtures.FinancialPostgresTests.tearDown(self)

    def req(self, method, path, body=None, role="ADMIN", token=None):
        if token is None and role:
            token = criar_access_token(
                {"sub": str(self.users[role]), "tipo": "usuario"}
            )

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token

        return self.client.request(
            method,
            "/admin/economia" + path,
            json.dumps(body).encode() if body is not None else b"",
            headers,
        )

    def ok(self, method, path, body=None):
        response = self.req(method, path, body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def contract_payload(self, **changes):
        payload = {
            "pagador_instituicao_id": self.owner,
            "codigo": "AE3",
            "edicao": 2,
            "tabela_preco_id": self.tid,
            "inicio": str(self.today),
            "fim": str(self.today + timedelta(days=90)),
        }
        payload.update(changes)
        return payload

    def test_contract_create_reload_update_publish_immutable(self):
        created = self.ok(
            "POST",
            "/contratos/",
            self.contract_payload(),
        )

        self.assertEqual(created["estado"], "DRAFT")
        self.assertEqual(created["pagador_instituicao_id"], self.owner)
        self.assertEqual(created["pagador_nome"], "A")
        self.assertEqual(created["tabela_preco_id"], self.tid)
        self.assertEqual(created["tabela_codigo"], "T")
        self.assertEqual(created["tabela_nome"], "Table")

        self.db.expire_all()

        self.assertEqual(
            self.ok("GET", f"/contratos/{created['id']}"),
            created,
        )

        rows = self.ok("GET", "/contratos/")
        self.assertEqual(len(rows), 2)

        updated = self.ok(
            "PUT",
            f"/contratos/{created['id']}",
            self.contract_payload(
                codigo="AE3-EDITADO",
                edicao=3,
            ),
        )
        self.assertEqual(updated["codigo"], "AE3-EDITADO")
        self.assertEqual(updated["edicao"], 3)

        published = self.ok(
            "POST",
            f"/contratos/{created['id']}/publicar",
        )
        self.assertEqual(published["estado"], "PUBLISHED")
        self.assertEqual(
            published["publicado_por_usuario_id"],
            self.actor,
        )
        self.assertIsNotNone(published["publicado_em"])

        blocked = self.req(
            "PUT",
            f"/contratos/{created['id']}",
            self.contract_payload(
                codigo="NAO-PODE",
                edicao=4,
            ),
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(
            blocked.json()["detail"]["code"],
            "PUBLISHED_IMMUTABLE",
        )

    def test_beneficiary_candidate_create_list_and_close(self):
        candidates = self.ok(
            "GET",
            f"/contratos/{self.cid}/beneficiarios/candidatos",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["paciente_id"],
            self.patient,
        )
        self.assertEqual(
            candidates[0]["paciente_nome"],
            "Synthetic",
        )

        created = self.ok(
            "POST",
            f"/contratos/{self.cid}/beneficiarios",
            {
                "paciente_id": self.patient,
                "inicio": str(self.today),
                "fim": None,
                "identificador_beneficiario": "BEN-001",
            },
        )

        self.assertEqual(created["paciente_id"], self.patient)
        self.assertEqual(created["contrato_id"], self.cid)
        self.assertEqual(created["paciente_nome"], "Synthetic")
        self.assertEqual(
            created["identificador_beneficiario"],
            "BEN-001",
        )
        self.assertIsNone(created["fim"])

        rows = self.ok(
            "GET",
            f"/contratos/{self.cid}/beneficiarios",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], created)

        closed = self.ok(
            "POST",
            f"/beneficiarios/{created['id']}/encerrar",
            {
                "fim": str(self.today + timedelta(days=30)),
            },
        )

        self.assertEqual(
            closed["fim"],
            str(self.today + timedelta(days=30)),
        )

    def test_beneficiary_must_be_within_contract_period(self):
        contract_end = self.today + timedelta(days=30)

        contract = self.ok(
            "POST",
            "/contratos/",
            self.contract_payload(
                codigo="AE3-PERIODO",
                edicao=10,
                fim=str(contract_end),
            ),
        )

        invalid_periods = [
            {
                "inicio": self.today - timedelta(days=1),
                "fim": contract_end,
            },
            {
                "inicio": self.today,
                "fim": None,
            },
            {
                "inicio": self.today,
                "fim": contract_end + timedelta(days=1),
            },
        ]

        for period in invalid_periods:
            response = self.req(
                "POST",
                f"/contratos/{contract['id']}/beneficiarios",
                {
                    "paciente_id": self.patient,
                    "inicio": (
                        str(period["inicio"])
                        if period["inicio"] is not None
                        else None
                    ),
                    "fim": (
                        str(period["fim"])
                        if period["fim"] is not None
                        else None
                    ),
                },
            )
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(
                response.json()["detail"]["code"],
                "BENEFICIARY_OUTSIDE_CONTRACT_PERIOD",
            )

        valid = self.ok(
            "POST",
            f"/contratos/{contract['id']}/beneficiarios",
            {
                "paciente_id": self.patient,
                "inicio": str(self.today),
                "fim": str(contract_end),
                "identificador_beneficiario": "BEN-PERIODO",
            },
        )

        self.assertEqual(valid["inicio"], str(self.today))
        self.assertEqual(valid["fim"], str(contract_end))

    def test_beneficiary_overlap_and_reentry(self):
        first_end = self.today + timedelta(days=10)

        first = self.ok(
            "POST",
            f"/contratos/{self.cid}/beneficiarios",
            {
                "paciente_id": self.patient,
                "inicio": str(self.today),
                "fim": str(first_end),
                "identificador_beneficiario": "BEN-FIRST",
            },
        )

        self.assertEqual(first["fim"], str(first_end))

        overlapping = self.req(
            "POST",
            f"/contratos/{self.cid}/beneficiarios",
            {
                "paciente_id": self.patient,
                "inicio": str(first_end),
                "fim": str(first_end + timedelta(days=5)),
                "identificador_beneficiario": "BEN-OVERLAP",
            },
        )

        self.assertEqual(overlapping.status_code, 409, overlapping.text)
        self.assertEqual(
            overlapping.json()["detail"]["code"],
            "BENEFICIARY_PERIOD_OVERLAP",
        )

        reentry_start = first_end + timedelta(days=1)

        reentry = self.ok(
            "POST",
            f"/contratos/{self.cid}/beneficiarios",
            {
                "paciente_id": self.patient,
                "inicio": str(reentry_start),
                "fim": None,
                "identificador_beneficiario": "BEN-REENTRY",
            },
        )

        self.assertEqual(reentry["inicio"], str(reentry_start))
        self.assertIsNone(reentry["fim"])

        rows = self.ok(
            "GET",
            f"/contratos/{self.cid}/beneficiarios",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row["identificador_beneficiario"] for row in rows},
            {"BEN-FIRST", "BEN-REENTRY"},
        )

    def test_beneficiary_close_rules(self):
        # 1. Não pode encerrar antes do início da cobertura.
        open_link = self.ok(
            "POST",
            f"/contratos/{self.cid}/beneficiarios",
            {
                "paciente_id": self.patient,
                "inicio": str(self.today),
                "fim": None,
                "identificador_beneficiario": "BEN-CLOSE-RULES",
            },
        )

        invalid = self.req(
            "POST",
            f"/beneficiarios/{open_link['id']}/encerrar",
            {
                "fim": str(self.today - timedelta(days=1)),
            },
        )

        self.assertEqual(invalid.status_code, 422, invalid.text)
        self.assertEqual(
            invalid.json()["detail"]["code"],
            "INVALID_PERIOD",
        )

        # 2. Encerramento válido.
        close_date = self.today + timedelta(days=10)

        closed = self.ok(
            "POST",
            f"/beneficiarios/{open_link['id']}/encerrar",
            {
                "fim": str(close_date),
            },
        )

        self.assertEqual(closed["fim"], str(close_date))

        # 3. Cobertura já encerrada não pode ser encerrada novamente.
        already_closed = self.req(
            "POST",
            f"/beneficiarios/{open_link['id']}/encerrar",
            {
                "fim": str(close_date + timedelta(days=1)),
            },
        )

        self.assertEqual(already_closed.status_code, 409, already_closed.text)
        self.assertEqual(
            already_closed.json()["detail"]["code"],
            "BENEFICIARY_ALREADY_CLOSED",
        )

        # 4. Contrato finito: encerramento não pode ultrapassar sua vigência.
        contract_end = self.today + timedelta(days=30)

        finite_contract = self.ok(
            "POST",
            "/contratos/",
            self.contract_payload(
                codigo="AE3-CLOSE-FINITE",
                edicao=11,
                fim=str(contract_end),
            ),
        )

        finite_link = self.ok(
            "POST",
            f"/contratos/{finite_contract['id']}/beneficiarios",
            {
                "paciente_id": self.patient,
                "inicio": str(self.today),
                "fim": str(contract_end),
                "identificador_beneficiario": "BEN-FINITE",
            },
        )

        # Para exercitar close_beneficiary, reabre apenas o registro
        # dentro da transação de teste; a API não possui operação de reabertura.
        self.db.execute(
            text(
                "UPDATE paciente_contratos "
                "SET fim = NULL "
                "WHERE id = :id"
            ),
            {"id": finite_link["id"]},
        )
        self.db.flush()

        beyond_contract = self.req(
            "POST",
            f"/beneficiarios/{finite_link['id']}/encerrar",
            {
                "fim": str(contract_end + timedelta(days=1)),
            },
        )

        self.assertEqual(
            beyond_contract.status_code,
            422,
            beyond_contract.text,
        )
        self.assertEqual(
            beyond_contract.json()["detail"]["code"],
            "BENEFICIARY_OUTSIDE_CONTRACT_PERIOD",
        )

    def test_beneficiary_requires_active_patient_and_payer_link(self):
        # 1. Paciente inativo não é candidato nem pode ser beneficiário.
        self.db.execute(
            text(
                "UPDATE pacientes "
                "SET ativo = false "
                "WHERE id = :p"
            ),
            {"p": self.patient},
        )
        self.db.flush()

        candidates = self.ok(
            "GET",
            f"/contratos/{self.cid}/beneficiarios/candidatos",
        )
        self.assertEqual(candidates, [])

        inactive = self.req(
            "POST",
            f"/contratos/{self.cid}/beneficiarios",
            {
                "paciente_id": self.patient,
                "inicio": str(self.today),
                "fim": None,
            },
        )
        self.assertEqual(inactive.status_code, 422, inactive.text)
        self.assertEqual(
            inactive.json()["detail"]["code"],
            "INVALID_BENEFICIARY",
        )

        # 2. Paciente ativo, mas sem vínculo ativo com o pagador.
        self.db.execute(
            text(
                "UPDATE pacientes "
                "SET ativo = true "
                "WHERE id = :p"
            ),
            {"p": self.patient},
        )
        self.db.execute(
            text(
                "UPDATE paciente_instituicoes "
                "SET ativo = false "
                "WHERE paciente_id = :p "
                "AND instituicao_id = :i"
            ),
            {
                "p": self.patient,
                "i": self.owner,
            },
        )
        self.db.flush()

        candidates = self.ok(
            "GET",
            f"/contratos/{self.cid}/beneficiarios/candidatos",
        )
        self.assertEqual(candidates, [])

        wrong_payer = self.req(
            "POST",
            f"/contratos/{self.cid}/beneficiarios",
            {
                "paciente_id": self.patient,
                "inicio": str(self.today),
                "fim": None,
            },
        )
        self.assertEqual(wrong_payer.status_code, 422, wrong_payer.text)
        self.assertEqual(
            wrong_payer.json()["detail"]["code"],
            "BENEFICIARY_PAYER_MISMATCH",
        )

        # 3. Restaurado o vínculo ativo com o pagador, volta a ser elegível.
        self.db.execute(
            text(
                "UPDATE paciente_instituicoes "
                "SET ativo = true "
                "WHERE paciente_id = :p "
                "AND instituicao_id = :i"
            ),
            {
                "p": self.patient,
                "i": self.owner,
            },
        )
        self.db.flush()

        candidates = self.ok(
            "GET",
            f"/contratos/{self.cid}/beneficiarios/candidatos",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["paciente_id"],
            self.patient,
        )

    def test_contract_payer_table_and_unique_edition_rules(self):
        # 1. A tabela escolhida deve pertencer à instituição pagadora.
        mismatch = self.req(
            "POST",
            "/contratos/",
            {
                "pagador_instituicao_id": self.other,
                "codigo": "AE3-PAYER-MISMATCH",
                "edicao": 1,
                "tabela_preco_id": self.tid,
                "inicio": str(self.today),
                "fim": None,
            },
        )

        self.assertEqual(mismatch.status_code, 422, mismatch.text)
        self.assertEqual(
            mismatch.json()["detail"]["code"],
            "PAYER_TABLE_MISMATCH",
        )

        # 2. Criação válida com pagador e tabela compatíveis.
        first = self.ok(
            "POST",
            "/contratos/",
            self.contract_payload(
                codigo="AE3-UNIQUE",
                edicao=20,
            ),
        )

        self.assertEqual(first["pagador_instituicao_id"], self.owner)
        self.assertEqual(first["tabela_preco_id"], self.tid)

        # 3. Mesmo pagador + código + edição não pode ser repetido.
        duplicate = self.req(
            "POST",
            "/contratos/",
            self.contract_payload(
                codigo="AE3-UNIQUE",
                edicao=20,
            ),
        )

        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(
            duplicate.json()["detail"]["code"],
            "CONTRACT_EDITION_EXISTS",
        )

    def test_all_routes_admin_only(self):
        routes = [
            ("GET", "/contratos/", None),
            ("POST", "/contratos/", self.contract_payload()),
            ("GET", f"/contratos/{self.cid}", None),
            (
                "PUT",
                f"/contratos/{self.cid}",
                self.contract_payload(edicao=1, codigo="C"),
            ),
            ("POST", f"/contratos/{self.cid}/publicar", None),
            (
                "GET",
                f"/contratos/{self.cid}/beneficiarios/candidatos",
                None,
            ),
            (
                "GET",
                f"/contratos/{self.cid}/beneficiarios",
                None,
            ),
            (
                "POST",
                f"/contratos/{self.cid}/beneficiarios",
                {
                    "paciente_id": self.patient,
                    "inicio": str(self.today),
                    "fim": None,
                },
            ),
            (
                "POST",
                "/beneficiarios/999999/encerrar",
                {"fim": str(self.today)},
            ),
        ]

        for role in (
            "ADMIN_CLINICA",
            "PROFISSIONAL",
            "SUPORTE",
            "GESTOR",
            None,
        ):
            for method, path, body in routes:
                response = self.req(
                    method,
                    path,
                    body,
                    role=role,
                )
                self.assertEqual(
                    response.status_code,
                    401 if role is None else 403,
                    (role, method, path, response.text),
                )

        self.assertEqual(
            self.req(
                "GET",
                "/contratos/",
                role=None,
                token="invalid",
            ).status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
