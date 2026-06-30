from sqlalchemy.orm import Session

from app.services.clinical_engine.context import AssessmentContext
from app.services.clinical_engine.registry import get_assessment_engine
from app.services.clinical_engine.assessment_builder import AssessmentBuilder
from app.services.clinical_engine.assessment_repository import AssessmentRepository
from app.services.clinical_engine.constants import get_assessment_label

def executar_avaliacao_clinica(
    context: AssessmentContext
) -> dict:

    engine = get_assessment_engine(context.instrumento)

    return engine.executar(context)


def executar_avaliacao_por_registro(
    db: Session,
    registro_id: int,
    instrumento: str
) -> dict:

    context = AssessmentBuilder.from_registro(
        db=db,
        registro_id=registro_id,
        instrumento=instrumento
    )

    resultado = executar_avaliacao_clinica(context)
    
    resultado["instrumento_label"] = get_assessment_label(
        resultado["instrumento"]
)

    avaliacao = AssessmentRepository.salvar_avaliacao(
        db=db,
        context=context,
        resultado=resultado
    )

    return {
        "avaliacao_id": avaliacao.id,
        "resultado": resultado
    }