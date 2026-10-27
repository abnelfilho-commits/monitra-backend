"""Authenticated PARAR only. No general multiline clinical routing or outbound IO.

A stop may protect transport without attributing a patient. A contextual event
requires current care links and transport identity, not current check-in consent.
"""
import json
from datetime import date
from sqlalchemy import select, or_
from fastapi import HTTPException
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation
from app.models.whatsapp_conversa import WhatsAppConversa as Legacy
from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel as Evidence
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.models.whatsapp_resolucao import WhatsAppResolucao as Audit
from app.services.checkin_bem_estar import CheckinInvalid, CheckinDenied
from app.services.whatsapp_comunicacao import coordinate_many, digest, append, follow_scope, recipient_scope
from app.services.whatsapp_multilinhas import identity, legacy_reason
from app.services.whatsapp_referencia import evidence, identity_matches

RESPONSE = 'As comunicações por WhatsApp foram interrompidas. Isso não encerra o acompanhamento assistencial. Procure a equipe para reativá-las.'
BLOCKED = 'As comunicações por WhatsApp estão interrompidas. Procure a equipe responsável para reativá-las.'


def is_stop(content):
    return isinstance(content, str) and content.strip().upper() == 'PARAR'


def current_link(db, c):
    from app.models.contexto_assistencial import ContextoAssistencial as Context, ContextoAssistencialLinha as Line
    from app.models.institucional import Instituicao, PacienteInstituicao
    from app.models.paciente import Paciente
    from app.models.pessoa import Pessoa
    from app.services.whatsapp_mental import now_utc
    a = db.get(Follow, c.acompanhamento_whatsapp_id, populate_existing=True)
    context = db.get(Context, c.contexto_assistencial_id, populate_existing=True)
    patient = db.get(Paciente, c.paciente_id, populate_existing=True)
    person = db.get(Pessoa, patient.pessoa_id, populate_existing=True) if patient and patient.pessoa_id else None
    link = db.get(PacienteInstituicao, context.paciente_instituicao_id, populate_existing=True) if context else None
    institution = db.get(Instituicao, context.instituicao_id, populate_existing=True) if context else None
    today = now_utc(db).date()
    # A historic invitation can stop a CURRENT followup. Neither E12C nor SIM
    # is granted/revoked here; expiry/status of the invitation is immaterial.
    return bool(a and a.status == 'ATIVO' and a.telefone == c.telefone
        and a.paciente_id == c.paciente_id and a.contexto_assistencial_id == c.contexto_assistencial_id
        and context and context.ativo and context.paciente_id == c.paciente_id
        and context.data_inicio <= today and context.data_fim is None
        and patient and person and person.ativo and institution and institution.ativo
        and link and link.ativo and link.paciente_id == c.paciente_id
        and link.instituicao_id == context.instituicao_id and link.data_inicio <= today
        and (link.data_fim is None or link.data_fim >= today)
        and db.scalar(select(Line.id).where(Line.contexto_assistencial_id == context.id,
            Line.modulo_id == 3, Line.ativo.is_(True))))


def propose(db, emitter, sender, reference):
    """Read-only target proposal. Never choose a patient by order/date/line."""
    considered = []
    if reference is not None:
        row = evidence(db, emitter, reference)
        if row is None:
            return None, 'REFERENCIA_DESCONHECIDA', considered
        if row.conversa_contextual_id is None:
            return None, 'PROTECAO_TRANSPORTE', considered
        c = db.get(Conversation, row.conversa_contextual_id, populate_existing=True)
        rows = list(db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter,
            Evidence.conversa_contextual_id == row.conversa_contextual_id)))
        if c is None or not identity_matches(db, row, sender, c.telefone) or identity(rows, sender, c.telefone)[0] != 'OK':
            return None, 'IDENTIDADE_INCOMPATIVEL', considered
        if not current_link(db, c):
            return None, 'VINCULO_INCOMPATIVEL', considered
        return c.id, 'PARAR_CONTEXTUAL', [dict(kind='MENTAL', conversation_id=c.id)]
    matching = list(db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter,
        or_(Evidence.destinatario_solicitado == sender, Evidence.wa_id == sender))))
    targets = {}
    unsafe = False
    for kind, model, field in (('MENTAL', Conversation, 'conversa_contextual_id'), ('LEGADO', Legacy, 'conversa_legada_id')):
        ids = {getattr(r, field) for r in matching if getattr(r, field) is not None}
        for c in db.scalars(select(model).where(or_(model.telefone == sender, model.id.in_(ids))).execution_options(populate_existing=True)):
            rows = list(db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter, getattr(Evidence, field) == c.id)))
            reason, proof = identity(rows, sender, c.telefone)
            if reason != 'OK':
                unsafe = True
            elif kind == 'MENTAL':
                if current_link(db, c):
                    targets.setdefault(('MENTAL', c.acompanhamento_whatsapp_id), []).append(c.id)
                else:
                    reason = 'VINCULO_INCOMPATIVEL'
            elif legacy_reason(db, c, [r for r in rows if r.id in proof], date.today()) == 'OK' or c.etapa_atual in ('INICIO', 'SELECIONAR_PACIENTE'):
                # Navigation with no patient is also a competing destination;
                # it never creates an individualized stop event.
                targets[('LEGADO', c.id)] = [c.id]
            considered.append(dict(kind=kind, conversation_id=c.id, reason=reason))
    if not unsafe and len(targets) == 1:
        (kind, _), ids = next(iter(targets.items()))
        if kind == 'MENTAL':
            # Multiple invitations of the SAME followup are not multiple targets.
            # No arbitrary conversation is attributed to unreferenced receipts.
            return tuple(sorted(ids)), 'PARAR_ACOMPANHAMENTO', considered
    return None, 'IDENTIDADE_INCOMPATIVEL' if unsafe else 'PROTECAO_TRANSPORTE', considered


def locked_target(db, message_id, emitter, sender, reference):
    with db.no_autoflush:
        initial, _, _ = propose(db, emitter, sender, reference)
        ids = initial if isinstance(initial, tuple) else (initial,) if initial else ()
        phones = {sender}
        phones.update(db.get(Conversation, i).telefone for i in ids)
        coordinate_many(db, emitter, phones, operation='ingress:'+message_id, identity_check=False)
        selected, reason, candidates = propose(db, emitter, sender, reference)
        if selected != initial:
            return None, None, 'SELECAO_ALTERADA', candidates
        follow = None
        if selected:
            from app.services.whatsapp_mental import lock_care, locked
            c = db.get(Conversation, ids[0])
            try:
                lock_care(db, c.contexto_assistencial_id)
                follow = locked(db, Follow, c.acompanhamento_whatsapp_id)
                # Stable row order, only one care scope. Never execute a handler.
                for i in sorted(ids): locked(db, Conversation, i)
            except CheckinDenied:
                return None, None, 'VINCULO_INCOMPATIVEL', candidates
            rebuilt, _, candidates = propose(db, emitter, sender, reference)
            if rebuilt != selected:
                return None, None, 'SELECAO_ALTERADA', candidates
        return follow, selected if isinstance(selected, int) else None, reason, candidates


def persist(db, receipt, emitter, sender, follow, conversation, reason, candidates):
    event = append(db, scope=follow_scope(follow.id) if follow else recipient_scope(emitter, sender),
        emitter=emitter, phone=sender, state='INTERROMPIDA', key=digest('stop:'+receipt.message_id),
        fingerprint=receipt.fingerprint, follow=follow, message=receipt.message_id)
    # Existing audit contract accepts internal IDs, never recipient/text/clinical data.
    if db.get(Audit, receipt.message_id) is None:
        db.add(Audit(message_id=receipt.message_id, decisao=dict(version=1,
            outcome=reason, operation='PARAR', communication_event_id=event.id,
            followup_id=follow.id if follow else None, conversation_id=conversation,
            candidates=candidates, clinical_execution=False)))
    receipt.resolucao = 'REFERENCIA_CONTEXTUAL' if conversation else 'REFERENCIA_RECUSADA' if receipt.context_wamid else 'LEGADO_SEM_CONVERSA'
    receipt.resolucao_motivo = reason
    receipt.conversa_contextual_id = conversation
    receipt.conversa_legada_id = None
    receipt.resposta = RESPONSE
    db.flush()
    return event


def interrupt(db, *, message_id, emitter, sender, content, context_wamid=None):
    """Internal compatibility command for an existing authenticated v2 receipt.

    Caller owns the transaction. Live ingress uses process() so care locks precede
    creation of receipt/audit/event. No implicit commit or external response.
    """
    if not is_stop(content): raise CheckinInvalid('STOP_REQUIRED')
    target = locked_target(db, message_id, emitter, sender, context_wamid)
    receipt = db.get(Receipt, message_id, populate_existing=True)
    expected = digest(json.dumps([emitter, sender, content, context_wamid], ensure_ascii=False))
    if not receipt or receipt.phone_number_id != emitter or receipt.fingerprint_versao != 2 or receipt.fingerprint != expected or receipt.context_wamid != context_wamid:
        raise CheckinInvalid('RECEIPT_IDENTITY_CONFLICT')
    from app.models.whatsapp_comunicacao import WhatsAppComunicacaoEvento as Event
    old = db.scalar(select(Event).where(Event.chave == digest('stop:'+message_id)))
    if old: return old
    return persist(db, receipt, emitter, sender, *target)


def process(db, message_id, emitter, sender, content, context_wamid):
    try:
        if not is_stop(content): raise CheckinInvalid('STOP_REQUIRED')
        # Reconstruct under locks before any receipt or communication write.
        target = locked_target(db, message_id, emitter, sender, context_wamid)
        expected = digest(json.dumps([emitter, sender, content, context_wamid], ensure_ascii=False))
        receipt = db.get(Receipt, message_id, populate_existing=True)
        if receipt is not None:
            fingerprint = digest(json.dumps([emitter, sender, content], ensure_ascii=False)) if receipt.fingerprint_versao == 1 else expected
            if receipt.phone_number_id != emitter or receipt.fingerprint != fingerprint:
                raise HTTPException(409, 'Webhook identity conflict.')
            result = receipt.resposta
        else:
            receipt = Receipt(message_id=message_id, phone_number_id=emitter, fingerprint=expected,
                fingerprint_versao=2, context_wamid=context_wamid, resposta='')
            db.add(receipt); db.flush()
            persist(db, receipt, emitter, sender, *target)
            result = receipt.resposta
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
