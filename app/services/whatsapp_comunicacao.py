"""Durable communication controls; PARAR is integrated by whatsapp_stop.

The ledger is the timeline source of truth, not a clinical record. Callers commit
atomically with the receipt. No automatic replies, grants or clinical transitions.
"""
import hashlib
import json
import re
from sqlalchemy import select, or_
from app.models.whatsapp_comunicacao import WhatsAppComunicacaoEvento as Event
from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel as Evidence
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.services.whatsapp_locks import acquire, transport, Resource, Phase
from app.services.checkin_bem_estar import CheckinInvalid


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def aliases(db, emitter, phone):
    # Only direct, non-contradictory Meta bridges; never transitive heuristics.
    rows = list(db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter,
        or_(Evidence.destinatario_solicitado == phone, Evidence.wa_id == phone))))
    result = {phone}
    for row in rows:
        siblings = list(db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter,
            Evidence.destinatario_solicitado == row.destinatario_solicitado)))
        mappings = {s.wa_id for s in siblings if s.evidencia_estado == 'VALIDA'}
        if any(s.evidencia_estado == 'INVALIDA' for s in siblings) or len(mappings) > 1:
            raise CheckinInvalid('TRANSPORT_IDENTITY_CONFLICT')
        if row.evidencia_estado == 'VALIDA':
            result.update((row.destinatario_solicitado, row.wa_id))
    return result


def coordinate_many(db, emitter, phones, *, operation=None, identity_check=True):
    """Declare the complete transport set before canonical phone/care locks.

    Raw phone locks remain for compatibility with unconverted clinical callers.
    Proven aliases only; the conservative transport key does not establish identity.
    """
    with db.no_autoflush:
        requested = set(phones)
        def lock_numbers():
            if identity_check:
                return set().union(*(aliases(db, emitter, phone) for phone in requested))
            # Ingress locks are not identity decisions. Preserve canonical refusal
            # of malformed/conflicting evidence in the unchanged resolver.
            rows = db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter,
                or_(Evidence.destinatario_solicitado.in_(requested), Evidence.wa_id.in_(requested))))
            values = set(requested)
            for row in rows:
                for value in (row.destinatario_solicitado, row.wa_id):
                    if value and value.isascii() and value.isdigit(): values.add(value)
            return values
        numbers = lock_numbers()
        plan = [transport(emitter, number) for number in numbers]
        if operation:
            plan.append(Resource(Phase.OPERATION, 'communication', (operation,)))
        acquire(db, plan, timeout_ms=3000)
        if lock_numbers() != numbers:
            raise CheckinInvalid('TRANSPORT_EVIDENCE_CHANGED')
        from app.services.whatsapp_mental import lock_phone
        from sqlalchemy import text
        from sqlalchemy.exc import DBAPIError
        from app.services.whatsapp_locks import LockUnavailable
        previous_timeout = db.scalar(text('SHOW lock_timeout'))
        try:
            db.execute(text("SELECT set_config('lock_timeout','3000ms',true)"))
            for phone in sorted(numbers):
                lock_phone(db, phone)
            db.execute(text("SELECT set_config('lock_timeout',:value,true)"), {'value':previous_timeout})
        except DBAPIError as exc:
            code = getattr(exc.orig, 'pgcode', None)
            db.rollback()
            if code in ('40P01','55P03','57014'):
                raise LockUnavailable('Transport lock unavailable; no retry') from None
            raise
        return numbers


def coordinate(db, emitter, phone, *, operation=None, identity_check=True):
    return coordinate_many(db, emitter, (phone,), operation=operation, identity_check=identity_check)


def coordinate_configured(db, phones, *, operation=None):
    import os
    emitter = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    if not emitter:
        raise CheckinInvalid('WHATSAPP_EMITTER_UNAVAILABLE')
    return coordinate_many(db, emitter, phones, operation=operation)


def recipient_scope(emitter, phone):
    return 'D:' + digest(json.dumps([emitter, phone]))


def follow_scope(follow_id):
    return 'A:' + str(follow_id)


def latest(db, scope):
    return db.scalar(select(Event).where(Event.escopo == scope).order_by(Event.id.desc()).limit(1)
                     .execution_options(populate_existing=True))


def blocked(db, emitter, phone, *, follow_id=None):
    scopes = [recipient_scope(emitter, number) for number in aliases(db, emitter, phone)]
    if follow_id is not None: scopes.append(follow_scope(follow_id))
    return any(row and row.estado == 'INTERROMPIDA' for row in (latest(db, s) for s in scopes))


def require_output(db, emitter, phone, *, conversation_id=None, invitation=False):
    """Caller already owns coordinate() before any care/receipt row lock."""
    from app.services.whatsapp_autorizacao import require_prior_authorization
    follow = None
    if conversation_id is not None:
        conversation = db.get(Conversation, conversation_id, populate_existing=True)
        if conversation is None: raise CheckinInvalid('CONVERSATION_UNAVAILABLE')
        follow = db.get(Follow, conversation.acompanhamento_whatsapp_id, populate_existing=True)
        if follow is None or conversation.telefone not in aliases(db, emitter, phone) or follow.telefone != conversation.telefone:
            raise CheckinInvalid('COMMUNICATION_DESTINATION_CHANGED')
    if blocked(db, emitter, phone, follow_id=follow.id if follow else None):
        raise CheckinInvalid('WHATSAPP_INTERROMPIDO')
    if follow:
        require_prior_authorization(db, follow)
        if follow.status != 'ATIVO' or follow.consentimento_status == 'REVOGADO':
            raise CheckinInvalid('COMMUNICATION_NOT_AUTHORIZED')
    return follow


def append(db, *, scope, emitter, phone, state, key, fingerprint, follow=None,
           message=None, actor=None, reference=None, evidence_hash=None, obtained=None):
    old = db.scalar(select(Event).where(Event.chave == key))
    if old:
        if old.comando_sha256 != fingerprint: raise CheckinInvalid('IDEMPOTENCY_CONFLICT')
        return old
    previous = latest(db, scope)
    values = {}
    if follow is not None:
        from app.models.contexto_assistencial import ContextoAssistencial
        context = db.get(ContextoAssistencial, follow.contexto_assistencial_id)
        values = dict(acompanhamento_id=follow.id,contexto_assistencial_id=context.id,
                      paciente_id=follow.paciente_id,instituicao_id=context.instituicao_id)
    row = Event(escopo=scope, anterior_id=previous.id if previous else None,
        phone_number_id=emitter,destino_sha256=digest(phone),estado=state,
        origem='WHATSAPP' if message else 'PROFISSIONAL',mensagem_id=message,usuario_id=actor,
        chave=key,comando_sha256=fingerprint,evidencia_referencia=reference,evidencia_sha256=evidence_hash,evidencia_obtida_em=obtained,**values)
    db.add(row); db.flush()
    return row


def interrupt(db, **command):
    """Compatibility entry to the authenticated communication stop command."""
    from app.services.whatsapp_stop import interrupt as stop
    return stop(db, **command)


def reactivate(db, context, key, payload):
    """Explicit professional action; does not grant E12C or remove recipient block.

    Recipient reactivation needs a separate multi-institution operational policy;
    intentionally no endpoint is exposed for it in this stage.
    """
    import os
    from app.services.whatsapp_mental import WhatsAppMentalService, lock_care, locked
    from app.services.whatsapp_autorizacao import require_prior_authorization
    service = WhatsAppMentalService()
    service.authorized(db,write=False,**context)
    initial = db.scalar(select(Follow).where(Follow.contexto_assistencial_id == context['context']))
    if initial is None: raise CheckinInvalid('FOLLOW_UP_NOT_FOUND')
    if not re.fullmatch(r'[A-Za-z0-9._:-]{16,128}',key or ''): raise CheckinInvalid('INVALID_IDEMPOTENCY_KEY')
    identity, phone = initial.id, initial.telefone
    emitter = os.getenv('WHATSAPP_PHONE_NUMBER_ID','')
    command = digest(json.dumps([context,key],sort_keys=True))
    fingerprint = digest(json.dumps([identity,payload.model_dump(mode='json')],sort_keys=True))
    coordinate(db,emitter,phone,operation=command)
    service.authorized(db,**context)
    follow = locked(db,Follow,identity)
    if follow.telefone != phone: raise CheckinInvalid('COMMUNICATION_DESTINATION_CHANGED')
    old = db.scalar(select(Event).where(Event.chave == command))
    if old:
        if old.comando_sha256 != fingerprint: raise CheckinInvalid('IDEMPOTENCY_CONFLICT')
        return event_view(old, context['person'])
    previous = latest(db,follow_scope(identity))
    if not previous or previous.estado != 'INTERROMPIDA': raise CheckinInvalid('COMMUNICATION_NOT_INTERRUPTED')
    require_prior_authorization(db,follow)
    from app.services.whatsapp_mental import now_utc
    if payload.obtida_em <= previous.ocorrido_em or payload.obtida_em > now_utc(db):
        raise CheckinInvalid('NEW_COMMUNICATION_EVIDENCE_REQUIRED')
    row = append(db,scope=follow_scope(identity),emitter=emitter,phone=phone,state='REATIVADA',
        key=command,fingerprint=fingerprint,follow=follow,actor=context['actor'],
        reference=payload.referencia_evidencia,evidence_hash=payload.evidencia_sha256,obtained=payload.obtida_em)
    return event_view(row,context['person'])


def event_view(row, person):
    return dict(id=row.id,tipo='COMUNICACAO_WHATSAPP_'+row.estado,
        acompanhamento_id=row.acompanhamento_id,pessoa_id=person,
        contexto_assistencial_id=row.contexto_assistencial_id,instituicao_id=row.instituicao_id,
        ocorrido_em=row.ocorrido_em,origem=row.origem,
        autoria={'tipo':'PESSOA' if row.origem=='WHATSAPP' else 'PROFISSIONAL',
                 'pessoa_id':person if row.origem=='WHATSAPP' else None,'usuario_id':row.usuario_id},
        referencia_auditoria='whatsapp-comunicacao:'+str(row.id))


def read(db, context):
    import os
    from app.services.whatsapp_mental import WhatsAppMentalService
    follow = WhatsAppMentalService().read(db,**context)
    if follow is None: return dict(estado='AUSENTE',acompanhamento_id=None,eventos=[],bloqueio_preventivo=False)
    rows=list(db.scalars(select(Event).where(Event.acompanhamento_id==follow.id,
        Event.contexto_assistencial_id==context['context'],Event.instituicao_id==context['institution']).order_by(Event.ocorrido_em,Event.id)))
    last=latest(db,follow_scope(follow.id))
    preventive=blocked(db,os.getenv('WHATSAPP_PHONE_NUMBER_ID',''),follow.telefone)
    return dict(estado='WHATSAPP_INTERROMPIDO' if preventive or (last and last.estado=='INTERROMPIDA') else 'SEM_INTERRUPCAO_REGISTRADA',
        acompanhamento_id=follow.id,interrompido_pela_pessoa=bool(last and last.estado=='INTERROMPIDA'),
        ocorrido_em=last.ocorrido_em if last else None,bloqueio_preventivo=preventive,
        acompanhamento_assistencial_independente=True,eventos=[event_view(r,context['person']) for r in rows])


def release_recipient(db, *, actor, emitter, phone, key, payload):
    """Internal explicit administrative procedure, no public endpoint or opt-in.

    Removing a cross-institution preventive block needs an active ADMIN and new
    verified evidence. It never unblocks contextual events or grants E12C.
    """
    from app.models.usuario import Usuario
    from app.services.checkin_bem_estar import CheckinDenied
    from app.services.whatsapp_mental import now_utc
    user=db.get(Usuario,actor)
    if not user or not user.ativo or user.perfil!='ADMIN': raise CheckinDenied('CHECKIN_UNAVAILABLE')
    if not re.fullmatch(r'[A-Za-z0-9._:-]{16,128}',key or ''): raise CheckinInvalid('INVALID_IDEMPOTENCY_KEY')
    command=digest(json.dumps(['recipient-release',actor,key]))
    fingerprint=digest(json.dumps([emitter,phone,payload.model_dump(mode='json')],sort_keys=True))
    coordinate(db,emitter,phone,operation=command)
    user=db.scalar(select(Usuario).where(Usuario.id==actor).with_for_update().execution_options(populate_existing=True))
    if not user or not user.ativo or user.perfil!='ADMIN': raise CheckinDenied('CHECKIN_UNAVAILABLE')
    old=db.scalar(select(Event).where(Event.chave==command))
    if old:
        if old.comando_sha256!=fingerprint: raise CheckinInvalid('IDEMPOTENCY_CONFLICT')
        return old.id
    # Exact barrier only: do not implicitly clear aliases or other scopes.
    scope=recipient_scope(emitter,phone);previous=latest(db,scope)
    if not previous or previous.estado!='INTERROMPIDA': raise CheckinInvalid('COMMUNICATION_NOT_INTERRUPTED')
    if payload.obtida_em<=previous.ocorrido_em or payload.obtida_em>now_utc(db):
        raise CheckinInvalid('NEW_COMMUNICATION_EVIDENCE_REQUIRED')
    return append(db,scope=scope,emitter=emitter,phone=phone,state='REATIVADA',key=command,
        fingerprint=fingerprint,actor=actor,reference=payload.referencia_evidencia,
        evidence_hash=payload.evidencia_sha256,obtained=payload.obtida_em).id
