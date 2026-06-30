from fastapi import HTTPException
from sqlalchemy import text

from app.services.longitudinal.adapters.base import LongitudinalAdapter


class MChatAdapter(LongitudinalAdapter):

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
              AND UPPER(ac.instrumento) = 'MCHAT'
        """), {
            "id": evento_id
        }).fetchone()

        if not avaliacao:
            raise HTTPException(
                status_code=404,
                detail="Avaliação M-CHAT não encontrada."
            )

        cards = [
            {"titulo": "Score", "valor": avaliacao.score_texto or avaliacao.score},
            {"titulo": "Classificação", "valor": avaliacao.classificacao},
            {"titulo": "Versão", "valor": avaliacao.versao},
        ]

        resultado = avaliacao.resultado or {}

        dominios = resultado.get("dominios") or {}
        alertas = resultado.get("alertas") or []

        conteudo = []

        if dominios.get("total_itens_risco") is not None:
            conteudo.append({
                "campo": "total_itens_risco",
                "titulo": "Total de itens de risco",
                "tipo": "number",
                "valor": dominios.get("total_itens_risco"),
                "label": dominios.get("total_itens_risco")
            })

        if dominios.get("items_risco") or dominios.get("itens_risco"):
            itens = dominios.get("items_risco") or dominios.get("itens_risco")
            conteudo.append({
                "campo": "itens_risco",
                "titulo": "Itens de risco identificados",
                "tipo": "text",
                "valor": ", ".join([str(i) for i in itens]),
                "label": ", ".join([str(i) for i in itens])
            })

        for idx, alerta in enumerate(alertas):
            conteudo.append({
                "campo": f"alerta_{idx+1}",
                "titulo": "Alerta clínico",
                "tipo": "text",
                "valor": alerta,
                "label": alerta
            })

        return self.response(
            tipo="MCHAT",
            titulo="M-CHAT",
            subtitulo=avaliacao.paciente,
            data=str(avaliacao.executado_em.date()) if avaliacao.executado_em else None,
            profissional=avaliacao.profissional,
            origem="PROFISSIONAL",
            cards=cards,
            conteudo=conteudo,
            interpretacao=avaliacao.interpretacao,
            conduta=avaliacao.conduta
        )