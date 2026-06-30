from fastapi import HTTPException
from sqlalchemy import text

from app.services.longitudinal.adapters.base import LongitudinalAdapter


class IntervencaoAdapter(LongitudinalAdapter):

    def build_response(self, db, evento_id):

        intervencao = db.execute(text("""
            SELECT
                i.id,
                i.tipo,
                i.descricao,
                i.data_intervencao,

                p.nome AS paciente,

                COALESCE(prof.nome, u.nome) AS profissional

            FROM intervencoes i

            LEFT JOIN pacientes p
              ON p.id = i.paciente_id

            LEFT JOIN usuarios u
              ON u.id = i.profissional_id

            LEFT JOIN profissionais prof
              ON prof.id = u.profissional_id

            WHERE i.id = :id
        """), {
            "id": evento_id
        }).fetchone()

        if not intervencao:
            raise HTTPException(
                status_code=404,
                detail="Intervenção não encontrada."
            )

        cards = [
            {
                "titulo": "Tipo",
                "valor": intervencao.tipo,
                "label": intervencao.tipo
            },
            {
                "titulo": "Profissional",
                "valor": intervencao.profissional,
                "label": intervencao.profissional or "-"
            },
        ]

        conteudo = [
            {
                "campo": "descricao",
                "titulo": "Descrição da intervenção",
                "tipo": "textarea",
                "valor": intervencao.descricao,
                "label": intervencao.descricao or "-"
            }
        ]

        return self.response(
            tipo="INTERVENCAO",
            titulo="Intervenção",
            subtitulo=intervencao.paciente,
            data=(
                str(intervencao.data_intervencao.date())
                if intervencao.data_intervencao
                else None
            ),
            profissional=intervencao.profissional,
            origem="PROFISSIONAL",
            cards=cards,
            conteudo=conteudo,
            interpretacao=None,
            conduta=None
        )