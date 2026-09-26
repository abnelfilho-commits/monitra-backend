"""F1.2.D HTTP boundary for institutional financial preview."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI

from app.core.deps import get_usuario_atual
from app.database import get_db
from app.routers import financeiro_institucional as api
from app.services.autorizacao_institucional import AutorizacaoInstitucionalErro
from test_whatsapp_security import LocalClient


class InstitutionalFinancialHttpTests(unittest.TestCase):
    def setUp(self):
        self.db = object()
        self.user = SimpleNamespace(id=7)

        self.app = FastAPI()
        self.app.include_router(api.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[get_usuario_atual] = lambda: self.user

        self.client = LocalClient(self.app)

        self.payload = {
            "instituicao_id": 11,
            "contrato_id": 22,
            "modulo_id": 1,
            "data_inicio": "2030-01-01",
            "data_fim": "2030-12-31",
        }

    def post(self, payload=None):
        body = self.payload if payload is None else payload
        return self.client.request(
            "POST",
            "/financeiro/institucional/preview",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
            None,
        )

    def test_authorized_request_uses_explicit_institution_and_projection(self):
        result = {
            "instituicao_id": 11,
            "contrato_id": 22,
            "modulo_id": 1,
            "data_inicio": "2030-01-01",
            "data_fim": "2030-12-31",
            "moeda": "BRL",
            "resumo": {
                "quantidade_considerada": 0,
                "quantidade_precificada": 0,
                "quantidade_pendente": 0,
                "subtotal_precificado": None,
                "pacientes_economicos": 0,
                "pacientes_com_sessoes": 0,
                "pacientes_com_itens_precificados": 0,
                "pacientes_somente_pendentes": 0,
                "pacientes_sem_sessoes": 0,
                "sessoes_mapeadas": 0,
                "cobertura_percentual": None,
                "completude": "SEM_SESSOES",
            },
            "pacientes": [],
            "totais_por_mes": [],
            "totais_por_servico": [],
            "pendencias": [],
            "detalhes": [],
        }

        with (
            patch.object(api.authorization, "authorize") as authorize,
            patch.object(api.projection, "run", return_value=result) as run,
        ):
            response = self.post()

        self.assertEqual(response.status_code, 200, response.text)
        authorize.assert_called_once_with(self.db, 7, 11)

        args = run.call_args.args
        self.assertIs(args[0], api.engine)
        self.assertEqual(args[1].instituicao_id, 11)
        self.assertEqual(args[1].contrato_id, 22)
        self.assertEqual(args[1].modulo_id, 1)
        self.assertEqual(str(args[1].data_inicio), "2030-01-01")
        self.assertEqual(str(args[1].data_fim), "2030-12-31")

    def test_denied_access_does_not_call_projection(self):
        with (
            patch.object(
                api.authorization,
                "authorize",
                side_effect=AutorizacaoInstitucionalErro(
                    "INSTITUTIONAL_ACCESS_DENIED"
                ),
            ),
            patch.object(api.projection, "run") as run,
        ):
            response = self.post()

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(
            response.json()["detail"],
            {"code": "INSTITUTIONAL_ACCESS_DENIED"},
        )
        run.assert_not_called()

    def test_projection_value_error_becomes_422(self):
        with (
            patch.object(api.authorization, "authorize"),
            patch.object(
                api.projection,
                "run",
                side_effect=ValueError("invalid economic context"),
            ),
        ):
            response = self.post()

        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "INVALID_INSTITUTIONAL_PREVIEW",
        )

    def test_payload_requires_explicit_contract(self):
        payload = dict(self.payload)
        payload.pop("contrato_id")

        with (
            patch.object(api.authorization, "authorize") as authorize,
            patch.object(api.projection, "run") as run,
        ):
            response = self.post(payload)

        self.assertEqual(response.status_code, 422, response.text)
        authorize.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
