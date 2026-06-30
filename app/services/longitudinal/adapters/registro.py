from fastapi import HTTPException
from sqlalchemy import text

from app.services.longitudinal.adapters.base import LongitudinalAdapter

from app.services.longitudinal.value_formatter import formatar_valor_clinico

class RegistroAdapter(LongitudinalAdapter):

    def build_response(self, db, evento_id):

        #
        # Cabeçalho do registro
        #
        registro = db.execute(text("""
            SELECT
                rl.id,
                rl.data_registro,
                rl.origem,
                rl.leitura_clinica,
                rl.protocolo,

                p.nome AS paciente,

                COALESCE(prof.nome, u.nome) AS profissional

            FROM registros_longitudinais rl

            JOIN pacientes p
            ON p.id = rl.paciente_id

            LEFT JOIN usuarios u
            ON u.id = rl.criado_por_usuario_id

            LEFT JOIN profissionais prof
            ON prof.id = u.profissional_id

            WHERE rl.id = :id

        """), {
            "id": evento_id
        }).fetchone()

        if not registro:
            raise HTTPException(
                status_code=404,
                detail="Registro longitudinal não encontrado."
            )

        #
        # Todas as respostas do formulário
        #
        respostas = db.execute(text("""
            SELECT

                cf.nome_campo,
                cf.label,
                cf.tipo_campo,
                cf.ordem,
                cf.opcoes,

                rr.valor_texto,
                rr.valor_numero,
                rr.valor_booleano,
                rr.valor_data,
                rr.valor_hora

            FROM respostas_registro rr

            JOIN campos_formulario cf
                ON cf.id = rr.campo_id

            WHERE rr.registro_id = :registro_id

            ORDER BY cf.ordem

        """), {
            "registro_id": evento_id
        }).fetchall()

        cards = []
        conteudo = []

        #
        # Campos que aparecem em destaque no topo
        #
        campos_resumo = {
            "sono_qualidade",
            "evacuacao",
            "consistencia_fezes",
            "irritabilidade",
            "crise_sensorial",
            "tempo_tela",
            "seletividade_alimentar"
        }

        for r in respostas:

            valor = None

            if r.valor_texto is not None:
                valor = r.valor_texto

            elif r.valor_numero is not None:
                valor = float(r.valor_numero)

            elif r.valor_booleano is not None:
                valor = "Sim" if r.valor_booleano else "Não"

            elif r.valor_data is not None:
                valor = str(r.valor_data)

            elif r.valor_hora is not None:
                valor = str(r.valor_hora)
            
            label = formatar_valor_clinico(
                r.nome_campo,
                valor,
                r.opcoes
            )

            item = {
                "campo": r.nome_campo,
                "titulo": r.label,
                "tipo": r.tipo_campo,
                "valor": valor,
                "label": label
            }

            conteudo.append(item)

            if r.nome_campo in campos_resumo:
                cards.append({
                    "titulo": r.label,
                    "valor": valor,
                    "label": label
                })

        return self.response(

            tipo="REGISTRO",

            titulo="Registro Diário",

            subtitulo=registro.paciente,

            data=str(registro.data_registro),

            profissional=registro.profissional,

            origem=registro.origem,

            cards=cards,

            conteudo=conteudo,

            interpretacao=registro.leitura_clinica,

            conduta=registro.protocolo
        )