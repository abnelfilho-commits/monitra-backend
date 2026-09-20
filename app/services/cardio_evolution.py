"""Factual trajectories from same-observation answers; no risk or trend rules."""
from math import isfinite
from sqlalchemy import func
from app.models.modular import RegistroLongitudinal as Record, FormularioModulo as Form
from app.models.modular import CampoFormulario as Field, RespostaRegistro as Answer

FIELDS = {'glicemia_jejum', 'pressao_sistolica', 'pressao_diastolica', 'peso', 'altura'}


def project_observation(record, answers):
    values, labels, seen = {}, {}, set()
    for name, label, number, text_value in answers:
        if name in seen:
            values[name] = None
            labels[name] = None
            continue
        seen.add(name)
        value = float(number) if number is not None else None
        values[name] = value if value is not None and isfinite(value) and text_value is None else None
        labels[name] = (label or '').strip().casefold()
    weight, height = values.get('peso'), values.get('altura')
    # Only explicit field units attest a dimensional calculation. No inferred units
    # from magnitude, patient height, other records, or internal field names.
    height_unit = {'altura (m)': 'm', 'altura (cm)': 'cm'}.get(labels.get('altura'))
    eligible = (labels.get('peso') == 'peso (kg)' and height_unit is not None
                and weight is not None and height is not None and weight > 0 and height > 0)
    meters = height / 100 if eligible and height_unit == 'cm' else height
    bmi = round(weight / (meters * meters), 1) if eligible else None
    return {'record_id': record.id, 'patient_id': record.paciente_id,
            'data': record.data_registro.isoformat(), 'origem': record.origem,
            **{name: values.get(name) for name in FIELDS - {'altura'}},
            'altura': meters if eligible else None, 'imc': bmi,
            'imc_availability': 'available' if eligible else 'unavailable_same_observation_units_required',
            'source': 'respostas_registro',
            'imc_units': {'peso': 'kg', 'altura': height_unit} if eligible else None}


def evolution(db, patient_ids, module_id, latest_only=False):
    if not patient_ids:
        return []
    query = db.query(Record).join(Form, Form.id == Record.formulario_id).filter(
        Record.paciente_id.in_(patient_ids), Record.modulo_id == module_id,
        Form.modulo_id == module_id, Form.tipo == 'REGISTRO_DIARIO')
    if latest_only:
        ranked = query.with_entities(Record.id.label('id'), func.row_number().over(
            partition_by=Record.paciente_id, order_by=(Record.data_registro.desc(), Record.id.desc())).label('pos')).subquery()
        query = db.query(Record).join(ranked, ranked.c.id == Record.id).filter(ranked.c.pos == 1)
    records = query.order_by(Record.data_registro, Record.id).all()
    if not records:
        return []
    rows = (db.query(Answer.registro_id, Field.nome_campo, Field.label, Answer.valor_numero, Answer.valor_texto)
        .join(Field, Field.id == Answer.campo_id).join(Record, Record.id == Answer.registro_id)
        .filter(Answer.registro_id.in_([r.id for r in records]), Field.formulario_id == Record.formulario_id,
                Field.nome_campo.in_(FIELDS)).all())
    grouped = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(tuple(row[1:]))
    return [project_observation(record, grouped.get(record.id, [])) for record in records]
