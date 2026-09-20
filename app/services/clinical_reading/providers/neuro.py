"""Translate the existing Neuro result without recalculating clinical rules."""
from sqlalchemy.orm import Session

from app.services import neuro_engine
from app.services.care_lines import CareLineDefinition
from ..models import ClinicalReading


def read_neuro(db: Session, patient_id: int, care_line: CareLineDefinition) -> ClinicalReading:
    raw = neuro_engine.analisar_paciente(db, patient_id)
    return from_raw(patient_id, care_line, raw)


def read_neuro_many(db, patient_ids, care_line):
    grouped = {pid: [] for pid in patient_ids}
    for record in neuro_engine.obter_registros_neuro_pacientes(db, patient_ids):
        grouped[record.paciente_id].append(record)
    return {pid: from_raw(pid, care_line, neuro_engine.analisar_registros(records))
            for pid, records in grouped.items()}


def from_raw(patient_id, care_line, raw):
    axis = raw.get("eixo_dominante")
    return ClinicalReading(
        patient_id=patient_id,
        care_line=care_line,
        reference_date=raw["ultimo_registro"],
        risk=raw["risco_atual"],
        trend=raw["tendencia"],
        summary=raw["resumo_clinico"],
        clinical_state=raw["momento_clinico"],
        # This is axis support, explicitly not a risk-score explanation.
        evidence={"scope": "axis_analysis", "base_sustentacao": axis["base_sustentacao"]}
        if axis and axis.get("base_sustentacao") else None,
        alerts=raw["alertas"],
        metadata={
            "source": "neuro_engine.analisar_paciente",
            **{key: raw[key] for key in (
                "pontuacao_risco", "protocolo", "prioridade", "eixo_dominante",
                "painel_clinico", "total_registros", "status_resumido", "interpretacao",
            )},
        },
    )
