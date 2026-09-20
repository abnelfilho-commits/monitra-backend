"""Legacy Neuro report boundary. Not the institutional Multi-Line reading API.

Keep the existing raw shape, errors and behavior until Report Engine integration.
No Cardio report capability is advertised by this compatibility mapping.
"""
from app.services import neuro_engine


def get_neuro_reading(db, patient_id):
    return neuro_engine.analisar_paciente(db=db, paciente_id=patient_id)


REPORT_READERS = {"NEURO": get_neuro_reading}


def build_report_context(db, patient_id, module):
    module = (module or "").upper()
    reader = REPORT_READERS.get(module)
    if reader is None:
        raise ValueError(f"Módulo clínico não suportado: {module}")
    return reader(db, patient_id)
