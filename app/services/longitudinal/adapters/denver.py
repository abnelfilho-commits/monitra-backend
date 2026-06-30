from fastapi import HTTPException
from sqlalchemy import text

from app.services.longitudinal.adapters.base import LongitudinalAdapter


class DenverAdapter(LongitudinalAdapter):

    def build_response(self, db, evento_id):

        avaliacao = db.execute(text("""
            SELECT
                ac.id,
                ac.registro_id,
                ac.instrumento,
                ac.versao,
                ac.score,
                ac.score_texto,
                ac.classificacao,
                ac.conduta,
                ac.interpretacao,
                ac.executado_em,
                ac.resultado,

                p.nome AS paciente,

                COALESCE(prof.nome, u.nome) AS profissional

            FROM avaliacoes_clinicas ac

            JOIN pacientes p
              ON p.id = ac.paciente_id

            LEFT JOIN usuarios u
              ON u.id = ac.profissional_id

            LEFT JOIN profissionais prof
              ON prof.id = u.profissional_id

            WHERE ac.id = :id
              AND UPPER(ac.instrumento) IN ('DENVER', 'DENVERII', 'DENVER_II')
        """), {
            "id": evento_id
        }).fetchone()

        if not avaliacao:
            raise HTTPException(
                status_code=404,
                detail="Avaliação Denver II não encontrada."
            )

        cards = [
            {"titulo": "Score", "valor": avaliacao.score_texto or avaliacao.score},
            {"titulo": "Classificação", "valor": avaliacao.classificacao},
            {"titulo": "Versão", "valor": avaliacao.versao},
        ]

        resultado = avaliacao.resultado or {}

        conteudo = []

        dominios = resultado.get("dominios", {})

        for chave, dominio in dominios.items():

            conteudo.append({
                "campo": chave,
                "titulo": dominio.get("dominio"),
                "tipo": "text",
                "valor": (
                    f"Passou: {dominio.get('passou',0)} | "
                    f"Falhou: {dominio.get('falhou',0)} | "
                    f"Recusou: {dominio.get('recusou',0)} | "
                    f"Não observado: {dominio.get('nao_observado',0)}"
                ),
                "label": (
                    f"Passou: {dominio.get('passou',0)} | "
                    f"Falhou: {dominio.get('falhou',0)} | "
                    f"Recusou: {dominio.get('recusou',0)} | "
                    f"Não observado: {dominio.get('nao_observado',0)}"
                )
            })

        return self.response(
            tipo="DENVER",
            titulo="Denver II",
            subtitulo=avaliacao.paciente,
            data=str(avaliacao.executado_em.date()) if avaliacao.executado_em else None,
            profissional=avaliacao.profissional,
            origem="PROFISSIONAL",
            cards=cards,
            conteudo=conteudo,
            interpretacao=avaliacao.interpretacao,
            conduta=avaliacao.conduta
        )