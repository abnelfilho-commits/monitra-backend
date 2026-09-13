"""Current Cardio reading from current-record answers and the domain engine.

Only checked-in modular tables are required. Legacy direct columns and persisted
interpretations are intentionally not mixed into this observation.
"""
from math import isfinite
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.modular import CampoFormulario, FormularioModulo, RegistroLongitudinal, RespostaRegistro
from app.services import cardiometabolico_engine as engine
from app.services.care_lines import CareLineDefinition
from ..models import ClinicalReading

NUMERIC_FIELDS = {"glicemia_jejum", "pressao_sistolica", "pressao_diastolica", "peso"}
TEXT_FIELDS = {"atividade_fisica", "sono", "humor"}


def read_cardio(db: Session, patient_id: int, care_line: CareLineDefinition) -> ClinicalReading:
    record = (
        db.query(RegistroLongitudinal)
        .join(FormularioModulo, FormularioModulo.id == RegistroLongitudinal.formulario_id)
        .filter(
            RegistroLongitudinal.paciente_id == patient_id,
            RegistroLongitudinal.modulo_id == care_line.module_id,
            FormularioModulo.modulo_id == care_line.module_id,
            FormularioModulo.tipo == "REGISTRO_DIARIO",
        )
        .order_by(RegistroLongitudinal.data_registro.desc(), RegistroLongitudinal.id.desc())
        .first()
    )
    metadata: Dict[str, Any] = {
        "source": "respostas_registro",
        "engine": "cardiometabolico_engine",
        "trend_availability": "unavailable_pending_clinical_validation",
    }
    if record is None:
        metadata["availability"] = "no_record"
        return ClinicalReading(patient_id, care_line, None, None, None, None, metadata)

    metadata["record_id"] = record.id
    rows = (
        db.query(CampoFormulario.nome_campo, RespostaRegistro.valor_numero, RespostaRegistro.valor_texto)
        .join(RespostaRegistro, RespostaRegistro.campo_id == CampoFormulario.id)
        .filter(
            RespostaRegistro.registro_id == record.id,
            CampoFormulario.formulario_id == record.formulario_id,
            CampoFormulario.nome_campo.in_(NUMERIC_FIELDS | TEXT_FIELDS),
        )
        .all()
    )
    measurements: Dict[str, Any] = {}
    seen = set()
    invalid = False
    for name, number, text_value in rows:
        if name in seen:
            invalid = True  # Never arbitrarily choose between duplicate answers.
        seen.add(name)
        if name in NUMERIC_FIELDS:
            if number is not None:
                value = float(number)
                if isfinite(value):
                    measurements[name] = value
                else:
                    invalid = True
            elif text_value is not None:
                invalid = True
        elif text_value is not None and text_value.strip():
            measurements[name] = text_value  # Preserve exact domain values.
        elif number is not None:
            invalid = True

    metadata["measurements"] = measurements
    if invalid or not measurements:
        metadata["availability"] = "invalid_answers" if invalid else "no_usable_answers"
        return ClinicalReading(patient_id, care_line, record.data_registro, None, None, None, metadata)

    score = engine.calcular_score(measurements)
    metadata.update({
        "availability": "available",
        "score": score,
        "protocol": engine.definir_protocolo(score),
    })
    return ClinicalReading(
        patient_id=patient_id,
        care_line=care_line,
        reference_date=record.data_registro,
        risk=engine.classificar_risco(score),
        trend=None,
        summary=engine.gerar_leitura_clinica(measurements, score),
        metadata=metadata,
    )
