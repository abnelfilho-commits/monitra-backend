from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db

from app.services.longitudinal.service import longitudinal_service

router = APIRouter(
    prefix="/timeline",
    tags=["Timeline"]
)


@router.get("/pacientes/{paciente_id}")
def obter_timeline_paciente(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    registros = db.execute(
        text("""
            SELECT
                rl.id,
                rl.paciente_id,
                rl.data_registro,
                rl.criado_em,
                rl.origem,

                MAX(CASE WHEN cf.nome_campo = 'sono_qualidade'
                    THEN rr.valor_numero END) AS sono_qualidade,

                MAX(CASE WHEN cf.nome_campo = 'irritabilidade'
                    THEN rr.valor_numero END) AS irritabilidade,

                MAX(CASE WHEN cf.nome_campo = 'crise_sensorial'
                    THEN rr.valor_numero END) AS crise_sensorial,

                MAX(CASE WHEN cf.nome_campo = 'tempo_tela'
                    THEN rr.valor_texto END) AS tempo_tela,

                MAX(CASE WHEN cf.nome_campo = 'seletividade_alimentar'
                    THEN rr.valor_texto END) AS seletividade_alimentar,

                COALESCE(
                    BOOL_OR(
                        CASE
                            WHEN cf.nome_campo = 'aceitou_alimento_novo'
                            THEN rr.valor_booleano
                        END
                    ),
                    false
                ) AS aceitou_alimento_novo,

                MAX(CASE WHEN cf.nome_campo = 'observacao'
                    THEN rr.valor_texto END) AS observacao

            FROM registros_longitudinais rl
            LEFT JOIN respostas_registro rr
                ON rr.registro_id = rl.id
            LEFT JOIN campos_formulario cf
                ON cf.id = rr.campo_id

            WHERE rl.paciente_id = :paciente_id
              AND rl.modulo_id = 1

            GROUP BY
                rl.id,
                rl.paciente_id,
                rl.data_registro,
                rl.criado_em,
                rl.origem

            ORDER BY rl.data_registro DESC, rl.id DESC
        """),
        {"paciente_id": paciente_id}
    ).fetchall()

    timeline = []

    for r in registros:
        timeline.append({
            "id": r.id,
            "paciente_id": r.paciente_id,
            "tipo_evento": "REGISTRO_DIARIO",
            "data": (
                r.criado_em.isoformat()
                if r.criado_em
                else r.data_registro.isoformat()
            ),
            "descricao": r.observacao,
            "origem": r.origem or "PROFISSIONAL",
            "sono_qualidade": str(int(r.sono_qualidade)) if r.sono_qualidade is not None else None,
            "irritabilidade": str(int(r.irritabilidade)) if r.irritabilidade is not None else None,
            "crise_sensorial": bool(r.crise_sensorial) if r.crise_sensorial is not None else None,
            "tempo_tela": r.tempo_tela,
            "seletividade_alimentar": r.seletividade_alimentar,
            "aceitou_alimento_novo": r.aceitou_alimento_novo,
        })

    intervencoes = db.execute(
        text("""
            SELECT
                id,
                paciente_id,
                data_intervencao,
                descricao,
                profissional_id
            FROM intervencoes
            WHERE paciente_id = :paciente_id
            ORDER BY data_intervencao DESC, id DESC
        """),
        {"paciente_id": paciente_id}
    ).fetchall()

    for i in intervencoes:
        timeline.append({
            "id": i.id,
            "paciente_id": i.paciente_id,
            "tipo_evento": "INTERVENCAO",
            "data": i.data_intervencao.isoformat(),
            "descricao": i.descricao,
            "origem": "PROFISSIONAL",
            "usuario_id": i.profissional_id,
            "sono_qualidade": None,
            "irritabilidade": None,
            "crise_sensorial": None,
        })

    avaliacoes = db.execute(
        text("""
            SELECT
                ac.id,
                ac.registro_id,
                ac.instrumento,
                ac.score,
                ac.classificacao,
                ac.created_at
            FROM avaliacoes_clinicas ac
            JOIN registros_longitudinais rl
                ON rl.id = ac.registro_id
            WHERE rl.paciente_id = :paciente_id
            ORDER BY ac.created_at DESC
        """),
        {"paciente_id": paciente_id}
    ).fetchall()

    for a in avaliacoes:
        timeline.append({
            "id": a.id,
            "paciente_id": paciente_id,
            "tipo_evento": "AVALIACAO_CLINICA",
            "data": a.created_at.isoformat(),
            "descricao": (
                f"Aplicação do {a.instrumento}. "
                f"Score {a.score}. "
                f"Classificação: {a.classificacao}."
            ),
            "origem": "FRAMEWORK",
            "instrumento": a.instrumento,
            "score": a.score,
            "classificacao": a.classificacao,
        })

    timeline = sorted(
        timeline,
        key=lambda x: x["data"],
        reverse=True
    )

    return timeline


listar_timeline_paciente = obter_timeline_paciente

@router.get("/eventos/{tipo}/{evento_id}")
def visualizar_evento(
    tipo: str,
    evento_id: int,
    db: Session = Depends(get_db)
):
    return longitudinal_service.visualizar(
        db,
        tipo,
        evento_id
    )
