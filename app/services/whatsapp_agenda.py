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
        execucao_automatica_ativa=automation_active(db, follow), impedimentos=impediments(db, follow),
        itens=[{key: getattr(row, key) for key in fields} for row in rows[:limit]],
        limite=limit, offset=offset, proximo_offset=offset + limit if len(rows) > limit else None)


# Weekly execution stays in the existing agenda service. No public executor API.
from dataclasses import dataclass
from datetime import timedelta
from sqlalchemy import func, text, and_, or_, case, event as sqlalchemy_event
from app.models.whatsapp_agenda import WhatsAppExecutorHabilitacao as Grant

IDENTITY = 'EXECUTOR_SEMANAL_MENTAL'


def executor_enabled():
    return os.getenv('WHATSAPP_WEEKLY_EXECUTOR_ENABLED', '').lower() == 'true'


def latest_grant(db, institution):
    return db.scalar(select(Grant).where(Grant.instituicao_id == institution)
        .order_by(Grant.id.desc()).limit(1).execution_options(populate_existing=True))


def set_executor_grant(db, *, institution, actor, enabled, reason):
    """Explicit administrative command, caller commits. No HTTP route or auto-grant."""
    from app.services.permissao_assistencial import PermissaoAssistencialService
    from app.services.autorizacao_institucional import AutorizacaoInstitucionalService
    if type(enabled) is not bool or not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 160:
        raise CheckinInvalid('INVALID_EXECUTOR_GRANT')
    permissions = PermissaoAssistencialService()
    permissions._gate(db, actor, institution, admin=True)
    AutorizacaoInstitucionalService().authorize(db, actor, institution)
    old = latest_grant(db, institution)
    if old is not None and old.habilitado == enabled:
        return old
    row = Grant(instituicao_id=institution, usuario_id=actor, habilitado=enabled,
                identidade=IDENTITY, motivo=reason.strip())
    db.add(row); db.flush()
    return row


@dataclass(frozen=True)
class WeeklyExecution:
    occurrence: int
    institution: int
    grant: int
    version: int


def authorize_weekly(db, execution, follow, *, conversation=None):
    """Typed internal capability PLUS live DB proofs, never a trusted boolean."""
    from app.models.contexto_assistencial import ContextoAssistencial
    from app.models.institucional import Instituicao
    from app.services.whatsapp_mental import now_utc
    from app.services.whatsapp_runtime import require_active
    if type(execution) is not WeeklyExecution or not executor_enabled():
        raise CheckinInvalid('WEEKLY_EXECUTION_NOT_ENABLED')
    context = db.get(ContextoAssistencial, follow.contexto_assistencial_id, populate_existing=True)
    institution = db.get(Instituicao, execution.institution, populate_existing=True)
    grant = latest_grant(db, execution.institution)
    row = db.get(Occurrence, execution.occurrence, populate_existing=True)
    if (context is None or context.instituicao_id != execution.institution or not institution or not institution.ativo
            or not grant or not grant.habilitado or grant.id != execution.grant
            or not row or row.acompanhamento_id != follow.id
            or row.programacao_versao != execution.version or follow.programacao_versao != execution.version
            or follow.programacao_data_fim is None or impediments(db, follow)):
        raise CheckinInvalid('WEEKLY_AUTHORIZATION_DENIED')
    require_active(db)
    now = aware(now_utc(db))
    if not row.previsto_em <= now <= row.previsto_em + timedelta(hours=2):
        raise CheckinInvalid('WEEKLY_OUTSIDE_WINDOW')
    if conversation is None:
        if row.status != 'AGENDADO' or not mutable(row):
            raise CheckinInvalid('WEEKLY_ALREADY_CLAIMED')
    elif (row.status != 'PROCESSANDO' or row.conversa_id != conversation.id
            or conversation.acompanhamento_whatsapp_id != follow.id
            or conversation.contexto_assistencial_id != context.id
            or conversation.telefone != follow.telefone):
        raise CheckinInvalid('WEEKLY_CONVERSATION_MISMATCH')
    return context


def authorize_delivery(db, execution, follow, conversation):
    context = authorize_weekly(db, execution, follow, conversation=conversation)
    return dict(context=context.id, institution=execution.institution, actor=None)


def execution_event(db, follow, row, status, reason, now, grant=None):
    previous = row.status
    if previous == status and row.motivo_estado == reason:
        return
    row.status, row.motivo_estado, row.atualizado_em = status, reason, now
    db.add(Event(acompanhamento_id=follow.id, ocorrencia_id=row.id,
        programacao_versao=row.programacao_versao, usuario_id=None, origem=IDENTITY,
        motivo=reason, estado_anterior=previous, estado_novo=status, criado_em=now,
        configuracao={'habilitacao_id': grant} if grant is not None else None))


def advance_next(db, follow):
    db.flush()
    follow.proximo_envio_em = db.scalar(select(func.min(Occurrence.previsto_em)).where(
        Occurrence.acompanhamento_id == follow.id, Occurrence.status == 'AGENDADO',
        Occurrence.programacao_versao == follow.programacao_versao)) if follow.programacao_ativa else None


def execute_occurrence(db, identity):
    """One attempt only. Parent locks serialize with configuration and lifecycle."""
    from app.services.whatsapp_mental import WhatsAppMentalService, Follow, lock_care, locked, now_utc
    from app.services.whatsapp_comunicacao import coordinate_configured
    if not executor_enabled():
        return
    row = db.get(Occurrence, identity)
    if row is None: return
    follow = db.get(Follow, row.acompanhamento_id)
    phone, follow_id = follow.telefone, follow.id
    coordinate_configured(db, (phone,))
    context, _, _ = lock_care(db, follow.contexto_assistencial_id)
    follow = locked(db, Follow, follow_id)
    # Parent lock protects the candidate; acquire occurrence row only after prepare's conversation locks.
    row = db.get(Occurrence, identity, populate_existing=True)
    if row.status != 'AGENDADO' or not mutable(row):
        db.rollback(); return
    grant = latest_grant(db, context.instituicao_id)
    if not grant or not grant.habilitado:
        db.rollback(); return
    now = aware(now_utc(db))
    if row.previsto_em > now:
        db.rollback(); return
    reason = None
    if follow.telefone != phone or row.programacao_versao != follow.programacao_versao:
        reason = 'SCHEDULE_CHANGED'
    elif now > row.previsto_em + timedelta(hours=2):
        reason = 'WINDOW_EXPIRED'
    execution = WeeklyExecution(identity, context.instituicao_id, grant.id, row.programacao_versao)
    conversation = None
    if reason is None:
        try:
            authorize_weekly(db, execution, follow)
            conversation = WhatsAppMentalService().prepare(db, follow.id, weekly=execution)
            if conversation is None: reason = 'NOT_ELIGIBLE'
        except CheckinInvalid:
            reason = 'WEEKLY_AUTHORIZATION_DENIED'
    row = locked(db, Occurrence, identity)
    if reason:
        execution_event(db, follow, row, 'PERDIDO' if reason == 'WINDOW_EXPIRED' else 'BLOQUEADO', reason, now, grant.id)
    else:
        row.conversa_id = conversation.id
        row.processamento_iniciado_em = now
        execution_event(db, follow, row, 'PROCESSANDO', 'CLAIMED', now, grant.id)
    advance_next(db, follow)
    db.commit()  # Claim and conversation durable before transport. Never resend this occurrence.
    if conversation is not None:
        try:
            WhatsAppMentalService().deliver_invitation(db, conversation.id, context=execution)
        except Exception:
            db.rollback()  # Transport owns uncertainty. Reconcile evidence, never retry delivery.
        reconcile_occurrence(db, identity, immediate=True)


def reconcile_occurrence(db, identity, *, immediate=False):
    """Read transport evidence after restart; NEVER calls prepare or delivery."""
    from app.services.whatsapp_mental import Follow, lock_care, locked, now_utc
    from app.services.whatsapp_comunicacao import coordinate_configured
    from app.models.whatsapp_convite import WhatsAppConviteEnvio
    row = db.get(Occurrence, identity)
    if row is None or row.status != 'PROCESSANDO':
        db.rollback(); return
    follow = db.get(Follow, row.acompanhamento_id)
    coordinate_configured(db, (follow.telefone,))
    lock_care(db, follow.contexto_assistencial_id)
    follow = locked(db, Follow, follow.id)
    row = locked(db, Occurrence, identity)
    if row.status != 'PROCESSANDO':
        db.rollback(); return
    now = aware(now_utc(db))
    attempt = db.scalar(select(WhatsAppConviteEnvio).where(WhatsAppConviteEnvio.conversa_id == row.conversa_id)
        .order_by(WhatsAppConviteEnvio.tentativa.desc()).limit(1))
    if attempt is not None and attempt.estado in ('ACEITO', 'REJEITADO'):
        row.processado_em = now
        execution_event(db, follow, row, 'EXECUTADO' if attempt.estado == 'ACEITO' else 'BLOQUEADO',
                        'META_ACCEPTED' if attempt.estado == 'ACEITO' else 'META_REJECTED', now)
    elif immediate or now >= row.processamento_iniciado_em + timedelta(minutes=2):
        execution_event(db, follow, row, 'PROCESSANDO', 'OUTCOME_UNCERTAIN', now)
    row.atualizado_em = now  # Fair bounded recovery scan, without repeated audit events.
    db.commit()


def run_executor_batch(session_factory, stop=None, limit=20):
    """Bounded, fresh sessions. A failed candidate never retries inside this cycle."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Executor batch limit must be between 1 and 100')
    if not executor_enabled() or (stop is not None and stop.is_set()): return
    from app.services.whatsapp_mental import Follow, now_utc
    from app.models.contexto_assistencial import ContextoAssistencial
    from sqlalchemy.orm import aliased
    newer = aliased(Grant)
    with session_factory() as db:
        sqlalchemy_event.listen(db, 'after_begin', executor_timeouts)
        enabled = select(Grant.id).where(Grant.instituicao_id == ContextoAssistencial.instituicao_id,
            Grant.habilitado.is_(True), ~select(newer.id).where(newer.instituicao_id == Grant.instituicao_id,
                newer.id > Grant.id).exists()).exists()
        base = select(Occurrence.id).join(Follow, Follow.id == Occurrence.acompanhamento_id).join(
            ContextoAssistencial, ContextoAssistencial.id == Follow.contexto_assistencial_id)
        now = aware(now_utc(db))
        expired = Occurrence.previsto_em < now - timedelta(hours=2)
        # Current eligible slots first. Expired slots are housekeeping only, never sent.
        current = and_(~expired, Follow.programacao_ativa.is_(True),
                       Occurrence.programacao_versao == Follow.programacao_versao)
        due = list(db.scalars(base.where(enabled, Occurrence.status == 'AGENDADO',
            Occurrence.previsto_em <= now, or_(current, expired))
            .order_by(case((expired, 1), else_=0), Occurrence.previsto_em, Occurrence.id).limit(limit)))
        # Recovery also runs after grant revocation, because it only records existing evidence.
        pending = list(db.scalars(select(Occurrence.id).where(Occurrence.status == 'PROCESSANDO')
            .order_by(Occurrence.atualizado_em, Occurrence.id).limit(limit)))
    for identity, recovery in [(i, False) for i in due] + [(i, True) for i in pending]:
        if stop is not None and stop.is_set(): break
        try:
            with session_factory() as db:
                sqlalchemy_event.listen(db, 'after_begin', executor_timeouts)
                if recovery: reconcile_occurrence(db, identity)
                else: execute_occurrence(db, identity)
        except Exception:
            # No credentials, recipient, SQL parameters or clinical data in executor logs.
            import logging
            logging.getLogger(__name__).error('weekly_executor_failed occurrence=%s recovery=%s', identity, recovery)


async def executor_loop(stop, session_factory):
    import asyncio
    import logging
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        started = loop.time()
        try:
            await asyncio.to_thread(run_executor_batch, session_factory, stop)
        except Exception:
            logging.getLogger(__name__).error('weekly_executor_cycle_failed')
        if not stop.is_set():
            await asyncio.to_thread(stop.wait, max(0, 60 - (loop.time() - started)))


from contextlib import asynccontextmanager

@asynccontextmanager
async def executor_lifespan(app):
    import asyncio
    from threading import Event as StopEvent
    from app.database import SessionLocal
    stop = StopEvent()
    task = asyncio.create_task(executor_loop(stop, SessionLocal)) if executor_enabled() else None
    try:
        yield
    finally:
        stop.set()
        if task is not None:
            await task  # Finish the bounded current operation; never abandon/retry network uncertainty.


def automation_active(db, follow):
    if not executor_enabled(): return False
    from app.models.contexto_assistencial import ContextoAssistencial
    from app.models.institucional import Instituicao
    context = db.get(ContextoAssistencial, follow.contexto_assistencial_id)
    institution = db.get(Instituicao, context.instituicao_id) if context else None
    grant = latest_grant(db, context.instituicao_id) if context else None
    if not (institution and institution.ativo and grant and grant.habilitado): return False
    from app.services.whatsapp_runtime import require_active
    try:
        require_active(db)
    except CheckinInvalid:
        return False
    return True


def executor_timeouts(session, transaction, connection):
    # Reapplied after every durable transport boundary, not only the first transaction.
    connection.execute(text("SET LOCAL lock_timeout = '3s'"))
    connection.execute(text("SET LOCAL statement_timeout = '15s'"))
