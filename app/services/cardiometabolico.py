from sqlalchemy.orm import Session
from sqlalchemy import text


def obter_dashboard_cardiometabolico(
    db: Session,
    paciente_id: int
):
    row = db.execute(
        text("""
             
            WITH ultimo_registro AS (
                SELECT DISTINCT ON (rl.paciente_id)

                    rl.id,
                    rl.paciente_id,
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
                    ) AS peso

                FROM registros_longitudinais rl

                WHERE rl.paciente_id = :paciente_id
                AND rl.modulo_id = 2

                ORDER BY
                    rl.paciente_id,
                    rl.data_registro DESC
            ),

            respostas AS (
                SELECT
                    rl.paciente_id,

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
                            WHEN c.nome_campo = 'pressao_diastolica'
                            THEN r.valor_numero
                        END
                    ) AS diastolica,

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

                FROM registros_longitudinais rl

                JOIN respostas_registro r
                ON r.registro_id = rl.id

                JOIN campos_formulario c
                ON c.id = r.campo_id

                WHERE rl.paciente_id = :paciente_id
                AND rl.modulo_id = 2

                GROUP BY rl.paciente_id
            )

            SELECT
                p.id,
                p.nome,

                u.score_clinico,
                u.risco,
                u.protocolo,
                u.leitura_clinica,
                u.data_registro,

                COALESCE(
                    u.glicemia_jejum,
                    resp.glicemia
                ) AS glicemia,

                COALESCE(
                    u.pressao_sistolica,
                    resp.sistolica
                ) AS pressao_sistolica,

                COALESCE(
                    u.pressao_diastolica,
                    resp.diastolica
                ) AS pressao_diastolica,

                COALESCE(
                    u.peso,
                    resp.peso
                ) AS peso,

                resp.altura AS altura

            FROM pacientes p

            JOIN ultimo_registro u
            ON u.paciente_id = p.id

            LEFT JOIN respostas resp
            ON resp.paciente_id = p.id

            WHERE p.id = :paciente_id
        """),
        {"paciente_id": paciente_id}
    ).fetchone()

    if not row:
        return {
            "erro": "Paciente sem dados cardiometabólicos"
        }

    imc = None

    if row.peso and row.altura:
        try:
            imc = round(
                float(row.peso) / (
                    float(row.altura) * float(row.altura)
                ),
                1
            )
        except Exception:
            imc = None

    tendencia = {
        "baixo": "Estável",
        "moderado": "Atenção longitudinal",
        "alto": "Alto Risco Persistente",
        "critico": "Alto Risco Persistente",
    }.get(row.risco, "Em acompanhamento")

    fatores = []

    glicemia = row.glicemia_jejum or 0
    sistolica = row.pressao_sistolica or 0

    if glicemia >= 180:
        fatores.append("🔴 Hiperglicemia persistente")

    if sistolica >= 160:
        fatores.append("🚨 Hipertensão importante")

    if imc and imc >= 35:
        fatores.append("⚖️ Obesidade severa")

    if row.score_clinico and row.score_clinico >= 8:
        fatores.append("📈 Alto risco clínico")

    if row.risco == "critico":
        fatores.append("⚠️ Alto risco persistente")

    pa = None

    if row.pressao_sistolica and row.pressao_diastolica:
        pa = (
            f"{int(row.pressao_sistolica)}x"
            f"{int(row.pressao_diastolica)}"
        )

    return {
        "paciente_id": row.id,
        "nome": row.nome,

        "score_clinico": row.score_clinico,
        "risco": row.risco,
        "tendencia": tendencia,

        "protocolo": row.protocolo,
        "leitura_clinica": row.leitura_clinica,

        "glicemia": row.glicemia_jejum,
        "pressao_arterial": pa,

        "peso": row.peso,
        "altura": row.altura,
        "imc": imc,

        "fatores_observados": fatores,

        "ultima_atualizacao": (
            str(row.data_registro)
            if row.data_registro else None
        ),
    }
