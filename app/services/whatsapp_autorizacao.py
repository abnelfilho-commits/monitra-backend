"""Canonical channel opt-in ledger. Evidence is attested by an authorized professional.

References/hashes identify evidence retained by the institution; this service never
fetches URLs or claims that a hash proves the truth of a document's contents.
"""
import hashlib
import json
import re
from sqlalchemy import select, text, func
from sqlalchemy.orm import aliased
from app.models.whatsapp_autorizacao import WhatsAppAutorizacaoComunicacao as Authorization
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation
from app.services.checkin_bem_estar import CheckinInvalid


def destination(phone):
    return hashlib.sha256(phone.encode()).hexdigest()


def latest(db, follow_id):
    return db.scalar(select(Authorization).where(Authorization.acompanhamento_id == follow_id)
        .order_by(Authorization.id.desc()).limit(1).execution_options(populate_existing=True))


def require_prior_authorization(db, follow):
    row = latest(db, follow.id)
    if row is None: raise CheckinInvalid('PRIOR_WHATSAPP_AUTHORIZATION_ABSENT')
    if row.estado != 'AUTORIZADA' or follow.consentimento_status == 'REVOGADO':
        raise CheckinInvalid('PRIOR_WHATSAPP_AUTHORIZATION_REVOKED')
    if row.destino_sha256 != destination(follow.telefone):
        raise CheckinInvalid('PRIOR_WHATSAPP_AUTHORIZATION_DESTINATION_CHANGED')
    return row


def authorized_follow_exists():
    # Latest event, not any historical grant. Phone changes are invalidated by configure().
    newer = aliased(Authorization)
    return select(Authorization.id).where(Authorization.acompanhamento_id == Follow.id,
        Authorization.estado == 'AUTORIZADA',
        Authorization.destino_sha256 == func.encode(func.sha256(func.convert_to(Follow.telefone, 'UTF8')), 'hex'),
        ~select(newer.id).where(newer.acompanhamento_id == Authorization.acompanhamento_id,
                               newer.id > Authorization.id).exists()).exists()


def append_event(db, follow, *, state, origin, occurred, actor=None, key=None,
                 fingerprint=None, reference=None, digest=None, reason=None, conversation=None, message=None):
    from app.models.contexto_assistencial import ContextoAssistencial
    from app.services.whatsapp_mental import now_utc
    previous = latest(db, follow.id)
    context = db.get(ContextoAssistencial, follow.contexto_assistencial_id)
    now = now_utc(db)
    row = Authorization(acompanhamento_id=follow.id, contexto_assistencial_id=context.id,
        paciente_id=follow.paciente_id,instituicao_id=context.instituicao_id,
        anterior_id=previous.id if previous else None,estado=state,origem=origin,
        ocorrido_em=occurred,registrado_em=now,usuario_id=actor,chave=key,
        comando_sha256=fingerprint,destino_sha256=destination(follow.telefone),
        referencia_evidencia=reference,evidencia_sha256=digest,motivo=reason,conversa_id=conversation,mensagem_id=message)
    db.add(row);db.flush()
    return row


def revoke_internal(db, follow, *, origin, reason, actor=None, conversation=None, message=None):
    # Caller already owns the canonical phone/care/follow locks. No intermediate commit.
    from app.services.whatsapp_mental import now_utc
    old = latest(db, follow.id)
    if old is not None and old.estado == 'REVOGADA': return old
    return append_event(db,follow,state='REVOGADA',origin=origin,occurred=now_utc(db),
                        actor=actor,reason=reason,conversation=conversation,message=message)


def view(row):
    return dict(id=row.id, acompanhamento_id=row.acompanhamento_id,estado=row.estado,
        origem=row.origem,ocorrido_em=row.ocorrido_em,registrado_em=row.registrado_em,
        usuario_id=row.usuario_id,anterior_id=row.anterior_id,
        referencia_evidencia=row.referencia_evidencia,evidencia_sha256=row.evidencia_sha256,
        motivo=row.motivo,conversa_id=row.conversa_id,mensagem_id=row.mensagem_id)


def register(db, context, key, payload, *, revoke=False):
    from app.services.whatsapp_mental import (WhatsAppMentalService, lock_phone, locked,
                                             lock_care, valid_scope, now_utc, OPEN)
    if not re.fullmatch(r'[A-Za-z0-9._:-]{16,128}',key or ''):
        raise CheckinInvalid('INVALID_IDEMPOTENCY_KEY')
    service = WhatsAppMentalService()
    service.authorized(db, **context)
    initial = db.scalar(select(Follow).where(Follow.contexto_assistencial_id == context['context']))
    if initial is None: raise CheckinInvalid('FOLLOW_UP_NOT_FOUND')
    identity,phone=initial.id,initial.telefone
    fingerprint=hashlib.sha256(json.dumps([identity,revoke,payload.model_dump(mode='json')],sort_keys=True).encode()).hexdigest()
    db.rollback()
    keylock=int.from_bytes(hashlib.sha256(f"whatsapp-auth:{context['institution']}:{context['actor']}:{key}".encode()).digest()[:8],'big',signed=True)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':keylock})
    lock_phone(db,phone)
    service.authorized(db, **context)
    follow=locked(db,Follow,identity)
    if follow.telefone != phone: raise CheckinInvalid('DESTINATION_CHANGED')
    old=db.scalar(select(Authorization).where(Authorization.instituicao_id==context['institution'],
        Authorization.usuario_id==context['actor'],Authorization.chave==key))
    if old:
        if old.comando_sha256 != fingerprint: raise CheckinInvalid('IDEMPOTENCY_CONFLICT')
        return dict(view(old), repetido=True, estado_atual=latest(db, identity).estado)  # Never reactivate.
    previous=latest(db,identity)
    now=now_utc(db)
    if revoke:
        if previous is not None and previous.estado=='REVOGADA':
            raise CheckinInvalid('AUTHORIZATION_ALREADY_REVOKED')
        row=append_event(db,follow,state='REVOGADA',origin='PORTAL_PROFISSIONAL',occurred=now,
            actor=context['actor'],key=key,fingerprint=fingerprint,reason=payload.motivo)
        for c in db.scalars(select(Conversation).where(Conversation.acompanhamento_whatsapp_id==identity,
                                                     Conversation.status.in_(OPEN)).with_for_update()):
            c.status='CANCELADA'
        db.flush()
    else:
        c,patient,person=lock_care(db,context['context'])
        if not valid_scope(db,follow,c,patient,person,now): raise CheckinInvalid('FOLLOW_UP_NOT_ELIGIBLE')
        if payload.obtida_em > now: raise CheckinInvalid('AUTHORIZATION_TIME_IN_FUTURE')
        if previous is not None:
            if previous.estado=='AUTORIZADA': raise CheckinInvalid('AUTHORIZATION_ALREADY_ACTIVE')
            if payload.obtida_em <= previous.registrado_em: raise CheckinInvalid('NEW_AUTHORIZATION_EVIDENCE_REQUIRED')
        if db.scalar(select(Authorization.id).where(Authorization.acompanhamento_id==identity,
                                                   Authorization.evidencia_sha256==payload.evidencia_sha256)):
            raise CheckinInvalid('AUTHORIZATION_EVIDENCE_ALREADY_USED')
        row=append_event(db,follow,state='AUTORIZADA',origin=payload.origem,occurred=payload.obtida_em,
            actor=context['actor'],key=key,fingerprint=fingerprint,
            reference=payload.referencia_evidencia,digest=payload.evidencia_sha256)
    return dict(view(row), repetido=False, estado_atual=row.estado)


def read(db, context):
    from app.services.whatsapp_mental import WhatsAppMentalService
    follow=WhatsAppMentalService().read(db, **context)
    if follow is None: return dict(acompanhamento_id=None,estado='AUSENTE',historico=[])
    rows=list(db.scalars(select(Authorization).where(Authorization.acompanhamento_id==follow.id).order_by(Authorization.id)))
    state=rows[-1].estado if rows else 'AUSENTE'
    if rows and state=='AUTORIZADA' and rows[-1].destino_sha256!=destination(follow.telefone):state='DESTINO_DIVERGENTE'
    return dict(acompanhamento_id=follow.id,estado=state,historico=[view(row) for row in rows])
