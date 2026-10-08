"""Bounded planning using the unchanged canonical scheduling date distribution."""
from datetime import date
from app.services.scheduling_engine import SchedulingEngine
from app.services.scheduling_models import PlanejamentoAssistencial


def planned_quantity(start: date, end: date, frequency: int, duration: int, manual=None):
    if end < start:
        raise ValueError('Data final deve ser igual ou posterior à inicial.')
    if frequency <= 0 or duration <= 0:
        raise ValueError('Informe frequência e duração positivas.')
    # Upper bound, followed by the actual canonical generator (including float/floor behavior).
    bound = ((end-start).days + 1) * frequency // 7 + frequency + 1
    if bound > 100000:
        raise ValueError('Período e frequência excedem o limite de 100000 ocorrências por planejamento.')
    generated = SchedulingEngine.generate_sessions(PlanejamentoAssistencial(start,bound,frequency,duration))
    maximum = sum(item.data_agendada <= end for item in generated)
    if manual is not None and (manual < 1 or manual > maximum):
        raise ValueError(f'Quantidade manual deve estar entre 1 e {maximum} para o período e frequência.')
    return dict(quantidade_sessoes=manual if manual is not None else maximum,
                quantidade_calculada=maximum, origem_quantidade='MANUAL' if manual is not None else 'CALCULADA')
