from app.services.clinical_engine.assessments.mchat_engine import MChatEngine

from app.services.clinical_engine.assessments.denver_engine import DenverEngine

from app.services.clinical_engine.assessments.phq9_engine import PHQ9Engine

ASSESSMENT_ENGINES = {
    "PHQ9": PHQ9Engine(),
    "MCHAT": MChatEngine(),
    "DENVER": DenverEngine(),
}


def get_assessment_engine(instrumento: str):
    instrumento = instrumento.upper()

    engine = ASSESSMENT_ENGINES.get(instrumento)

    if not engine:
        raise ValueError(f"Instrumento clínico não registrado: {instrumento}")

    return engine