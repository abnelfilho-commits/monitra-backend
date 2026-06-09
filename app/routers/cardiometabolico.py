

from datetime import datetime
from fastapi import HTTPException, APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_usuario_atual
from app.core.acl import is_admin_global

from app.database import get_db
from app.services.cardiometabolico import obter_dashboard_cardiometabolico
from app.schemas.cardiometabolico import (
    RegistroDiarioCardio,
    IntervencaoCreate,
)
from app.services.cardiometabolico_engine import (
    calcular_score,
    classificar_risco,
    definir_protocolo,
    gerar_leitura_clinica,
)

router = APIRouter(
    prefix="/cardiometabolico",
    tags=["Cardiometabólico"]
)

@router.get("/pacientes/{paciente_id}")
def obter_paciente_cardiometabolico(
    paciente_id: int,
    db: Session = Depends(get_db),
):
    paciente = db.execute(
        text("""
            SELECT
                p.id,
                p.nome,
                p.data_nascimento
            FROM pacientes p
            WHERE p.id = :paciente_id
            LIMIT 1
        """),
        {"paciente_id": paciente_id},
    ).fetchone()

    ultimo_registro = db.execute(
        text("""
            SELECT
                score_clinico,
                risco,
                protocolo,
                leitura_clinica,
                data_registro

            FROM registros_longitudinais

            WHERE paciente_id = :paciente_id
              AND modulo_id = 2

            ORDER BY data_registro DESC

            LIMIT 1
        """),
        {
        "paciente_id": paciente_id
        }
    ).fetchone()
    
    scores_rows = db.execute(
        text("""
            SELECT score_clinico

            FROM registros_longitudinais

            WHERE paciente_id = :paciente_id
              AND modulo_id = 2
              AND score_clinico IS NOT NULL

            ORDER BY data_registro ASC
        """),
        {
            "paciente_id": paciente_id,
        }
    ).fetchall()

    scores = [
        r.score_clinico
        for r in scores_rows
    ]

    tendencia = calcular_tendencia(scores)

    if not paciente:
        raise HTTPException(
            status_code=404,
            detail="Paciente não encontrado"
        )

    return {
        "id": paciente.id,

        "nome": paciente.nome,

        "data_nascimento": 
            str(paciente.data_nascimento)
            if paciente.data_nascimento
            else None,

        "score_clinico":
            ultimo_registro.score_clinico
            if ultimo_registro else 0,

        "risco":
            ultimo_registro.risco
            if ultimo_registro else "baixo",

        "protocolo":
            ultimo_registro.protocolo
            if ultimo_registro else "preventivo",

        "tendencia":
            tendencia,


        "leitura_clinica":
            ultimo_registro.leitura_clinica
            if ultimo_registro else "",

        "ultima_atualizacao":
            str(ultimo_registro.data_registro)
            if ultimo_registro else None,
    }

def calcular_adesao(
    total_registros
):

    if total_registros >= 20:
        return "alta"

    if total_registros >= 10:
        return "moderada"

    return "baixa"

def calcular_dias_em_risco(
    valores,
    limite
):
    dias = 0

    for valor in valores:

        if valor >= limite:
            dias += 1

    return dias

def gerar_resumo_clinico(
    glicemia,
    imc,
    sistolica,
    tendencia
):

    eventos = []

    # GLICEMIA

    if glicemia >= 180:
        eventos.append(
            "🔴 Hiperglicemia persistente detectada"
        )

    elif glicemia >= 150:
        eventos.append(
            "⚠ Glicemia acima da meta clínica"
        )

    # IMC

    if imc >= 40:
        eventos.append(
            "⚖ Obesidade mórbida identificada"
        )

    elif imc >= 30:
        eventos.append(
            "⚖ Obesidade em acompanhamento"
        )

    # PRESSÃO

    if sistolica >= 160:
        eventos.append(
            "🚨 Hipertensão persistente importante"
        )

    elif sistolica >= 140:
        eventos.append(
            "⚠ Pressão arterial elevada"
        )

    # TENDÊNCIA

    if tendencia == "alto risco persistente":
        eventos.append(
            "📈 Alto risco persistente"
        )

    elif tendencia == "piora":
        eventos.append(
            "📈 Tendência progressiva de piora"
        )

    elif tendencia == "melhora":
        eventos.append(
            "📉 Sinais de resposta terapêutica"
        )

    # DEFAULT

    if not eventos:
        return (
            "✅ Paciente apresenta estabilidade clínica."
        )

    return " • ".join(eventos)

def gerar_eventos_clinicos(
    glicemia,
    imc,
    sistolica,
    score,
    tendencia
):
    eventos = []

    if glicemia and glicemia >= 180:
        eventos.append("🔴 Hiperglicemia persistente")

    if sistolica and sistolica >= 160:
        eventos.append("🚨 Hipertensão importante")

    if imc and imc >= 40:
        eventos.append("⚖ Obesidade mórbida")

    if score and score >= 8:
        eventos.append("📈 Alto risco clínico")

    if (
        tendencia == "alto risco persistente"
        and score
        and score >= 8
    ):
        eventos.append("⚠ Alto risco persistente")

    return eventos

def calcular_tendencia(valores):

    if len(valores) < 3:
        return "monitoramento inicial"

    media_recente = sum(
        valores[-3:]
    ) / 3

    media_antiga = sum(
        valores[:-3]
    ) / max(len(valores[:-3]), 1)

    if media_recente >= 8:
        return "alto risco persistente"

    if media_recente > media_antiga * 1.15:
        return "piora"

    if media_recente < media_antiga * 0.90:
        return "melhora"

    return "estavel"

def calcular_variacao_percentual(
    valores
):

    if len(valores) < 2:
        return 0

    inicial = valores[0]
    final = valores[-1]

    if inicial == 0:
        return 0

    variacao = (
        (final - inicial)
        / inicial
    ) * 100

    return round(variacao, 1)

def calcular_prioridade_operacional(
    score,
    abandono,
    adesao,
    condicoes
):

    if (
        score >= 10
        or (
            abandono
            and condicoes >= 3
        )
    ):
        return "critica"

    if score >= 7:
        return "alta"

    if score >= 4:
        return "moderada"

    return "baixa"

def gerar_recomendacao(
    score,
    abandono,
    adesao,
    condicoes,
    tendencia
):

    if abandono:
        return (
            "Realizar busca ativa e "
            "retomar acompanhamento."
        )

    if (
        score >= 10
        or condicoes >= 3
    ):
        return (
            "Sugere-se acompanhamento "
            "multidisciplinar intensivo."
        )

    if tendencia == "piora":
        return (
            "Recomenda-se intensificar "
            "monitoramento clínico."
        )

    if adesao == "baixa":
        return (
            "Reforçar adesão ao "
            "acompanhamento longitudinal."
        )

    return (
        "Manter acompanhamento regular."
    )

def definir_protocolo_dashboard(
    score,
    abandono,
    adesao,
    condicoes,
    tendencia
):

    if abandono:
        return {
            "codigo": "busca_ativa",
            "descricao":
                "Paciente sem acompanhamento recente."
        }

    if (
        score >= 10
        or condicoes >= 3
    ):
        return {
            "codigo":
                "intensivo_cardiometabolico",

            "descricao":
                "Paciente elegível para "
                "acompanhamento intensivo."
        }

    if (
        score >= 6
        or tendencia == "piora"
    ):
        return {
            "codigo":
                "acompanhamento_clinico",

            "descricao":
                "Paciente requer "
                "monitoramento frequente."
        }

    if (
        tendencia == "melhora"
        and adesao == "alta"
        and score <= 3
    ):
        return {
            "codigo":
                "desospitalizacao_risco",

            "descricao":
                "Paciente apresenta estabilidade "
                "clínica sustentada."
        }

    return {
        "codigo":
            "monitoramento_preventivo",

        "descricao":
            "Paciente em monitoramento preventivo."
    }

def calcular_evolucao_assistencial(
    protocolo,
    tendencia,
    score
):

    codigo = protocolo.get("codigo")

    if (
        codigo == "intensivo_cardiometabolico"
        and tendencia == "melhora"
    ):
        return "melhora_assistencial"

    if (
        codigo == "busca_ativa"
        and score >= 8
    ):
        return "risco_elevado"

    if tendencia == "piora":
        return "agravamento_clinico"

    return "estavel"

@router.get("/pacientes/{paciente_id}/dashboard")
def dashboard_cardiometabolico(
    db: Session = Depends(get_db),
    usuario = Depends(get_usuario_atual),
):
    return obter_dashboard_cardiometabolico(db, paciente_id)

@router.get("/pacientes")
def listar_pacientes_cardiometabolico(
    db: Session = Depends(get_db),
    usuario = Depends(get_usuario_atual),
):
    rows = db.execute(
        text("""
            WITH ultimos AS (
                SELECT DISTINCT ON (rl.paciente_id)
                    rl.id AS registro_id,
                    rl.paciente_id,
                    rl.score_clinico,
                    rl.risco,
                    rl.data_registro
                    
                FROM registros_longitudinais rl
                JOIN pacientes p ON p.id = rl.paciente_id
                WHERE rl.modulo_id = 2
                AND (
                    :is_admin = true
                    OR p.clinica_id = :clinica_id
                )
                ORDER BY rl.paciente_id, rl.data_registro DESC
            ),

            valores AS (
                SELECT
                    rl.paciente_id,

                    (
                        SELECT r.valor_numero
                        FROM respostas_registro r
                        JOIN campos_formulario c ON c.id = r.campo_id
                        JOIN registros_longitudinais rl2 ON rl2.id = r.registro_id
                        WHERE rl2.paciente_id = rl.paciente_id
                        AND rl2.modulo_id = 2
                        AND c.nome_campo = 'glicemia_jejum'
                        AND r.valor_numero IS NOT NULL
                        ORDER BY rl2.data_registro DESC
                        LIMIT 1
                    ) AS glicemia,

                    (
                        SELECT r.valor_numero
                        FROM respostas_registro r
                        JOIN campos_formulario c ON c.id = r.campo_id
                        JOIN registros_longitudinais rl2 ON rl2.id = r.registro_id
                        WHERE rl2.paciente_id = rl.paciente_id
                        AND rl2.modulo_id = 2
                        AND c.nome_campo = 'pressao_sistolica'
                        AND r.valor_numero IS NOT NULL
                        ORDER BY rl2.data_registro DESC
                        LIMIT 1
                    ) AS sistolica,

                    (
                        SELECT r.valor_numero
                        FROM respostas_registro r
                        JOIN campos_formulario c ON c.id = r.campo_id
                        JOIN registros_longitudinais rl2 ON rl2.id = r.registro_id
                        WHERE rl2.paciente_id = rl.paciente_id
                        AND rl2.modulo_id = 2
                        AND c.nome_campo = 'pressao_diastolica'
                        AND r.valor_numero IS NOT NULL
                        ORDER BY rl2.data_registro DESC
                        LIMIT 1
                    ) AS diastolica,

                    (
                        SELECT r.valor_numero
                        FROM respostas_registro r
                        JOIN campos_formulario c ON c.id = r.campo_id
                        JOIN registros_longitudinais rl2 ON rl2.id = r.registro_id
                        WHERE rl2.paciente_id = rl.paciente_id
                        AND rl2.modulo_id = 2
                        AND c.nome_campo = 'peso'
                        AND r.valor_numero IS NOT NULL
                        ORDER BY rl2.data_registro DESC
                        LIMIT 1
                    ) AS peso,

                    (
                        SELECT r.valor_numero
                        FROM respostas_registro r
                        JOIN campos_formulario c ON c.id = r.campo_id
                        JOIN registros_longitudinais rl2 ON rl2.id = r.registro_id
                        WHERE rl2.paciente_id = rl.paciente_id
                        AND rl2.modulo_id = 2
                        AND c.nome_campo = 'altura'
                        AND r.valor_numero IS NOT NULL
                        ORDER BY rl2.data_registro DESC
                        LIMIT 1
                    ) AS altura

                FROM registros_longitudinais rl
                WHERE rl.modulo_id = 2
                GROUP BY rl.paciente_id
            )

            SELECT
                p.id,
                p.nome,
                u.score_clinico,
                u.risco,

                COALESCE(rl.glicemia_jejum, v.glicemia) AS glicemia,
                COALESCE(rl.pressao_sistolica, v.sistolica) AS sistolica,
                COALESCE(rl.pressao_diastolica, v.diastolica) AS diastolica,
                COALESCE(rl.peso, v.peso) AS peso,
                v.altura AS altura

            FROM ultimos u
            JOIN registros_longitudinais rl ON rl.id = u.registro_id
            JOIN pacientes p ON p.id = u.paciente_id
            LEFT JOIN valores v ON v.paciente_id = p.id
            WHERE (
                :is_admin = true
                OR p.clinica_id = :clinica_id
            )
            ORDER BY p.nome ASC
        """),
        {
            "is_admin": is_admin_global(usuario),
            "clinica_id": usuario.clinica_id,
        }
    ).fetchall()

    pacientes = []

    for row in rows:
        imc = None

        if row.peso and row.altura:
            imc = round(
                float(row.peso) / (
                    float(row.altura) * float(row.altura)
                ),
                1
            )

        pacientes.append({
            "id": row.id,
            "nome": row.nome,

            "glicemia": row.glicemia,

            "pressao": (
                f"{int(row.sistolica)}x{int(row.diastolica)}"
                if row.sistolica and row.diastolica
                else None
            ),

            "peso": row.peso,
            "altura": row.altura,
            "imc": imc,

            "score_clinico": row.score_clinico or 0,

            "risco": row.risco or "baixo",
        })

    return pacientes


@router.get("/pacientes/{paciente_id}/evolucao")
def evolucao_cardiometabolica(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    rows = db.execute(
        text("""
            SELECT
                rl.data_registro,

                rl.glicemia_jejum,
                rl.glicemia_pos_prandial,

                rl.pressao_sistolica,
                rl.pressao_diastolica,

                rl.peso

            FROM registros_longitudinais rl

            WHERE rl.paciente_id = :paciente_id
              AND rl.modulo_id = 2

            ORDER BY rl.data_registro ASC
        """),
        {"paciente_id": paciente_id}
    ).fetchall()

    evolucao = []

    for r in rows:

        evolucao.append({
            "data": r.data_registro.isoformat(),

            "glicemia_jejum": r.glicemia_jejum,
            "glicemia_pos_prandial": r.glicemia_pos_prandial,

            "pressao_sistolica": r.pressao_sistolica,
            "pressao_diastolica": r.pressao_diastolica,

            "peso": r.peso,

            "altura": None,
            "imc": None,
        })

    return evolucao

@router.get("/pacientes/{paciente_id}/timeline")
def timeline_cardiometabolica(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    rows = db.execute(
        text("""
            SELECT
                rl.id,
                rl.data_registro,

                rl.score_clinico,
                rl.risco,
                rl.protocolo,
                rl.leitura_clinica,

                COALESCE(
                    rl.glicemia_jejum,
                    (
                        SELECT r.valor_numero
                        FROM respostas_registro r
                        JOIN campos_formulario c
                        ON c.id = r.campo_id
                        WHERE r.registro_id = rl.id
                        AND c.nome_campo = 'glicemia_jejum'
                        LIMIT 1
                    )
                ) AS glicemia_jejum,

                COALESCE(
                    rl.pressao_sistolica,
                    (
                        SELECT r.valor_numero
                        FROM respostas_registro r
                        JOIN campos_formulario c
                        ON c.id = r.campo_id
                        WHERE r.registro_id = rl.id
                        AND c.nome_campo = 'pressao_sistolica'
                        LIMIT 1
                    )
                ) AS pressao_sistolica,

                COALESCE(
                    rl.pressao_diastolica,
                    (
                        SELECT r.valor_numero
                        FROM respostas_registro r
                        JOIN campos_formulario c
                        ON c.id = r.campo_id
                        WHERE r.registro_id = rl.id
                        AND c.nome_campo = 'pressao_diastolica'
                        LIMIT 1
                    )
                ) AS pressao_diastolica,

                COALESCE(
                    rl.peso,
                    (
                        SELECT r.valor_numero
                        FROM respostas_registro r
                        JOIN campos_formulario c
                        ON c.id = r.campo_id
                        WHERE r.registro_id = rl.id
                        AND c.nome_campo = 'peso'
                        LIMIT 1
                    )
                ) AS peso,
                
                (
                    SELECT r.valor_numero
                    FROM respostas_registro r
                    JOIN campos_formulario c
                    ON c.id = r.campo_id
                    WHERE r.registro_id = rl.id
                    AND c.nome_campo = 'altura'
                    LIMIT 1
                ) AS altura,
                
                rl.sono,
                rl.humor,
                rl.origem

            FROM registros_longitudinais rl

            WHERE rl.paciente_id = :paciente_id
            AND rl.modulo_id = 2

            ORDER BY rl.data_registro DESC
        """),
        {"paciente_id": paciente_id}
    ).fetchall()

    agrupado = {}

    for r in rows:
        registro_id = r.id

        if registro_id not in agrupado:
            agrupado[registro_id] = {
                "id": registro_id,

                "data": r.data_registro.isoformat(),

                "tipo": "Registro diário",
                
                "origem": r.origem,
                "tipo_evento": (
                    "❤️ Registro do Responsável"
                    if r.origem == "RESPONSAVEL"
                    else "📈 Registro diário"
                ),

                "glicemia": None,

                "pressao": None,

                "peso": None,

                "altura": None,

                "imc": None,
                
                "sono": None,
                "humor": None,

                "score":
                    r.score_clinico or 0,

                "risco":
                    r.risco or "baixo",

                "protocolo":
                    r.protocolo or "preventivo",

                "descricao":
                    r.leitura_clinica or "",

            }

        agrupado[registro_id]["glicemia"] = r.glicemia_jejum

        agrupado[registro_id]["pressao_sistolica"] = r.pressao_sistolica

        agrupado[registro_id]["pressao_diastolica"] = r.pressao_diastolica

        agrupado[registro_id]["peso"] = r.peso
        
        agrupado[registro_id]["altura"] = r.altura

        agrupado[registro_id]["sono"] = r.sono

        agrupado[registro_id]["humor"] = r.humor

    intervencoes = db.execute(
        text("""
            SELECT
                id,
                tipo,
                descricao,
                prioridade,
                created_at
            FROM intervencoes_cardiometabolicas
            WHERE paciente_id = :paciente_id
            ORDER BY created_at DESC
        """),
        {
            "paciente_id": paciente_id
        }
    ).fetchall()

    # Pós-processamento
    for item in agrupado.values():

        sistolica = item.get("pressao_sistolica")
        diastolica = item.get("pressao_diastolica")

        if sistolica and diastolica:
            item["pressao"] = f"{int(sistolica)}x{int(diastolica)}"

        peso = item.get("peso")
        altura = item.get("altura")

        if peso and altura and altura > 0:
            imc = round(peso / (altura * altura), 1)

            item["imc"] = imc

            if imc >= 40:
                item["descricao"] += " Obesidade mórbida identificada."
                item["risco"] = "alto"

            elif imc >= 30:
                item["descricao"] += " Obesidade identificada."
                item["risco"] = "moderado"

        glicemia = item.get("glicemia")                

        tendencia_item = None

        if item.get("score") >= 8:
            tendencia_item = "alto risco persistente"
        elif item.get("score") >= 4:
            tendencia_item = "atenção clínica"
        else:
            tendencia_item = "estável"

        item["eventos_clinicos"] = gerar_eventos_clinicos(
            glicemia=item.get("glicemia"),
            imc=item.get("imc"),
            sistolica=item.get("pressao_sistolica"),
            score=item.get("score"),
            tendencia=tendencia_item,
        )        

    timeline = list(agrupado.values())

    for intervencao in intervencoes:

        timeline.append({
            "id": f"intervencao-{intervencao.id}",

            "data":
                intervencao.created_at.isoformat(),

            "tipo":
                "Intervenção clínica",

            "tipo_evento":
                "🩺 Intervenção clínica",

            "descricao":
                intervencao.descricao,

            "prioridade":
                intervencao.prioridade,

            "intervencao_tipo":
                intervencao.tipo,

            "eventos_clinicos": [
                f"🩺 {intervencao.tipo.replace('_', ' ').title()}",
                (
                    f"🚨 Prioridade {intervencao.prioridade}"
                    if intervencao.prioridade in ["alta", "critica"]
                    else f"📋 Prioridade {intervencao.prioridade}"
                )
            ]
        })

    timeline = sorted(
        timeline,
        key=lambda x: x["data"],
        reverse=True
    )

    return timeline

@router.get("/dashboard")
def dashboard_cardiometabolico(
    db: Session = Depends(get_db)
):
    rows = db.execute(
        text("""
            SELECT DISTINCT ON (rl.paciente_id)
                rl.paciente_id,
                rl.score_clinico,
                rl.risco
            FROM registros_longitudinais rl
            WHERE rl.modulo_id = 2
            ORDER BY
                rl.paciente_id,
                rl.data_registro DESC
        """),
        {
            "is_admin": is_admin_global(usuario),
            "clinica_id": usuario.clinica_id,
        }
    ).fetchall()

    total = len(rows)
    alto_risco = 0
    moderado = 0
    baixo = 0
    critico = 0

    for r in rows:
        risco = r.risco or "baixo"

        if risco == "critico":
            critico += 1
        elif risco == "alto":
            alto_risco += 1
        elif risco == "moderado":
            moderado += 1
        else:
            baixo += 1

    return {
        "total_pacientes": total,
        "critico": critico,
        "alto_risco": alto_risco,
        "moderado": moderado,
        "baixo": baixo,
    }


@router.get("/dashboard-analytics")
def dashboard_analytics(
    db: Session = Depends(get_db),
    usuario = Depends(get_usuario_atual),
):
    rows = db.execute(
        text("""
            WITH ultimos AS (
                SELECT DISTINCT ON (rl.paciente_id)
                    rl.id AS registro_id,
                    rl.paciente_id,
                    rl.score_clinico,
                    rl.risco,
                    rl.data_registro
                FROM registros_longitudinais rl
                JOIN pacientes p ON p.id = rl.paciente_id
                WHERE rl.modulo_id = 2
                AND (
                    :is_admin = true
                    OR p.clinica_id = :clinica_id
                )
                ORDER BY rl.paciente_id, rl.data_registro DESC
            ),

            valores AS (
                SELECT
                    rl.paciente_id,

                    MAX(r.valor_numero) FILTER (
                        WHERE c.nome_campo = 'glicemia_jejum'
                    ) AS glicemia,

                    MAX(r.valor_numero) FILTER (
                        WHERE c.nome_campo = 'pressao_sistolica'
                    ) AS sistolica,

                    MAX(r.valor_numero) FILTER (
                        WHERE c.nome_campo = 'pressao_diastolica'
                    ) AS diastolica,

                    MAX(r.valor_numero) FILTER (
                        WHERE c.nome_campo = 'peso'
                    ) AS peso,

                    MAX(r.valor_numero) FILTER (
                        WHERE c.nome_campo = 'altura'
                    ) AS altura

                FROM registros_longitudinais rl
                JOIN pacientes p ON p.id = rl.paciente_id
                JOIN respostas_registro r
                ON r.registro_id = rl.id
                JOIN campos_formulario c
                ON c.id = r.campo_id
                WHERE rl.modulo_id = 2
                AND (
                    :is_admin = true
                    OR p.clinica_id = :clinica_id
                )
                GROUP BY rl.paciente_id
            )

            SELECT
                p.id,
                p.nome,

                u.score_clinico,
                u.risco,
                rl.protocolo,
                rl.leitura_clinica,
                rl.data_registro,

                COALESCE(rl.glicemia_jejum, v.glicemia) AS glicemia,
                COALESCE(rl.pressao_sistolica, v.sistolica) AS sistolica,
                COALESCE(rl.pressao_diastolica, v.diastolica) AS diastolica,
                COALESCE(rl.peso, v.peso) AS peso,
                v.altura AS altura

            FROM ultimos u
            JOIN registros_longitudinais rl
            ON rl.id = u.registro_id
            JOIN pacientes p
            ON p.id = u.paciente_id
            LEFT JOIN valores v
            ON v.paciente_id = p.id
            ORDER BY p.nome ASC;
        """),
        {
            "is_admin": is_admin_global(usuario),
            "clinica_id": usuario.clinica_id,
        }
    ).fetchall()

    pacientes_criticos = []

    risco_baixo = 0
    risco_moderado = 0
    risco_alto = 0
    risco_critico = 0

    glicemia_critica = 0
    obesidade = 0
    hipertensos = 0

    for row in rows:
        score = row.score_clinico or 0
        risco = row.risco or "baixo"
        resumo = row.leitura_clinica or "Paciente em acompanhamento."
        protocolo = row.protocolo or "preventivo"

        imc = None

        if row.peso and row.altura:
            imc = round(float(row.peso) / (float(row.altura) * float(row.altura)), 1)

        pa = (
            f"{int(row.sistolica)}x{int(row.diastolica)}"
            if row.sistolica and row.diastolica
            else None
        )

        if risco == "critico":
            risco_critico += 1
        elif risco == "alto":
            risco_alto += 1
        elif risco == "moderado":
            risco_moderado += 1
        else:
            risco_baixo += 1

        if row.glicemia and row.glicemia >= 180:
            glicemia_critica += 1

        if imc and imc >= 35:
            obesidade += 1

        if row.sistolica and row.sistolica >= 160:
            hipertensos += 1

        pacientes_criticos.append({
            "id": row.id,
            "nome": row.nome,
            "score": score,
            "risco": risco,
            "resumo": resumo,
            "protocolo": protocolo,
            "protocolo_label": {
                "preventivo": "Preventivo",
                "monitoramento_ativo": "Monitoramento Ativo",
                "intensivo_cardiometabolico": "Intensivo Cardiometabólico",
                "Alerta crítico / busca ativa imediata": "Alerta crítico / busca ativa imediata",
                "Intervenção clínica prioritária": "Intervenção clínica prioritária",
                "Monitoramento intensificado": "Monitoramento intensificado",
                "Acompanhamento de rotina": "Acompanhamento de rotina",
            }.get(protocolo, protocolo),
            "glicemia": row.glicemia,
            "imc": imc,
            "pa": pa,
            "ultima_atualizacao": (
                str(row.data_registro)
                if row.data_registro else None
            ),
        })

    pacientes_criticos = sorted(
        pacientes_criticos,
        key=lambda x: x["score"],
        reverse=True
    )

    grafico_glicemia = [
        {
            "mes": p["nome"].split(" ")[0],
            "media": p["glicemia"] or 0
        }
        for p in pacientes_criticos
    ]

    grafico_score = [
        {
            "mes": p["nome"].split(" ")[0],
            "media": p["score"] or 0
        }
        for p in pacientes_criticos
    ]

    return {
        "indicadores": {
            "total_pacientes": len(rows),
            "critico": risco_critico,
            "alto_risco": risco_alto,
            "moderado": risco_moderado,
            "baixo": risco_baixo,
            "glicemia_critica": glicemia_critica,
            "obesidade": obesidade,
            "hipertensos": hipertensos,
            "sem_acompanhamento": 0,
        },
        "distribuicao_risco": {
            "critico": risco_critico,
            "alto": risco_alto,
            "moderado": risco_moderado,
            "baixo": risco_baixo,
        },
        "pacientes_criticos": pacientes_criticos,
        "grafico_glicemia": grafico_glicemia,
        "grafico_score": grafico_score,
    }

@router.get("/alertas")
def alertas_cardiometabolico(
    db: Session = Depends(get_db)
    ):
    rows = db.execute(text("""
        SELECT
            p.id,
            p.nome,

            MAX(
                CASE
                    WHEN c.nome_campo = 'glicemia_jejum'
                    THEN r.valor_numero
                END
            ) AS glicemia,

            MAX(
                CASE
                    WHEN c.nome_campo = 'pressao_sistolica'
                    THEN r.valor_numero
                END
            ) AS sistolica,

            MAX(
                CASE
                    WHEN c.nome_campo = 'peso'
                    THEN r.valor_numero
                END
            ) AS peso,

            MAX(
                CASE
                    WHEN c.nome_campo = 'altura'
                    THEN r.valor_numero
                END
            ) AS altura

        FROM pacientes p

        JOIN registros_longitudinais rl
          ON rl.paciente_id = p.id

        JOIN respostas_registro r
          ON r.registro_id = rl.id

        JOIN campos_formulario c
          ON c.id = r.campo_id

        JOIN modulos_clinicos m
          ON m.id = rl.modulo_id

        WHERE m.slug = 'cardiometabolico'

        GROUP BY p.id, p.nome
    """)).fetchall()

    alertas = []

    for row in rows:
        glicemia = row.glicemia or 0
        sistolica = row.sistolica or 0

        peso = row.peso or 0
        altura = row.altura or 0

        imc = 0

        if peso and altura:
            imc = round(
                peso / (altura * altura),
                1
            )

        if glicemia >= 250:

            alertas.append({
                "tipo": "glicemia_critica",
                "paciente_id": row.id,
                "paciente": row.nome,
                "mensagem":
                    "Glicemia criticamente elevada.",
                "gravidade": "alta"
            })

        if sistolica >= 180:

            alertas.append({
                "tipo": "hipertensao_severa",
                "paciente_id": row.id,
                "paciente": row.nome,
                "mensagem":
                    "Hipertensão severa identificada.",
                "gravidade": "alta"
            })

        if imc >= 40:

            alertas.append({
                "tipo": "obesidade_morbida",
                "paciente_id": row.id,
                "paciente": row.nome,
                "mensagem":
                    "Obesidade mórbida identificada.",
                "gravidade": "moderada"
            })

    return {
        "total_alertas": len(alertas),
        "alertas": alertas
    }

@router.post("/registro-diario")
def criar_registro_diario(
    payload: RegistroDiarioCardio,
    db: Session = Depends(get_db)
    ):
    formulario = db.execute(text("""
        SELECT fm.id
        FROM formularios_modulo fm
        JOIN modulos_clinicos mc ON mc.id = fm.modulo_id
        WHERE mc.slug = 'cardiometabolico'
        AND fm.tipo = 'REGISTRO_DIARIO'
        AND fm.ativo = true
        LIMIT 1
    """)).fetchone()

    if not formulario:
        raise HTTPException(
            status_code=400,
            detail="Formulário cardiometabólico não configurado."
        )

    dados_motor = {
        "glicemia_jejum":
            payload.glicemia_jejum,

        "pressao_sistolica":
            payload.pressao_sistolica,

        "pressao_diastolica":
            payload.pressao_diastolica,

        "peso":
            payload.peso,

        "atividade_fisica":
            payload.atividade_fisica,

        "humor": payload.humor,

        "sono": payload.sono,
    }

    score = calcular_score(
        dados_motor
    )

    risco = classificar_risco(
        score
    )

    protocolo = definir_protocolo(
    score
    )

    leitura_clinica = gerar_leitura_clinica(
        dados_motor,
        score,
    )

    registro = db.execute(
        text("""
            INSERT INTO registros_longitudinais (
                paciente_id,
                modulo_id,
                formulario_id,
                data_registro,
                origem,
                score_clinico,
                risco,
                protocolo,
                leitura_clinica
            )
            VALUES (
                :paciente_id,
                2,
                :formulario_id,
                NOW(),
                'PROFISSIONAL',
                :score_clinico,
                :risco,
                :protocolo,
                :leitura_clinica
            )
            RETURNING id
        """),
        {
            "paciente_id": 
                payload.paciente_id,

            "formulario_id": formulario.id,

            "score_clinico":
                score,

            "risco":
                risco,

            "protocolo":
                protocolo,

            "leitura_clinica":
                leitura_clinica,
        }
    ).fetchone()
           
    respostas = {
        "glicemia_jejum":
            payload.glicemia_jejum,

        "pressao_sistolica":
            payload.pressao_sistolica,

        "pressao_diastolica":
            payload.pressao_diastolica,

        "peso":
            payload.peso,

        "uso_medicacao":
            payload.uso_medicacao,

        "atividade_fisica":
            payload.atividade_fisica,

        "adesao_alimentar":
            payload.adesao_alimentar,
            
        "sono": payload.sono,
        
        "humor": payload.humor,
    }
    
    for nome_campo, valor in respostas.items():

        campo = db.execute(text("""
            SELECT id
            FROM campos_formulario
            WHERE nome_campo = :nome_campo
        """), {
            "nome_campo": nome_campo
        }).fetchone()

        if not campo:
            continue

        if isinstance(valor, (int, float)):
            db.execute(text("""
                INSERT INTO respostas_registro (
                    registro_id,
                    campo_id,
                    valor_numero
                ) 
                VALUES (
                    :registro_id,
                    :campo_id,
                    :valor
                )
            """), {
                "registro_id": registro.id,
                "campo_id": campo.id,
                "valor": valor
            })
        else:
            db.execute(text("""
                INSERT INTO respostas_registro (
                    registro_id,
                    campo_id,
                    valor_texto
                )
                VALUES (
                    :registro_id,
                    :campo_id,
                    :valor
                )
            """), {
                "registro_id": registro.id,
                "campo_id": campo.id,
                "valor": str(valor)
            })

    db.commit()
    return {
        "message":
            "Registro diário criado com sucesso.",

        "registro_id":
            registro.id
    }

@router.get("/mapa-risco")
def mapa_risco_cardiometabolico(
    db: Session = Depends(get_db)
):
    rows = db.execute(
        text("""
            SELECT DISTINCT ON (p.id)
                p.id,
                p.nome,
                COALESCE(c.nome, 'Clínica não informada') AS clinica,
                rl.score_clinico,
                rl.risco,
                rl.protocolo
            FROM pacientes p
            JOIN registros_longitudinais rl
              ON rl.paciente_id = p.id
            LEFT JOIN clinicas c
              ON c.id = p.clinica_id
            WHERE rl.modulo_id = 2
            ORDER BY p.id, rl.data_registro DESC
        """)
    ).fetchall()

    mapa = {}

    for row in rows:
        clinica = row.clinica or "Clínica não informada"
        risco = row.risco or "baixo"
        score = row.score_clinico or 0
        
        if clinica not in mapa:
            mapa[clinica] = {
                "clinica": clinica,
                "total": 0,
                "alto": 0,
                "moderado": 0,
                "baixo": 0,
                "score_total": 0,
                "pacientes_criticos": [],
            }

        mapa[clinica]["total"] += 1
        mapa[clinica]["score_total"] += score

        mapa[clinica]["pacientes_criticos"].append({
            "id": row.id,
            "nome": row.nome,
            "score": score,
            "risco": risco,
            "protocolo": row.protocolo or "preventivo",
        })

        if risco == "alto":
            mapa[clinica]["alto"] += 1
        elif risco == "moderado":
            mapa[clinica]["moderado"] += 1
        else:
            mapa[clinica]["baixo"] += 1

    resultado = []

    for item in mapa.values():
        total = item["total"] or 1

        criticos = sorted(
            item["pacientes_criticos"],
            key=lambda x: x["score"],
            reverse=True
        )

        resultado.append({
            "clinica": item["clinica"],
            "total": item["total"],
            "alto": item["alto"],
            "moderado": item["moderado"],
            "baixo": item["baixo"],
            "score_medio": round(item["score_total"] / total, 1),
            "pacientes_criticos": criticos[:3],
        })

    return sorted(
        resultado,
        key=lambda x: x["alto"],
        reverse=True
    ) 

@router.post("/pacientes/{paciente_id}/intervencoes")
def criar_intervencao(
    paciente_id: int,
    payload: IntervencaoCreate,
    db: Session = Depends(get_db)
):
    db.execute(
        text("""
            INSERT INTO intervencoes_cardiometabolicas (
                paciente_id,
                tipo,
                descricao,
                prioridade
            )
            VALUES (
                :paciente_id,
                :tipo,
                :descricao,
                :prioridade
            )
        """),
        {
            "paciente_id": paciente_id,
            "tipo": payload.tipo,
            "descricao": payload.descricao,
            "prioridade": payload.prioridade,
        }
    )

    db.commit()

    return {
        "success": True
    }
    
@router.get("/pacientes/{paciente_id}/intervencoes")
def listar_intervencoes(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    rows = db.execute(
        text("""
            SELECT
                id,
                tipo,
                descricao,
                prioridade,
                created_at
            FROM intervencoes_cardiometabolicas
            WHERE paciente_id = :paciente_id
            ORDER BY created_at DESC
        """),
        {
            "paciente_id": paciente_id
        }
    ).fetchall()

    return [
        {
            "id": r.id,
            "tipo": r.tipo,
            "descricao": r.descricao,
            "prioridade": r.prioridade,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]