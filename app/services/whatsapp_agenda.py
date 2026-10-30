"""Transactional agenda management only. Never imports preparation or delivery.

All writers own the canonical transport/care/follow locks before locking agenda
rows. GET never repairs rows or classifies elapsed occurrences.
"""
import calendar
import os
from sqlalchemy import select
from app.models.whatsapp_agenda import WhatsAppAgendaCheckin as Occurrence, WhatsAppAgendaEvento as Event
from app.services.checkin_bem_estar import CheckinInvalid
from app.services.whatsapp_programacao import ZONE, aware, next_occurrence

MUTABLE = ('AGENDADO', 'BLOQUEADO', 'CANCELADO')


def horizon(today):
    return today.replace(year=today.year + 1,
                         day=min(today.day, calendar.monthrange(today.year + 1, today.month)[1]))


def slots(day, local_time, end, now):
    slot = next_occurrence(day, local_time, now)
    result = []
    while slot.astimezone(ZONE).date() <= end:
        result.append(slot)
        slot = next_occurrence(day, local_time, slot)
    return result


def impediments(db, follow):
    from app.services.whatsapp_comunicacao import blocked
    from app.services.whatsapp_autorizacao import require_prior_authorization
    from app.models.contexto_assistencial import ContextoAssistencial
    reasons = []
    if follow.status != 'ATIVO': reasons.append('FOLLOW_UP_' + follow.status)
    if follow.consentimento_status == 'REVOGADO': reasons.append('CONSENT_REVOKED')
    context = db.get(ContextoAssistencial, follow.contexto_assistencial_id)
    if context is None or not context.ativo or context.data_fim is not None:
        reasons.append('CONTEXT_CLOSED')
    if not follow.programacao_ativa: reasons.append('SCHEDULE_PAUSED')
    emitter = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '')
    if not emitter:
        reasons.append('TRANSPORT_UNAVAILABLE')
    elif blocked(db, emitter, follow.telefone, follow_id=follow.id):
        reasons.append('WHATSAPP_INTERROMPIDO')
    try:
        require_prior_authorization(db, follow)
    except CheckinInvalid as exc:
        reasons.append(str(exc))
    return reasons


def future_rows(db, follow, now):
    return list(db.scalars(select(Occurrence).where(
        Occurrence.acompanhamento_id == follow.id, Occurrence.previsto_em > now)
        .order_by(Occurrence.id).with_for_update().execution_options(populate_existing=True)))


def mutable(row):
    return (row.status in MUTABLE and row.conversa_id is None
            and row.processamento_iniciado_em is None and row.processado_em is None)


def event(db, follow, now, reason, actor=None, row=None, previous=None, configuration=None):
    db.add(Event(acompanhamento_id=follow.id, ocorrencia_id=row.id if row else None,
        programacao_versao=follow.programacao_versao, usuario_id=actor,
        origem='CONFIGURACAO' if configuration else 'GESTAO', motivo=reason,
        estado_anterior=previous, estado_novo=row.status if row else None,
        configuracao=configuration, criado_em=now))


def transition(db, follow, row, status, reason, now, actor=None):
    previous = row.status
    if previous == status and row.motivo_estado == reason and row.programacao_versao == follow.programacao_versao:
        return
    row.status, row.motivo_estado = status, reason
    row.programacao_versao, row.atualizado_em = follow.programacao_versao, now
    event(db, follow, now, reason, actor, row, previous)


def invalidate(db, follow, *, reason, actor=None, cancel=False):
    """Same-transaction lifecycle/ledger hook; no fan-out on preventive STOP."""
    if follow.programacao_data_fim is None:
        return
    from app.services.whatsapp_mental import now_utc
    now = now_utc(db)
    for row in future_rows(db, follow, now):
        if mutable(row) and row.status != 'CANCELADO':
            transition(db, follow, row, 'CANCELADO' if cancel else 'BLOQUEADO', reason, now, actor)
    follow.proximo_envio_em = None
    db.flush()


def configure(db, follow, payload, actor):
    """Called only after authorization and canonical locks by /programacao."""
    from app.services.whatsapp_mental import now_utc
    now = aware(now_utc(db))
    end = payload.programacao_data_fim
    if 'programacao_data_fim' not in payload.model_fields_set:
        end = follow.programacao_data_fim
    if end is None:
        raise CheckinInvalid('AGENDA_END_REQUIRED')
    preference = (payload.dia_semana, payload.horario_local, payload.programacao_ativa, end)
    current = (follow.dia_semana, follow.horario_local, follow.programacao_ativa, follow.programacao_data_fim)
    # Strict optimistic concurrency, including retries: callers refresh on 409.
    if payload.versao_esperada is None or payload.versao_esperada != follow.programacao_versao:
        raise CheckinInvalid('SCHEDULE_VERSION_CONFLICT')
    if preference == current:
        return follow
    today = now.astimezone(ZONE).date()
    if end > horizon(today) or (end < today and end != follow.programacao_data_fim):
        raise CheckinInvalid('AGENDA_END_OUT_OF_RANGE')
    desired = slots(payload.dia_semana, payload.horario_local, end, now)
    if payload.programacao_ativa and not desired:
        raise CheckinInvalid('AGENDA_NO_FUTURE_OCCURRENCES')
    follow.dia_semana, follow.horario_local, follow.programacao_ativa, follow.programacao_data_fim = preference
    follow.programacao_versao += 1
    follow.configurado_por_usuario_id = actor
    reasons = impediments(db, follow)
    status = 'BLOQUEADO' if reasons else 'AGENDADO'
    reason = reasons[0] if reasons else 'PROGRAMACAO'
    rows = future_rows(db, follow, now)
    by_instant = {aware(row.previsto_em): row for row in rows}
    desired_set = set(desired)
    for row in rows:
        if mutable(row) and aware(row.previsto_em) not in desired_set:
            transition(db, follow, row, 'CANCELADO', 'REPROGRAMACAO', now, actor)
    for instant in desired:
        row = by_instant.get(instant)
        if row is None:
            row = Occurrence(acompanhamento_id=follow.id, previsto_em=instant,
                status=status, motivo_estado=reason, programacao_versao=follow.programacao_versao,
                criado_em=now, atualizado_em=now)
            db.add(row); db.flush()
            event(db, follow, now, reason, actor, row)
            rows.append(row)
        elif mutable(row):
            transition(db, follow, row, status, reason, now, actor)
    follow.proximo_envio_em = min((r.previsto_em for r in rows
        if r.status == 'AGENDADO' and r.previsto_em in desired_set and mutable(r)), default=None)
    event(db, follow, now, 'PROGRAMACAO', actor, configuration={
        'dia_semana': follow.dia_semana, 'horario_local': follow.horario_local.isoformat(),
        'programacao_ativa': follow.programacao_ativa, 'programacao_data_fim': end.isoformat()})
    db.flush()
    return follow


def read(db, scope, *, limit=50, offset=0):
    from app.services.whatsapp_mental import WhatsAppMentalService
    follow = WhatsAppMentalService().read(db, **scope)
    if follow is None:
        raise CheckinInvalid('FOLLOW_UP_NOT_FOUND')
    rows = list(db.scalars(select(Occurrence).where(Occurrence.acompanhamento_id == follow.id)
        .order_by(Occurrence.previsto_em, Occurrence.id).offset(offset).limit(limit + 1)))
    fields = ('id', 'previsto_em', 'status', 'programacao_versao', 'conversa_id',
              'criado_em', 'atualizado_em', 'processamento_iniciado_em', 'processado_em', 'motivo_estado')
    return dict(acompanhamento_id=follow.id, programacao_versao=follow.programacao_versao,
        execucao_automatica_ativa=False, impedimentos=impediments(db, follow),
        itens=[{key: getattr(row, key) for key in fields} for row in rows[:limit]],
        limite=limit, offset=offset, proximo_offset=offset + limit if len(rows) > limit else None)
