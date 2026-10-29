"""Civil weekly preferences only. No executor, transport or technical identity."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('America/Cuiaba')
LATE_WINDOW = timedelta(hours=2)


def aware(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('An aware instant is required')
    return value.astimezone(timezone.utc)


def next_occurrence(day, local_time, now, *, allow_late=False):
    """Strictly future for config/resume; optionally retain an unexpired due slot.

    Call after processing with allow_late=False: lateness never shifts civil time.
    Missed weeks are skipped, never accumulated. All comparisons use UTC.
    """
    now = aware(now)
    if not 0 <= day <= 6 or local_time.tzinfo is not None:
        raise ValueError('Invalid weekly preference')
    local = now.astimezone(ZONE)
    date = local.date() - timedelta(days=(local.weekday() - day) % 7)
    slot = datetime.combine(date, local_time, tzinfo=ZONE).astimezone(timezone.utc)
    if allow_late and slot <= now <= slot + LATE_WINDOW:
        return slot
    return datetime.combine(date + timedelta(days=7), local_time, tzinfo=ZONE).astimezone(timezone.utc) if slot <= now else slot


def due_in_window(follow, now):
    """Temporal eligibility only, NOT authorization or permission to send."""
    if not follow.programacao_ativa or follow.dia_semana is None or follow.proximo_envio_em is None:
        return False
    slot = aware(follow.proximo_envio_em)
    return slot <= aware(now) <= slot + LATE_WINDOW


def configure(db, payload, **scope):
    from sqlalchemy import select
    from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow
    from app.services.whatsapp_mental import WhatsAppMentalService, locked, now_utc
    from app.services.whatsapp_comunicacao import coordinate_configured
    from app.services.checkin_bem_estar import CheckinInvalid

    service = WhatsAppMentalService()
    # Authorize before disclosing existence; revalidate under canonical locks.
    service.authorized(db, write=False, **scope)
    initial = db.scalar(select(Follow).where(Follow.contexto_assistencial_id == scope['context']))
    if initial is None:
        raise CheckinInvalid('FOLLOW_UP_NOT_FOUND')
    phone = initial.telefone
    coordinate_configured(db, (phone,))
    service.authorized(db, **scope)
    follow = locked(db, Follow, initial.id)
    if follow.telefone != phone:
        raise CheckinInvalid('DESTINATION_CHANGED')
    if follow.status == 'ENCERRADO' or follow.consentimento_status == 'REVOGADO':
        raise CheckinInvalid('FOLLOW_UP_CLOSED')
    preference = (payload.dia_semana, payload.horario_local, payload.programacao_ativa)
    if (preference == (follow.dia_semana, follow.horario_local, follow.programacao_ativa)
            and (not payload.programacao_ativa or follow.proximo_envio_em is not None)):
        return follow  # An identical retry must not move an overdue occurrence.
    # Existing destination changes clear the date; an explicit save can restore it.
    follow.dia_semana, follow.horario_local, follow.programacao_ativa = preference
    follow.configurado_por_usuario_id = scope['actor']
    follow.proximo_envio_em = next_occurrence(payload.dia_semana, payload.horario_local, now_utc(db)) if payload.programacao_ativa else None
    db.flush()
    return follow
