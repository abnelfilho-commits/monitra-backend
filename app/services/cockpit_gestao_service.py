from typing import Optional
from datetime import datetime, time, timezone, date, timedelta 
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.acl import is_admin_global
from app.models.paciente import Paciente
from app.models.usuario import Usuario
from app.models.intervencao import Intervencao
from app.services.risk_analytics import analisar_risco_paciente

class CockpitGestaoService:
    """
    Serviço de leitura agregada do Dashboard de Gestão.

    Preserva a abrangência atual:
    - ADMIN: visão global
    - ADMIN_CLINICA: somente a clínica vinculada

    Não redefine regras clínicas.
    """

    @staticmethod
    def obter_estrutura_operacao(
        db: Session,
        usuario: Usuario,
        analises_clinicas=None,
        continuidade_longitudinal=None,
        periodo_dias: int = 30,
    ):
        from collections import defaultdict
        from datetime import date, timedelta
        from sqlalchemy import text

        # A Estrutura da Operação V1 é uma visão comparativa
        # exclusiva do ADMIN global.
        if not is_admin_global(usuario):
            return None

        # ---------------------------------------------------------
        # 1. Reutiliza as fontes já calculadas quando disponíveis
        # ---------------------------------------------------------

        if analises_clinicas is None:
            analises_clinicas = (
                CockpitGestaoService.obter_analises_clinicas(
                    db=db,
                    usuario=usuario,
                )
            )

        if continuidade_longitudinal is None:
            continuidade_longitudinal = (
                CockpitGestaoService.obter_continuidade_longitudinal(
                    db=db,
                    usuario=usuario,
                )
            )

        atencao_necessaria = (
            CockpitGestaoService.obter_atencao_necessaria(
                db=db,
                usuario=usuario,
                analises_clinicas=analises_clinicas,
                continuidade_longitudinal=continuidade_longitudinal,
            )
        )

        # ---------------------------------------------------------
        # 2. Período do acompanhamento ativo
        # ---------------------------------------------------------

        data_fim = date.today()
        data_inicio = data_fim - timedelta(days=periodo_dias - 1)

        # ---------------------------------------------------------
        # 3. Mapa Paciente -> Clínica
        # ---------------------------------------------------------

        pacientes_rows = db.execute(
            text("""
                SELECT
                    p.id AS paciente_id,
                    p.clinica_id
                FROM pacientes p
                WHERE p.ativo = TRUE
            """)
        ).mappings().all()

        clinica_por_paciente = {
            row["paciente_id"]: row["clinica_id"]
            for row in pacientes_rows
        }

        # ---------------------------------------------------------
        # 4. Pessoas em acompanhamento ativo
        #
        # Mesma regra já validada na E03:
        # - Registro Diário
        # - Sessão REALIZADA
        # - Avaliação CONCLUÍDA
        # - Intervenção
        # dentro dos últimos N dias.
        # ---------------------------------------------------------

        ativos_rows = db.execute(
            text("""
                SELECT DISTINCT paciente_id
                FROM (
                    SELECT rl.paciente_id
                    FROM registros_longitudinais rl
                    JOIN pacientes p
                    ON p.id = rl.paciente_id
                    WHERE p.ativo = TRUE
                    AND rl.data_registro
                        BETWEEN :data_inicio AND :data_fim

                    UNION

                    SELECT sa.paciente_id
                    FROM sessoes_assistenciais sa
                    JOIN pacientes p
                    ON p.id = sa.paciente_id
                    WHERE p.ativo = TRUE
                    AND sa.status = 'REALIZADA'
                    AND sa.data_realizacao
                        BETWEEN :data_inicio AND :data_fim

                    UNION

                    SELECT ac.paciente_id
                    FROM avaliacoes_clinicas ac
                    JOIN pacientes p
                    ON p.id = ac.paciente_id
                    WHERE p.ativo = TRUE
                    AND ac.status = 'CONCLUIDA'
                    AND DATE(ac.executado_em)
                        BETWEEN :data_inicio AND :data_fim

                    UNION

                    SELECT i.paciente_id
                    FROM intervencoes i
                    JOIN pacientes p
                    ON p.id = i.paciente_id
                    WHERE p.ativo = TRUE
                    AND DATE(i.data_intervencao)
                        BETWEEN :data_inicio AND :data_fim
                ) atividade
            """),
            {
                "data_inicio": data_inicio,
                "data_fim": data_fim,
            },
        ).mappings().all()

        pacientes_ativos = {
            row["paciente_id"]
            for row in ativos_rows
        }

        # ---------------------------------------------------------
        # 5. Pessoas em Atenção Necessária
        #
        # O resultado já vem deduplicado pela E04.
        # ---------------------------------------------------------

        pacientes_atencao = {
            item["paciente_id"]
            for item in atencao_necessaria["prioridades"]
        }

        # ---------------------------------------------------------
        # 6. Estrutura básica das unidades
        # ---------------------------------------------------------

        unidades_rows = db.execute(
            text("""
                SELECT
                    c.id AS clinica_id,
                    c.nome AS clinica_nome,

                    (
                        SELECT COUNT(*)
                        FROM pacientes p
                        WHERE p.clinica_id = c.id
                        AND p.ativo = TRUE
                    ) AS pessoas_acompanhadas,

                    (
                        SELECT COUNT(*)
                        FROM profissionais pr
                        WHERE pr.clinica_id = c.id
                        AND pr.ativo = TRUE
                    ) AS profissionais_ativos

                FROM clinicas c
                WHERE c.ativa = TRUE
                ORDER BY c.nome
            """)
        ).mappings().all()

        # ---------------------------------------------------------
        # 7. Agrupamento por clínica
        # ---------------------------------------------------------

        ativos_por_clinica = defaultdict(int)
        atencao_por_clinica = defaultdict(int)

        for paciente_id in pacientes_ativos:
            clinica_id = clinica_por_paciente.get(paciente_id)

            if clinica_id is not None:
                ativos_por_clinica[clinica_id] += 1

        for paciente_id in pacientes_atencao:
            clinica_id = clinica_por_paciente.get(paciente_id)

            if clinica_id is not None:
                atencao_por_clinica[clinica_id] += 1

        # ---------------------------------------------------------
        # 8. Payload final
        # ---------------------------------------------------------

        unidades = []

        for row in unidades_rows:
            clinica_id = row["clinica_id"]

            pessoas_acompanhadas = row["pessoas_acompanhadas"]
            acompanhamento_ativo = ativos_por_clinica[clinica_id]
            atencao = atencao_por_clinica[clinica_id]
            profissionais_ativos = row["profissionais_ativos"]

            cobertura_assistencial = (
                round(
                    (
                        acompanhamento_ativo
                        / pessoas_acompanhadas
                    ) * 100,
                    2,
                )
                if pessoas_acompanhadas > 0
                else 0.0
            )

            unidades.append(
                {
                    "clinica_id": clinica_id,
                    "nome": row["clinica_nome"],
                    "pessoas_acompanhadas": pessoas_acompanhadas,
                    "acompanhamento_ativo": acompanhamento_ativo,
                    "cobertura_assistencial": cobertura_assistencial,
                    "atencao_necessaria": atencao,
                    "profissionais_ativos": profissionais_ativos,
                }
            )

        return {
            "periodo_dias": periodo_dias,
            "unidades": unidades,
        }

    @staticmethod
    def obter_profissionais_ativos(
        db: Session,
        usuario: Usuario,
    ):
        from sqlalchemy import text

        escopo = CockpitGestaoService.resolver_escopo(usuario)

        parametros = {}

        filtro_clinica = ""

        if not escopo["admin_global"]:
            filtro_clinica = """
                AND pr.clinica_id = :clinica_id
            """

            parametros["clinica_id"] = escopo["clinica_id"]

        resultado = db.execute(
            text(
                f"""
                SELECT COUNT(*) AS total
                FROM profissionais pr
                JOIN clinicas c
                ON c.id = pr.clinica_id
                WHERE pr.ativo = TRUE
                AND c.ativa = TRUE
                {filtro_clinica}
                """
            ),
            parametros,
        ).mappings().first()

        return int(resultado["total"] or 0)

    @staticmethod
    def obter_atividade_assistencial(
        db: Session,
        usuario: Usuario,
        periodo_dias: int = 30,
    ):
        from datetime import date, timedelta
        from sqlalchemy import text

        escopo = CockpitGestaoService.resolver_escopo(usuario)

        data_fim = date.today()
        data_inicio = data_fim - timedelta(days=periodo_dias - 1)

        filtro_clinica = ""
        params = {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
        }

        if not escopo["admin_global"]:
            filtro_clinica = "AND p.clinica_id = :clinica_id"
            params["clinica_id"] = escopo["clinica_id"]

        sql = text(f"""
            SELECT tipo, COUNT(*) AS total
            FROM (
                SELECT 'REGISTRO_DIARIO' AS tipo
                FROM registros_longitudinais rl
                JOIN pacientes p
                ON p.id = rl.paciente_id
                WHERE p.ativo = TRUE
                {filtro_clinica}
                AND rl.data_registro BETWEEN :data_inicio AND :data_fim

                UNION ALL

                SELECT 'SESSAO_REALIZADA' AS tipo
                FROM sessoes_assistenciais sa
                JOIN pacientes p
                ON p.id = sa.paciente_id
                WHERE p.ativo = TRUE
                {filtro_clinica}
                AND sa.status = 'REALIZADA'
                AND sa.data_realizacao BETWEEN :data_inicio AND :data_fim

                UNION ALL

                SELECT 'AVALIACAO_CLINICA' AS tipo
                FROM avaliacoes_clinicas ac
                JOIN pacientes p
                ON p.id = ac.paciente_id
                WHERE p.ativo = TRUE
                {filtro_clinica}
                AND ac.status = 'CONCLUIDA'
                AND DATE(ac.executado_em) BETWEEN :data_inicio AND :data_fim

                UNION ALL

                SELECT 'INTERVENCAO' AS tipo
                FROM intervencoes i
                JOIN pacientes p
                ON p.id = i.paciente_id
                WHERE p.ativo = TRUE
                {filtro_clinica}
                AND DATE(i.data_intervencao) BETWEEN :data_inicio AND :data_fim
            ) atividade
            GROUP BY tipo
        """)

        totais = {
            "REGISTRO_DIARIO": 0,
            "SESSAO_REALIZADA": 0,
            "AVALIACAO_CLINICA": 0,
            "INTERVENCAO": 0,
        }

        for row in db.execute(sql, params):
            totais[row.tipo] = row.total

        return {
            "periodo_dias": periodo_dias,
            "data_inicio": data_inicio.isoformat(),
            "data_fim": data_fim.isoformat(),
            "registros_diarios": totais["REGISTRO_DIARIO"],
            "sessoes_realizadas": totais["SESSAO_REALIZADA"],
            "avaliacoes_clinicas": totais["AVALIACAO_CLINICA"],
            "intervencoes": totais["INTERVENCAO"],
        }

    @staticmethod
    def resolver_escopo(
        usuario: Usuario,
        clinica_id: Optional[int] = None
    ):
        """
        Resolve o escopo administrativo do Cockpit de Gestão.

        ADMIN:
            visão global quando clinica_id não for informado;
            pode filtrar uma clínica específica.

        ADMIN_CLINICA:
            permanece obrigatoriamente restrito à clínica
            vinculada ao usuário, independentemente do parâmetro.
        """

        admin_global = is_admin_global(usuario)

        if admin_global:
            return {
                "admin_global": True,
                "clinica_id": clinica_id,
            }

        return {
            "admin_global": False,
            "clinica_id": usuario.clinica_id,
        }

    @staticmethod
    def classificar_continuidade(dias_sem_registro):
        """
        Classifica a continuidade longitudinal com base
        no último Registro Diário.

        None  -> nunca iniciou
        0-3   -> regular
        4-6   -> atenção
        7+    -> crítica
        """

        if dias_sem_registro is None:
            return "NAO_INICIADA"

        if dias_sem_registro >= 7:
            return "CRITICA"

        if dias_sem_registro >= 4:
            return "ATENCAO"

        return "REGULAR"

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
    def obter_eventos_recentes(
        db: Session,
        usuario: Usuario,
        limit: int = 10,
        clinica_id: Optional[int] = None
    ):
        """
        Retorna os eventos clínicos mais recentes do escopo
        do usuário sem carregar Timelines completas.

        ADMIN:
            todos os pacientes ativos.

        ADMIN_CLINICA:
            somente pacientes ativos da clínica vinculada.
        """

        escopo = CockpitGestaoService.resolver_escopo(
            usuario,
            clinica_id=clinica_id,
        )

        filtro_clinica = ""
        parametros = {
            "limite": max(limit * 3, 30),
        }

        if not escopo["admin_global"]:
            if not escopo["clinica_id"]:
                return []

            filtro_clinica = "AND p.clinica_id = :clinica_id"
            parametros["clinica_id"] = escopo["clinica_id"]

        eventos = []

        # ---------------------------------------------------------
        # REGISTROS DIÁRIOS
        # ---------------------------------------------------------
        registros = db.execute(
            text(
                f"""
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

                WHERE p.ativo = TRUE
                  AND rl.modulo_id = 1
                  {filtro_clinica}

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
            parametros,
        ).fetchall()

        for registro in registros:
            eventos.append(
                {
                    "id": registro.id,
                    "paciente_id": registro.paciente_id,
                    "paciente_nome": registro.paciente_nome,
                    "tipo_evento": "REGISTRO_DIARIO",
                    "data": CockpitGestaoService._iso_timestamp_utc(
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
                f"""
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

                WHERE p.ativo = TRUE
                  {filtro_clinica}

                ORDER BY
                    i.created_at DESC,
                    i.id DESC

                LIMIT :limite
                """
            ),
            parametros,
        ).fetchall()

        for intervencao in intervencoes:
            eventos.append(
                {
                    "id": intervencao.id,
                    "paciente_id": intervencao.paciente_id,
                    "paciente_nome": intervencao.paciente_nome,
                    "tipo_evento": "INTERVENCAO",
                    "data": CockpitGestaoService._iso_timestamp_utc(
                        intervencao.created_at
                        or intervencao.data_intervencao
                    ),
                    "descricao": intervencao.descricao,
                    "origem": "PROFISSIONAL",
                }
            )

        # ---------------------------------------------------------
        # AVALIAÇÕES
        # ---------------------------------------------------------
        avaliacoes = db.execute(
            text(
                f"""
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

                WHERE p.ativo = TRUE
                  {filtro_clinica}

                ORDER BY
                    ac.created_at DESC,
                    ac.id DESC

                LIMIT :limite
                """
            ),
            parametros,
        ).fetchall()

        for avaliacao in avaliacoes:
            eventos.append(
                {
                    "id": avaliacao.id,
                    "paciente_id": avaliacao.paciente_id,
                    "paciente_nome": avaliacao.paciente_nome,
                    "tipo_evento": "AVALIACAO_CLINICA",
                    "data": CockpitGestaoService._iso_timestamp_utc(
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
                f"""
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

                WHERE p.ativo = TRUE
                  AND sa.status = 'REALIZADA'
                  {filtro_clinica}

                ORDER BY
                    sa.data_realizacao DESC,
                    sa.numero_sessao DESC

                LIMIT :limite
                """
            ),
            parametros,
        ).fetchall()

        for sessao in sessoes:
            data_base = (
                sessao.data_realizacao
                or sessao.data_agendada
            )

            data_evento = (
                datetime.combine(
                    data_base,
                    sessao.hora_fim_real or time.min,
                )
                if data_base
                else None
            )

            eventos.append(
                {
                    "id": sessao.id,
                    "paciente_id": sessao.paciente_id,
                    "paciente_nome": sessao.paciente_nome,
                    "tipo_evento": "SESSAO_REALIZADA",
                    "data": CockpitGestaoService._iso_timestamp_utc(
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
                f"""
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

                WHERE p.ativo = TRUE
                  AND d.status != 'CANCELADO'
                  {filtro_clinica}

                ORDER BY
                    d.data_diagnostico DESC,
                    d.id DESC

                LIMIT :limite
                """
            ),
            parametros,
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
                    "data": CockpitGestaoService._iso_timestamp_utc(
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

        return eventos[:limit]

    @staticmethod
    def obter_continuidade_longitudinal(
        db: Session,
        usuario: Usuario,
    ):
        """
        Retorna a situação de continuidade longitudinal
        dos pacientes ativos no escopo administrativo.

        A referência é exclusivamente o Registro Diário
        do módulo Neurodesenvolvimento nesta primeira etapa.
        """

        escopo = CockpitGestaoService.resolver_escopo(usuario)

        filtro_clinica = ""
        parametros = {}

        if not escopo["admin_global"]:
            if not escopo["clinica_id"]:
                return {
                    "resumo": {
                        "regular": 0,
                        "atencao": 0,
                        "critica": 0,
                        "nao_iniciada": 0,
                    },
                    "pacientes": [],
                }

            filtro_clinica = "AND p.clinica_id = :clinica_id"
            parametros["clinica_id"] = escopo["clinica_id"]

        rows = db.execute(
            text(
                f"""
                SELECT
                    p.id AS paciente_id,
                    p.nome AS paciente_nome,
                    p.profissional_id,
                    MAX(rl.data_registro) AS ultimo_registro

                FROM pacientes p

                LEFT JOIN registros_longitudinais rl
                    ON rl.paciente_id = p.id
                   AND rl.modulo_id = 1

                WHERE p.ativo = TRUE
                  {filtro_clinica}

                GROUP BY
                    p.id,
                    p.nome,
                    p.profissional_id

                ORDER BY p.nome ASC
                """
            ),
            parametros,
        ).fetchall()

        hoje = date.today()

        pacientes = []

        resumo = {
            "regular": 0,
            "atencao": 0,
            "critica": 0,
            "nao_iniciada": 0,
        }

        for row in rows:
            ultimo_registro = row.ultimo_registro

            if ultimo_registro is None:
                dias_sem_registro = None
            else:
                if isinstance(ultimo_registro, datetime):
                    data_ultimo_registro = ultimo_registro.date()
                else:
                    data_ultimo_registro = ultimo_registro

                dias_sem_registro = max(
                    (hoje - data_ultimo_registro).days,
                    0,
                )

            classificacao = (
                CockpitGestaoService.classificar_continuidade(
                    dias_sem_registro
                )
            )

            resumo[classificacao.lower()] += 1

            pacientes.append(
                {
                    "paciente_id": row.paciente_id,
                    "paciente_nome": row.paciente_nome,
                    "profissional_id": row.profissional_id,
                    "ultimo_registro": (
                        ultimo_registro.isoformat()
                        if ultimo_registro
                        else None
                    ),
                    "dias_sem_registro": dias_sem_registro,
                    "classificacao": classificacao,
                }
            )

        return {
            "resumo": resumo,
            "pacientes": pacientes,
        }

    @staticmethod
    def obter_resumo(
        db: Session,
        usuario: Usuario,
        clinica_id: Optional[int] = None,
        analises_clinicas=None,
    ):
        analises = analises_clinicas

        if analises is None:
            analises = (
                CockpitGestaoService.obter_analises_clinicas(
                    db=db,
                    usuario=usuario,
                    clinica_id=clinica_id,
                )
            )

        contadores = (
            CockpitGestaoService.obter_contadores_por_paciente(
                db=db,
                usuario=usuario,
                clinica_id=clinica_id,
            )
        )

        pacientes = []

        for item in analises:
            paciente = item["paciente"]
            risco = item["risco"]

            contador = contadores.get(
                paciente.id,
                {
                    "total_registros": 0,
                    "total_intervencoes": 0,
                },
            )

            pacientes.append(
                {
                    "id": paciente.id,
                    "nome": paciente.nome,
                    "profissional_id": paciente.profissional_id,
                    "profissional_nome": (
                        paciente.profissional.nome
                        if getattr(paciente, "profissional", None)
                        else None
                    ),
                    "risco": risco,
                    "total_registros": contador["total_registros"],
                    "total_intervencoes": contador["total_intervencoes"],
                }
            )

        total_alto_risco = sum(
            1
            for p in pacientes
            if p["risco"].get("risco_atual") == "alto_risco"
        )

        total_atencao = sum(
            1
            for p in pacientes
            if p["risco"].get("risco_atual") == "atencao"
        )

        total_em_piora = sum(
            1
            for p in pacientes
            if p["risco"].get("tendencia") == "piora"
        )

        total_estaveis = sum(
            1
            for p in pacientes
            if p["risco"].get("tendencia") == "estavel"
        )

        total_sem_dados = sum(
            1
            for p in pacientes
            if p["risco"].get("risco_atual") == "sem_dados"
        )

        total_registros = sum(
            p["total_registros"]
            for p in pacientes
        )

        total_intervencoes = sum(
            p["total_intervencoes"]
            for p in pacientes
        )

        pacientes_criticos = [
            p
            for p in pacientes
            if p["risco"].get("risco_atual")
            in ("alto_risco", "atencao")
        ]

        pacientes_criticos.sort(
            key=lambda p: (
                p["risco"].get("risco_atual") == "alto_risco",
                p["risco"].get("pontuacao_risco") or 0,
                p["risco"].get("tendencia") == "piora",
                p["total_registros"],
            ),
            reverse=True,
        )

        grafico_intervencoes = [
            {
                "paciente_id": p["id"],
                "nome": p["nome"],
                "valor": p["total_intervencoes"],
                "semDados": p["total_intervencoes"] == 0,
            }
            for p in pacientes
        ]

        grafico_registros = [
            {
                "paciente_id": p["id"],
                "nome": p["nome"],
                "valor": p["total_registros"],
                "semDados": p["total_registros"] == 0,
            }
            for p in pacientes
        ]

        pacientes_resumo = []

        for p in pacientes:
            momento = (
                p["risco"].get("momento_clinico") or {}
            )

            status_clinico = momento.get("status")

            if status_clinico == "CRITICO":
                status = "vermelho"
            elif status_clinico == "ATENCAO":
                status = "amarelo"
            elif status_clinico == "ESTAVEL":
                status = "verde"
            else:
                status = "sem_dados"

            pacientes_resumo.append(
                {
                    "id": p["id"],
                    "nome": p["nome"],
                    "total_intervencoes":
                        p["total_intervencoes"],
                    "total_registros":
                        p["total_registros"],
                    "status": status,
                }
            )

        return {
            "resumo": {
                "total_pacientes": len(pacientes),
                "alto_risco": total_alto_risco,
                "atencao": total_atencao,
                "em_piora": total_em_piora,
                "estaveis": total_estaveis,
                "sem_dados": total_sem_dados,
                "total_registros": total_registros,
                "total_intervencoes": total_intervencoes,
            },
            "pacientes_criticos": pacientes_criticos[:6],
            "pacientes_resumo": pacientes_resumo,
            "grafico_intervencoes": grafico_intervencoes,
            "grafico_registros": grafico_registros,
        }    

    @staticmethod
    def obter_contadores_por_paciente(
        db: Session,
        usuario: Usuario,
        clinica_id: Optional[int] = None
    ):
        """
        Retorna contadores agregados de Registros Diários
        e Intervenções por paciente, sem carregar Timeline.
        """

        escopo = CockpitGestaoService.resolver_escopo(
            usuario,
            clinica_id=clinica_id,
        )

        filtro_clinica = ""
        parametros = {}

        if not escopo["admin_global"]:
            if not escopo["clinica_id"]:
                return {}

            filtro_clinica = "AND p.clinica_id = :clinica_id"
            parametros["clinica_id"] = escopo["clinica_id"]

        rows = db.execute(
            text(
                f"""
                SELECT
                    p.id AS paciente_id,

                    COUNT(DISTINCT CASE
                        WHEN rl.modulo_id = 1
                        THEN rl.id
                    END) AS total_registros,

                    COUNT(DISTINCT i.id) AS total_intervencoes

                FROM pacientes p

                LEFT JOIN registros_longitudinais rl
                    ON rl.paciente_id = p.id

                LEFT JOIN intervencoes i
                    ON i.paciente_id = p.id

                WHERE p.ativo = TRUE
                  {filtro_clinica}

                GROUP BY p.id
                """
            ),
            parametros,
        ).fetchall()

        return {
            row.paciente_id: {
                "total_registros": int(row.total_registros or 0),
                "total_intervencoes": int(row.total_intervencoes or 0),
            }
            for row in rows
        }
            
    @staticmethod
    def obter_pacientes(
        db: Session,
        usuario: Usuario,
        clinica_id: Optional[int] = None
    ):
        escopo = CockpitGestaoService.resolver_escopo(
            usuario,
            clinica_id=clinica_id,
        )

        query = (
            db.query(Paciente)
            .filter(Paciente.ativo == True)
        )

        if not escopo["admin_global"]:
            if not escopo["clinica_id"]:
                return []

            query = query.filter(
                Paciente.clinica_id == escopo["clinica_id"]
            )

        return (
            query
            .order_by(Paciente.nome.asc())
            .all()
        )

    @staticmethod
    def obter_analises_clinicas(
        db: Session,
        usuario: Usuario,
        clinica_id: Optional[int] = None
    ):
        """
        Reutiliza integralmente o Clinical Engine existente.
        """

        pacientes = CockpitGestaoService.obter_pacientes(
            db=db,
            usuario=usuario,
            clinica_id=clinica_id,
        )

        resultado = []

        for paciente in pacientes:
            analise = analisar_risco_paciente(
                db=db,
                paciente=paciente,
            )

            resultado.append(
                {
                    "paciente": paciente,
                    "risco": analise,
                }
            )

        return resultado
    
    @staticmethod
    def obter_acompanhamento_ativo(
        db: Session,
        usuario: Usuario,
        periodo_dias: int = 30,
    ):
        """
        Calcula o acompanhamento ativo e a cobertura assistencial.

        Uma pessoa é considerada em acompanhamento ativo quando possui
        pelo menos uma evidência assistencial no período:

        - Registro Diário;
        - Sessão Assistencial REALIZADA;
        - Avaliação Clínica CONCLUIDA;
        - Intervenção.

        O cálculo considera pessoas distintas, independentemente da
        quantidade de eventos existentes no período.
        """

        escopo = CockpitGestaoService.resolver_escopo(usuario)

        if not escopo["admin_global"] and not escopo["clinica_id"]:
            return {
                "pessoas_acompanhadas": 0,
                "acompanhamento_ativo": 0,
                "cobertura_assistencial": 0.0,
                "periodo_dias": periodo_dias,
            }

        filtro_clinica = ""
        parametros = {
            "data_inicio": date.today() - timedelta(days=periodo_dias - 1),
        }

        if not escopo["admin_global"]:
            filtro_clinica = "AND p.clinica_id = :clinica_id"
            parametros["clinica_id"] = escopo["clinica_id"]

        # População ativa no escopo
        sql_populacao = text(
            f"""
            SELECT COUNT(DISTINCT p.id)
            FROM pacientes p
            WHERE p.ativo = true
            {filtro_clinica}
            """
        )

        pessoas_acompanhadas = (
            db.execute(sql_populacao, parametros).scalar() or 0
        )

        # Pessoas com alguma evidência assistencial no período.
        #
        # UNION elimina duplicidades entre as fontes, garantindo que
        # cada paciente seja contado uma única vez.
        sql_ativos = text(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT rl.paciente_id
                FROM registros_longitudinais rl
                JOIN pacientes p ON p.id = rl.paciente_id
                WHERE p.ativo = true
                AND rl.data_registro >= :data_inicio
                {filtro_clinica}

                UNION

                SELECT sa.paciente_id
                FROM sessoes_assistenciais sa
                JOIN pacientes p ON p.id = sa.paciente_id
                WHERE p.ativo = true
                AND sa.status = 'REALIZADA'
                AND sa.data_realizacao IS NOT NULL
                AND sa.data_realizacao >= :data_inicio
                {filtro_clinica}

                UNION

                SELECT ac.paciente_id
                FROM avaliacoes_clinicas ac
                JOIN pacientes p ON p.id = ac.paciente_id
                WHERE p.ativo = true
                AND ac.status = 'CONCLUIDA'
                AND ac.executado_em::date >= :data_inicio
                {filtro_clinica}

                UNION

                SELECT i.paciente_id
                FROM intervencoes i
                JOIN pacientes p ON p.id = i.paciente_id
                WHERE p.ativo = true
                AND i.paciente_id IS NOT NULL
                AND i.data_intervencao::date >= :data_inicio
                {filtro_clinica}
            ) pessoas_ativas
            """
        )

        acompanhamento_ativo = (
            db.execute(sql_ativos, parametros).scalar() or 0
        )

        cobertura_assistencial = (
            round(
                (acompanhamento_ativo / pessoas_acompanhadas) * 100,
                2,
            )
            if pessoas_acompanhadas > 0
            else 0.0
        )

        return {
            "pessoas_acompanhadas": pessoas_acompanhadas,
            "acompanhamento_ativo": acompanhamento_ativo,
            "cobertura_assistencial": cobertura_assistencial,
            "periodo_dias": periodo_dias,
        }
        
    @staticmethod
    def obter_atencao_necessaria(
        db: Session,
        usuario: Usuario,
        analises_clinicas=None,
        continuidade_longitudinal=None,
    ):
        """
        Consolida as pessoas que necessitam de atenção gerencial.

        Fontes:
        - Clinical Engine:
            * risco clínico alto
            * atenção clínica
            * tendência de piora
        - Continuidade Longitudinal:
            * continuidade crítica
            * continuidade em atenção

        A mesma pessoa é contabilizada apenas uma vez no total executivo,
        mesmo quando possui múltiplos motivos de atenção.
        """

        if analises_clinicas is None:
            analises_clinicas = CockpitGestaoService.obter_analises_clinicas(
                db=db,
                usuario=usuario,
            )

        if continuidade_longitudinal is None:
            continuidade_longitudinal = (
                CockpitGestaoService.obter_continuidade_longitudinal(
                    db=db,
                    usuario=usuario,
                )
            )

        prioridades = {}

        contadores = {
            "risco_alto": 0,
            "atencao_clinica": 0,
            "piora_clinica": 0,
            "continuidade_critica": 0,
            "continuidade_atencao": 0,
        }

        ordem_prioridade = {
            "RISCO_CLINICO_ALTO": 1,
            "CONTINUIDADE_CRITICA": 2,
            "PIORA_CLINICA": 3,
            "ATENCAO_CLINICA": 4,
            "CONTINUIDADE_ATENCAO": 5,
        }

        def garantir_pessoa(paciente_id, nome):
            if paciente_id not in prioridades:
                prioridades[paciente_id] = {
                    "paciente_id": paciente_id,
                    "nome": nome,
                    "motivos": [],
                }

            return prioridades[paciente_id]

        def adicionar_motivo(paciente_id, nome, motivo):
            pessoa = garantir_pessoa(paciente_id, nome)

            tipos_existentes = {
                item["tipo"]
                for item in pessoa["motivos"]
            }

            if motivo["tipo"] not in tipos_existentes:
                pessoa["motivos"].append(motivo)

        # ---------------------------------------------------------
        # Clinical Engine
        # ---------------------------------------------------------

        for analise in analises_clinicas:
            risco = analise.get("risco") or {}

            paciente_id = risco.get("paciente_id")
            nome = risco.get("nome")

            if not paciente_id:
                continue

            risco_atual = str(
                risco.get("risco_atual") or ""
            ).lower()

            tendencia = str(
                risco.get("tendencia") or ""
            ).lower()

            if risco_atual in ("alto", "alto_risco"):
                adicionar_motivo(
                    paciente_id,
                    nome,
                    {
                        "tipo": "RISCO_CLINICO_ALTO",
                    },
                )
                contadores["risco_alto"] += 1

            if risco_atual in ("atencao", "atenção"):
                adicionar_motivo(
                    paciente_id,
                    nome,
                    {
                        "tipo": "ATENCAO_CLINICA",
                    },
                )
                contadores["atencao_clinica"] += 1

            if tendencia in ("piora", "piorando"):
                adicionar_motivo(
                    paciente_id,
                    nome,
                    {
                        "tipo": "PIORA_CLINICA",
                    },
                )
                contadores["piora_clinica"] += 1

        # ---------------------------------------------------------
        # Continuidade Longitudinal
        # ---------------------------------------------------------

        for item in continuidade_longitudinal.get("pacientes", []):
            paciente_id = item.get("paciente_id")
            nome = item.get("nome") or item.get("paciente_nome")
            classificacao = item.get("classificacao")
            dias_sem_registro = item.get("dias_sem_registro")

            if not paciente_id:
                continue

            if classificacao == "CRITICA":
                adicionar_motivo(
                    paciente_id,
                    nome,
                    {
                        "tipo": "CONTINUIDADE_CRITICA",
                        "dias_sem_registro": dias_sem_registro,
                    },
                )
                contadores["continuidade_critica"] += 1

            elif classificacao == "ATENCAO":
                adicionar_motivo(
                    paciente_id,
                    nome,
                    {
                        "tipo": "CONTINUIDADE_ATENCAO",
                        "dias_sem_registro": dias_sem_registro,
                    },
                )
                contadores["continuidade_atencao"] += 1

        # ---------------------------------------------------------
        # Ordenação
        # ---------------------------------------------------------

        prioridades_lista = list(prioridades.values())

        for pessoa in prioridades_lista:
            pessoa["motivos"].sort(
                key=lambda motivo: ordem_prioridade.get(
                    motivo["tipo"],
                    999,
                )
            )

            pessoa["prioridade_principal"] = (
                pessoa["motivos"][0]["tipo"]
                if pessoa["motivos"]
                else None
            )

        prioridades_lista.sort(
            key=lambda pessoa: (
                ordem_prioridade.get(
                    pessoa["prioridade_principal"],
                    999,
                ),
                pessoa["nome"] or "",
            )
        )

        return {
            "total_pessoas": len(prioridades_lista),
            "por_motivo": contadores,
            "prioridades": prioridades_lista,
        }
        
    @staticmethod
    def montar_cockpit_v2(
        usuario: Usuario,
        resumo,
        continuidade_longitudinal,
        acompanhamento,
        atencao_necessaria,
        atividade_assistencial,
        estrutura_operacao,
        eventos_recentes,
        profissionais_ativos: int,
    ):
        perfil = usuario.perfil

        contexto = {
            "perfil": perfil,
            "escopo": (
                "GLOBAL"
                if is_admin_global(usuario)
                else "CLINICA"
            ),
        }

        resumo_continuidade = (
            continuidade_longitudinal.get("resumo", {})
        )
        
        resumo_executivo = resumo.get("resumo", {})

        return {
            "contexto": contexto,

            "visao_executiva": {
                "pessoas_acompanhadas": acompanhamento.get(
                    "pessoas_acompanhadas", 0
                ),
                "acompanhamento_ativo": acompanhamento.get(
                    "acompanhamento_ativo", 0
                ),
                "cobertura_assistencial": acompanhamento.get(
                    "cobertura_assistencial", 0.0
                ),
                "atencao_necessaria": atencao_necessaria.get(
                    "total_pessoas", 0
                ),
                "profissionais_ativos": profissionais_ativos,
            },

            "situacao_populacao": {
                "situacao_clinica": {
                    "alto_risco": resumo_executivo.get(
                        "alto_risco", 0
                    ),
                    "atencao": resumo_executivo.get(
                        "atencao", 0
                    ),
                    "em_piora": resumo_executivo.get(
                        "em_piora", 0
                    ),
                    "estavel": resumo_executivo.get(
                        "estaveis", 0
                    ),
                    "sem_dados": resumo_executivo.get(
                        "sem_dados", 0
                    ),
                },

                "continuidade_longitudinal": {
                    "regular": resumo_continuidade.get(
                        "regular", 0
                    ),
                    "atencao": resumo_continuidade.get(
                        "atencao", 0
                    ),
                    "critica": resumo_continuidade.get(
                        "critica", 0
                    ),
                    "nao_iniciada": resumo_continuidade.get(
                        "nao_iniciada", 0
                    ),
                },
            },

            "prioridades_atencao": {
                "total_pessoas": atencao_necessaria.get(
                    "total_pessoas", 0
                ),
                "por_motivo": atencao_necessaria.get(
                    "por_motivo", {}
                ),
                "prioridades": atencao_necessaria.get(
                    "prioridades", []
                ),
            },

            "operacao_assistencial": atividade_assistencial,

            "estrutura_operacao": estrutura_operacao,

            "atividade_recente": eventos_recentes,
        }