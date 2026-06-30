from app.services.clinical_engine.assessments.mchat_engine import MChatEngine

from app.services.clinical_engine.assessments.denver_engine import DenverEngine

ASSESSMENT_ENGINES = {
    "MCHAT": MChatEngine(),
    "DENVER": DenverEngine(),
}


def get_assessment_engine(instrumento: str):
    instrumento = instrumento.upper()

    engine = ASSESSMENT_ENGINES.get(instrumento)

    if not engine:
        raise ValueError(f"Instrumento clínico não registrado: {instrumento}")

    return engine