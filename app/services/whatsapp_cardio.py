"""Cardio transport questionnaire: existing four measurements and approved text.

No scoring or clinical thresholds here. Blank measurement uses explicit 'pular'.
"""
from decimal import Decimal, InvalidOperation
import math

FIELDS = (
    ('glicemia_jejum', 'Informe a glicemia em jejum (mg/dL), ou pular.'),
    ('pressao_sistolica', 'Informe a pressão sistólica (mmHg), ou pular.'),
    ('pressao_diastolica', 'Informe a pressão diastólica (mmHg), ou pular.'),
    ('peso', 'Informe o peso (kg), ou pular.'),
    ('observacoes', 'Informe observações gerais complementares, ou pular.'),
)


def start(db, conversation, reference_date):
    conversation.data_referencia = reference_date
    conversation.respostas_json = {}
    conversation.etapa_atual = 'CARDIO_0'
    db.flush()
    return FIELDS[0][1]


def step(db, conversation, message, responsible, save):
    position = int(conversation.etapa_atual.split('_')[1])
    if position == len(FIELDS):
        if message.strip() == '2':
            conversation.etapa_atual = 'INICIO'
            conversation.paciente_id = None
            conversation.data_referencia = None
            conversation.respostas_json = {}
            db.flush()
            return 'Registro cancelado.'
        if message.strip() != '1':
            return '1 - Confirmar envio\n2 - Cancelar'
        result = save(db, responsible.id, conversation.paciente_id, conversation.care_line,
                      conversation.data_referencia, dict(conversation.respostas_json))
        conversation.etapa_atual = 'INICIO'
        conversation.paciente_id = None
        conversation.data_referencia = None
        conversation.respostas_json = {}
        db.flush()
        return 'Acompanhamento enviado com sucesso. Registro #{}'.format(result.record_id)
    name, prompt = FIELDS[position]
    value = None
    if message.strip().casefold() != 'pular':
        if name == 'observacoes':
            value = message  # Complementary text is preserved, never interpreted.
        else:
            try:
                number = Decimal(message.strip().replace(',', '.'))
                value = float(number)
                if not number.is_finite() or not math.isfinite(value):
                    raise ValueError()
            except (InvalidOperation, ValueError, OverflowError):
                return prompt
    values = dict(conversation.respostas_json)
    values[name] = value
    conversation.respostas_json = values
    conversation.etapa_atual = 'CARDIO_{}'.format(position + 1)
    db.flush()
    return FIELDS[position + 1][1] if position + 1 < len(FIELDS) else '1 - Confirmar envio\n2 - Cancelar'
