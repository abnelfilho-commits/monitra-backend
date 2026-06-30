from sqlalchemy.orm import Session

from app.models.avaliacao_clinica import AvaliacaoClinica
from app.services.clinical_engine.context import AssessmentContext


class AssessmentRepository:

    @staticmethod
    def salvar_avaliacao(
        db: Session,
        context: AssessmentContext,
        resultado: dict
    ) -> AvaliacaoClinica:

        avaliacao = AvaliacaoClinica(

            registro_id=context.registro_id,
            paciente_id=context.paciente_id,
            modulo_id=context.modulo_id,
            formulario_id=context.formulario_id,

            instrumento=resultado.get("instrumento"),
            versao=resultado.get("versao"),

            score=resultado.get("score"),
            score_texto=str(resultado.get("score")) if resultado.get("score") is not None else None,

            classificacao=resultado.get("classificacao"),
            classificacao_codigo=resultado.get("classificacao_codigo"),

            conduta=resultado.get("conduta"),
            interpretacao=resultado.get("interpretacao"),

            resultado=resultado,

            engine_version=resultado.get("metadata", {}).get("engine_version"),

            profissional_id=context.profissional_id,

            status="CONCLUIDA"
        )

        db.add(avaliacao)
        db.commit()
        db.refresh(avaliacao)

        return avaliacao