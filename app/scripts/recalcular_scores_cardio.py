from sqlalchemy import text
from app.database import SessionLocal

from app.services.cardiometabolico_engine import (
    calcular_score,
    classificar_risco,
    definir_protocolo,
    gerar_leitura_clinica,
)

db = SessionLocal()

rows = db.execute(text("""
    SELECT id
    FROM registros_longitudinais
    WHERE modulo_id = 2
""")).fetchall()

for row in rows:

    registro_id = row.id

    respostas = db.execute(text("""
        SELECT
            c.nome_campo,
            r.valor_numero,
            r.valor_texto
        FROM respostas_registro r
        JOIN campos_formulario c
          ON c.id = r.campo_id
        WHERE r.registro_id = :registro_id
    """), {
        "registro_id": registro_id
    }).fetchall()

    dados = {}

    for r in respostas:

        valor = (
            r.valor_numero
            if r.valor_numero is not None
            else r.valor_texto
        )

        dados[r.nome_campo] = valor

    score = calcular_score(dados)

    risco = classificar_risco(score)

    protocolo = definir_protocolo(score)

    leitura = gerar_leitura_clinica(
        dados,
        score
    )

    db.execute(text("""
        UPDATE registros_longitudinais
        SET
            score_clinico = :score,
            risco = :risco,
            protocolo = :protocolo,
            leitura_clinica = :leitura
        WHERE id = :registro_id
    """), {
        "score": score,
        "risco": risco,
        "protocolo": protocolo,
        "leitura": leitura,
        "registro_id": registro_id
    })

db.commit()

print("Scores recalculados com sucesso.")