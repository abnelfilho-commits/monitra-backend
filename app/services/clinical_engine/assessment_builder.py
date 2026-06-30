from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.clinical_engine.context import AssessmentContext


class AssessmentBuilder:

    @staticmethod
    def from_registro(
        db: Session,
        registro_id: int,
        instrumento: str
    ) -> AssessmentContext:

        registro = db.execute(
            text("""
                SELECT
                    id,
                    paciente_id,
                    modulo_id,
                    formulario_id,
                    criado_por_usuario_id,
                    data_registro
                FROM registros_longitudinais
                WHERE id = :registro_id
            """),
            {
                "registro_id": registro_id
            }
        ).fetchone()

        if not registro:
            raise ValueError(
                f"Registro longitudinal {registro_id} não encontrado."
            )

        respostas_db = db.execute(
            text("""
                SELECT
                    cf.nome_campo,
                    rr.valor_texto,
                    rr.valor_numero,
                    rr.valor_booleano

                FROM respostas_registro rr

                JOIN campos_formulario cf
                    ON cf.id = rr.campo_id

                WHERE rr.registro_id = :registro_id
            """),
            {
                "registro_id": registro_id
            }
        ).fetchall()

        respostas = {}

        for row in respostas_db:

            valor = (
                row.valor_texto
                if row.valor_texto is not None
                else row.valor_numero
                if row.valor_numero is not None
                else row.valor_booleano
            )

            respostas[row.nome_campo] = valor

        return AssessmentContext(

            registro_id=registro.id,

            instrumento=instrumento,

            respostas=respostas,

            paciente_id=registro.paciente_id,

            modulo_id=registro.modulo_id,

            profissional_id=registro.criado_por_usuario_id,

            formulario_id=registro.formulario_id,

            data_registro=str(registro.data_registro)

            if registro.data_registro

            else None
        )