from dataclasses import dataclass, field
from typing import Any, Dict
from app.models.modular import FormularioModulo, CampoFormulario
from ..exceptions import (DailyRecordFormNotFound, AmbiguousDailyRecordForm,
                          InvalidDailyRecordPayload)


@dataclass
class PreparedRecord:
    form_id: int
    answers: Dict[int, Any]
    projection: Dict[str, Any] = field(default_factory=dict)


def resolve_form(db, line):
    forms = db.query(FormularioModulo).filter(
        FormularioModulo.modulo_id == line.module_id,
        FormularioModulo.tipo == 'REGISTRO_DIARIO',
        FormularioModulo.ativo.is_(True),
    ).order_by(FormularioModulo.id).all()
    if not forms:
        raise DailyRecordFormNotFound('Active Daily Record form not found.')
    if len(forms) != 1:
        raise AmbiguousDailyRecordForm('Multiple active Daily Record forms.')
    return forms[0]


def resolve_fields(db, form_id, values):
    fields = db.query(CampoFormulario).filter(
        CampoFormulario.formulario_id == form_id,
        CampoFormulario.ativo.is_(True),
        CampoFormulario.nome_campo.in_(list(values)),
    ).all()
    by_name = {}
    for item in fields:
        if item.nome_campo in by_name:
            raise InvalidDailyRecordPayload('Duplicate active field name in form.')
        by_name[item.nome_campo] = item.id
    if set(by_name) != set(values):
        raise InvalidDailyRecordPayload('Payload field is not active in selected form.')
    return {by_name[name]: value for name, value in values.items()}
