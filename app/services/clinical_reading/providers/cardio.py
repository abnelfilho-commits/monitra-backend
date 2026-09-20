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
    rows = [] if record is None else (
        db.query(CampoFormulario.nome_campo, RespostaRegistro.valor_numero, RespostaRegistro.valor_texto)
        .join(RespostaRegistro, RespostaRegistro.campo_id == CampoFormulario.id)
        .filter(
            RespostaRegistro.registro_id == record.id,
            CampoFormulario.formulario_id == record.formulario_id,
            CampoFormulario.nome_campo.in_(NUMERIC_FIELDS | TEXT_FIELDS),
        )
        .all()
    )
    return reading_from_observation(patient_id, care_line, record, rows)


def reading_from_observation(patient_id, care_line, record, rows):
    metadata: Dict[str, Any] = {
        "source": "respostas_registro",
        "engine": "cardiometabolico_engine",
        "trend_availability": "unavailable_pending_clinical_validation",
    }
    if record is None:
        metadata["availability"] = "no_record"
        return ClinicalReading(patient_id, care_line, None, None, None, None, metadata)

    metadata["record_id"] = record.id
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


def read_cardio_many(db, patient_ids, care_line):
    """Same current-reading translation, two queries regardless of patient count."""
    from sqlalchemy import func
    if not patient_ids:
        return {}
    ranked = (db.query(RegistroLongitudinal.id.label('id'), func.row_number().over(
        partition_by=RegistroLongitudinal.paciente_id,
        order_by=(RegistroLongitudinal.data_registro.desc(), RegistroLongitudinal.id.desc())).label('position'))
        .join(FormularioModulo, FormularioModulo.id == RegistroLongitudinal.formulario_id)
        .filter(RegistroLongitudinal.paciente_id.in_(patient_ids),
                RegistroLongitudinal.modulo_id == care_line.module_id,
                FormularioModulo.modulo_id == care_line.module_id,
                FormularioModulo.tipo == 'REGISTRO_DIARIO').subquery())
    records = db.query(RegistroLongitudinal).join(ranked, ranked.c.id == RegistroLongitudinal.id).filter(ranked.c.position == 1).all()
    by_patient = {r.paciente_id: r for r in records}
    answers = {}
    if records:
        rows = (db.query(RespostaRegistro.registro_id, CampoFormulario.nome_campo,
                        RespostaRegistro.valor_numero, RespostaRegistro.valor_texto)
            .join(CampoFormulario, CampoFormulario.id == RespostaRegistro.campo_id)
            .join(RegistroLongitudinal, RegistroLongitudinal.id == RespostaRegistro.registro_id)
            .filter(RespostaRegistro.registro_id.in_([r.id for r in records]),
                    CampoFormulario.formulario_id == RegistroLongitudinal.formulario_id,
                    CampoFormulario.nome_campo.in_(NUMERIC_FIELDS | TEXT_FIELDS)).all())
        for row in rows:
            answers.setdefault(row[0], []).append(tuple(row[1:]))
    return {pid: reading_from_observation(pid, care_line, by_patient.get(pid),
            answers.get(by_patient[pid].id, []) if pid in by_patient else []) for pid in patient_ids}
