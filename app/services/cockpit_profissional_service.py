from datetime import datetime, time, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.models.usuario import Usuario

from app.services.risk_analytics import analisar_risco_paciente

class CockpitProfissionalService:
    """
    Serviço de leitura otimizada do Cockpit Assistencial.

    Consolida informações necessárias ao Cockpit do profissional
    sem alterar as regras clínicas e assistenciais existentes.
    """

    @staticmethod
    def _iso_timestamp_utc(valor):
        if valor is None:
            return None

        if not isinstance(valor, datetime):
            valor = datetime.combine(valor, time.min)

        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)

        return valor.astimezone(timezone.utc).isoformat()

    @staticmethod
    def obter_pacientes_clinica(
        db: Session,
        usuario: Usuario,
    ):
        if not usuario.clinica_id:
            return []

        return (
            db.query(Paciente)
            .filter(
                Paciente.ativo == True,
                Paciente.clinica_id == usuario.clinica_id,
            )
            .order_by(Paciente.nome.asc())
            .all()
        )

    @staticmethod
    def obter_prioridades(
        db: Session,
        usuario: Usuario,
        limit: int = 5,
    ):
        """
        Calcula as prioridades clínicas necessárias ao Cockpit
        reutilizando integralmente o Clinical Engine atual.

        Não cria regra clínica própria.
        """

        pacientes = (
            CockpitProfissionalService.obter_pacientes_clinica(
                db=db,
                usuario=usuario,
            )
        )

        analises = []

        for paciente in pacientes:
            analise = analisar_risco_paciente(
                db=db,
                paciente=paciente,
            )

            if analise.get("risco_atual") in (
                "alto_risco",
                "atencao",
            ):
                analises.append(analise)

        analises.sort(
            key=lambda item: (
                item.get("pontuacao_risco") or 0,
                item.get("total_registros") or 0,
            ),
            reverse=True,
        )

        return {
            "total_pacientes": len(pacientes),
            "pacientes_prioritarios": analises[:limit],
        }

    @staticmethod
    def obter_atividades_recentes(
        db: Session,
        usuario: Usuario,
        limit: int = 5,
    ):
        """
        Retorna atividades recentes da clínica do profissional
        sem carregar a Timeline completa de cada paciente.

        Cada fonte entrega apenas candidatos recentes.
        Depois os eventos são consolidados, ordenados e limitados.
        """

        if not usuario.clinica_id:
            return []

        limite_candidatos = max(limit * 3, 15)

        eventos = []

        # ---------------------------------------------------------
        # REGISTROS DIÁRIOS
        # ---------------------------------------------------------
        registros = db.execute(
            text(
                """
                SELECT
                    rl.id,
                    rl.paciente_id,
                    p.nome AS paciente_nome,
                    rl.criado_em,
                    rl.data_registro,
                    rl.origem,

                    MAX(
                        CASE
                            WHEN cf.nome_campo = 'observacao'
                            THEN rr.valor_texto
                        END
                    ) AS observacao

                FROM registros_longitudinais rl

                JOIN pacientes p
                    ON p.id = rl.paciente_id

                LEFT JOIN respostas_registro rr
                    ON rr.registro_id = rl.id

                LEFT JOIN campos_formulario cf
                    ON cf.id = rr.campo_id

                WHERE p.clinica_id = :clinica_id
                  AND p.ativo = TRUE
                  AND rl.modulo_id = 1

                GROUP BY
                    rl.id,
                    rl.paciente_id,
                    p.nome,
                    rl.criado_em,
                    rl.data_registro,
                    rl.origem

                ORDER BY
                    rl.criado_em DESC,
                    rl.id DESC

                LIMIT :limite
                """
            ),
            {
                "clinica_id": usuario.clinica_id,
                "limite": limite_candidatos,
            },
        ).fetchall()

        for registro in registros:
            eventos.append(
                {
                    "id": registro.id,
                    "paciente_id": registro.paciente_id,
                    "paciente_nome": registro.paciente_nome,
                    "tipo_evento": "REGISTRO_DIARIO",
                    "tipo": "REGISTRO_DIARIO",
                    "data": CockpitProfissionalService._iso_timestamp_utc(
                        registro.criado_em
                        or registro.data_registro
                    ),
                    "descricao": registro.observacao,
                    "origem": registro.origem or "PROFISSIONAL",
                }
            )

        # ---------------------------------------------------------
        # INTERVENÇÕES
        # ---------------------------------------------------------
        intervencoes = db.execute(
            text(
                """
                SELECT
                    i.id,
                    i.paciente_id,
                    p.nome AS paciente_nome,
                    i.created_at,
                    i.data_intervencao,
                    i.descricao

                FROM intervencoes i

                JOIN pacientes p
                    ON p.id = i.paciente_id

                WHERE p.clinica_id = :clinica_id
                  AND p.ativo = TRUE

                ORDER BY
                    i.created_at DESC,
                    i.id DESC

                LIMIT :limite
                """
            ),
            {
                "clinica_id": usuario.clinica_id,
                "limite": limite_candidatos,
            },
        ).fetchall()

        for intervencao in intervencoes:
            eventos.append(
                {
                    "id": intervencao.id,
                    "paciente_id": intervencao.paciente_id,
                    "paciente_nome": intervencao.paciente_nome,
                    "tipo_evento": "INTERVENCAO",
                    "tipo": "INTERVENCAO",
                    "data": CockpitProfissionalService._iso_timestamp_utc(
                        intervencao.created_at
                        or intervencao.data_intervencao
                    ),
                    "descricao": intervencao.descricao,
                    "origem": "PROFISSIONAL",
                }
            )

        # ---------------------------------------------------------
        # AVALIAÇÕES CLÍNICAS
        # ---------------------------------------------------------
        avaliacoes = db.execute(
            text(
                """
                SELECT
                    ac.id,
                    rl.paciente_id,
                    p.nome AS paciente_nome,
                    ac.instrumento,
                    ac.score,
                    ac.classificacao,
                    ac.created_at

                FROM avaliacoes_clinicas ac

                JOIN registros_longitudinais rl
                    ON rl.id = ac.registro_id

                JOIN pacientes p
                    ON p.id = rl.paciente_id

                WHERE p.clinica_id = :clinica_id
                  AND p.ativo = TRUE

                ORDER BY
                    ac.created_at DESC,
                    ac.id DESC

                LIMIT :limite
                """
            ),
            {
                "clinica_id": usuario.clinica_id,
                "limite": limite_candidatos,
            },
        ).fetchall()

        for avaliacao in avaliacoes:
            eventos.append(
                {
                    "id": avaliacao.id,
                    "paciente_id": avaliacao.paciente_id,
                    "paciente_nome": avaliacao.paciente_nome,
                    "tipo_evento": "AVALIACAO_CLINICA",
                    "tipo": "AVALIACAO_CLINICA",
                    "data": CockpitProfissionalService._iso_timestamp_utc(
                        avaliacao.created_at
                    ),
                    "descricao": (
                        f"Aplicação do {avaliacao.instrumento}. "
                        f"Score {avaliacao.score}. "
                        f"Classificação: {avaliacao.classificacao}."
                    ),
                    "origem": "FRAMEWORK",
                }
            )

        # ---------------------------------------------------------
        # SESSÕES REALIZADAS
        # ---------------------------------------------------------
        sessoes = db.execute(
            text(
                """
                SELECT
                    sa.id,
                    sa.paciente_id,
                    p.nome AS paciente_nome,
                    sa.numero_sessao,
                    sa.data_realizacao,
                    sa.data_agendada,
                    sa.hora_fim_real,
                    at.nome AS atividade_nome

                FROM sessoes_assistenciais sa

                JOIN pacientes p
                    ON p.id = sa.paciente_id

                JOIN agenda_cuidados agenda
                    ON agenda.id = sa.agenda_cuidado_id

                JOIN atividades_terapeuticas at
                    ON at.id = agenda.atividade_id

                WHERE p.clinica_id = :clinica_id
                  AND p.ativo = TRUE
                  AND sa.status = 'REALIZADA'

                ORDER BY
                    sa.data_realizacao DESC,
                    sa.numero_sessao DESC

                LIMIT :limite
                """
            ),
            {
                "clinica_id": usuario.clinica_id,
                "limite": limite_candidatos,
            },
        ).fetchall()

        for sessao in sessoes:
            data_base = (
                sessao.data_realizacao
                or sessao.data_agendada
            )

            if data_base:
                data_evento = datetime.combine(
                    data_base,
                    sessao.hora_fim_real or time.min,
                )
            else:
                data_evento = None

            eventos.append(
                {
                    "id": sessao.id,
                    "paciente_id": sessao.paciente_id,
                    "paciente_nome": sessao.paciente_nome,
                    "tipo_evento": "SESSAO_REALIZADA",
                    "tipo": "SESSAO_REALIZADA",
                    "data": CockpitProfissionalService._iso_timestamp_utc(
                        data_evento
                    ),
                    "descricao": (
                        f"Sessão {sessao.numero_sessao} de "
                        f"{sessao.atividade_nome} realizada."
                    ),
                    "origem": "ASSISTENCIAL",
                }
            )

        # ---------------------------------------------------------
        # DIAGNÓSTICOS
        # ---------------------------------------------------------
        diagnosticos = db.execute(
            text(
                """
                SELECT
                    d.id,
                    d.paciente_id,
                    p.nome AS paciente_nome,
                    d.data_diagnostico,
                    d.cid,
                    d.descricao_clinica

                FROM diagnosticos d

                JOIN pacientes p
                    ON p.id = d.paciente_id

                WHERE p.clinica_id = :clinica_id
                  AND p.ativo = TRUE
                  AND d.status != 'CANCELADO'

                ORDER BY
                    d.data_diagnostico DESC,
                    d.id DESC

                LIMIT :limite
                """
            ),
            {
                "clinica_id": usuario.clinica_id,
                "limite": limite_candidatos,
            },
        ).fetchall()

        for diagnostico in diagnosticos:
            data_evento = (
                datetime.combine(
                    diagnostico.data_diagnostico,
                    time.min,
                )
                if diagnostico.data_diagnostico
                else None
            )

            eventos.append(
                {
                    "id": diagnostico.id,
                    "paciente_id": diagnostico.paciente_id,
                    "paciente_nome": diagnostico.paciente_nome,
                    "tipo_evento": "DIAGNOSTICO",
                    "tipo": "DIAGNOSTICO",
                    "data": CockpitProfissionalService._iso_timestamp_utc(
                        data_evento
                    ),
                    "descricao": (
                        f"{diagnostico.cid or ''} "
                        f"{diagnostico.descricao_clinica or ''}"
                    ).strip(),
                    "origem": "ASSISTENCIAL",
                }
            )

        eventos = [
            evento
            for evento in eventos
            if evento.get("data")
        ]

        eventos.sort(
            key=lambda evento: evento["data"],
            reverse=True,
        )

        # Mantém a regra atual do Cockpit:
        # apenas o evento mais recente de cada paciente.
        pacientes_exibidos = set()
        resultado = []

        for evento in eventos:
            paciente_id = evento.get("paciente_id")

            if paciente_id in pacientes_exibidos:
                continue

            pacientes_exibidos.add(paciente_id)
            resultado.append(evento)

            if len(resultado) >= limit:
                break

        return resultado