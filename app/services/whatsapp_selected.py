"""Selected-conversation ingress. No HTTP or retry.

Owns one transaction; replies are only returned/persisted, never transmitted.
"""
from dataclasses import dataclass, asdict
from datetime import date
import hashlib
import json
from sqlalchemy import select
from fastapi import HTTPException
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.models.whatsapp_resolucao import WhatsAppResolucao as Audit
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Mental
from app.models.whatsapp_conversa import WhatsAppConversa as Legacy
from app.services import whatsapp_multilinhas as multi
from app.services import whatsapp_referencia as reference
from app.services.whatsapp_comunicacao import coordinate_many, require_output
from app.services.whatsapp_transporte import legacy_state


@dataclass(frozen=True)
class Selection:
    kind: str
    conversation_id: int
    care_line: str
    institution_id: object
    patient_id: object
    person_id: object
    followup_id: object
    responsible_id: object
    emitter: str
    sender: str
    message_id: str
    context_wamid: object
    evidence_ids: tuple
    state: str
    navigation_patients: tuple = ()

    def audit(self):
        # No transport identifiers, message text or clinical contents in JSON audit.
        return {k: v for k, v in asdict(self).items()
                if k not in ('sender', 'emitter', 'context_wamid')}


def selection(db, kind, identity, emitter, sender, message_id, context_wamid, evidence_ids):
    from app.models.paciente import Paciente
    c = db.get(Mental if kind == 'MENTAL' else Legacy, identity, populate_existing=True)
    patient = db.get(Paciente, c.paciente_id, populate_existing=True) if c.paciente_id else None
    if kind == 'MENTAL':
        from app.services.whatsapp_mental import Context
        context = db.get(Context, c.contexto_assistencial_id, populate_existing=True)
        institution = context.instituicao_id
        state = hashlib.sha256(json.dumps([c.status, str(c.expires_at), c.etapa_atual,
            c.contexto_assistencial_id, c.telefone], default=str).encode()).hexdigest()
    else:
        institution = patient.clinica_id if patient else None
        state = legacy_state(c)
    return Selection(kind, identity, 'MENTAL' if kind == 'MENTAL' else c.care_line,
        institution, c.paciente_id, patient.pessoa_id if patient else None,
        c.acompanhamento_whatsapp_id if kind == 'MENTAL' else None,
        c.responsavel_id if kind == 'LEGADO' else None, emitter, sender,
        message_id, context_wamid, tuple(evidence_ids), state,
        (c.paciente_id,) if kind == 'LEGADO' and c.etapa_atual == 'SELECIONAR_LINHA' else ())


def navigation(db, emitter, sender, message_id, candidates):
    """Resume a unique existing menu; never create a session or infer a patient."""
    from dataclasses import replace
    from app.models.responsavel import Responsavel
    from app.models.responsavel_paciente import ResponsavelPaciente
    from app.services.whatsapp_conversation_service import normalizar_telefone
    from app.services.whatsapp_daily_record import eligible_lines
    from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel as Evidence
    menus = []
    for candidate in candidates:
        if candidate.kind != 'LEGADO': return None
        c = db.get(Legacy, candidate.conversation_id, populate_existing=True)
        if c.etapa_atual not in ('INICIO', 'SELECIONAR_PACIENTE'):
            return None
        rows = list(db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter, Evidence.conversa_legada_id == c.id)))
        reason, ids = multi.identity(rows, sender, c.telefone)
        responsible = db.get(Responsavel, c.responsavel_id, populate_existing=True)
        if reason != 'OK' or not responsible or not responsible.ativo or normalizar_telefone(responsible.telefone) != c.telefone:
            return None
        if rows and not any(r.id in ids and r.legado_estado_sha256 == legacy_state(c) for r in rows):
            return None
        # Uniqueness is verified even for another responsible with no session.
        owners = [r.id for r in db.scalars(select(Responsavel).where(Responsavel.ativo.is_(True)))
                  if normalizar_telefone(r.telefone) in (sender, c.telefone)]
        if owners != [responsible.id]: return None
        links = list(db.scalars(select(ResponsavelPaciente).where(ResponsavelPaciente.responsavel_id == responsible.id, ResponsavelPaciente.ativo.is_(True))))
        patients = []
        for link in links:
            try:
                if not eligible_lines(db, responsible.id, link.paciente_id): return None
            except ValueError: return None
            patients.append(link.paciente_id)
        if not patients: return None
        menus.append(replace(selection(db, 'LEGADO', c.id, emitter, sender, message_id, None, ids),
                             navigation_patients=tuple(sorted(set(patients)))))
    return menus[0] if len(menus) == 1 else None


def fresh_navigation(db, emitter, sender, message_id, responsible_id):
    from app.models.responsavel import Responsavel
    from app.models.responsavel_paciente import ResponsavelPaciente
    from app.services.whatsapp_daily_record import eligible_lines
    r = db.get(Responsavel, responsible_id, populate_existing=True)
    links = list(db.scalars(select(ResponsavelPaciente).where(
        ResponsavelPaciente.responsavel_id == responsible_id, ResponsavelPaciente.ativo.is_(True))))
    patients = []
    for link in links:
        try:
            if not eligible_lines(db, responsible_id, link.paciente_id): return None
        except ValueError: return None
        patients.append(link.paciente_id)
    if not patients: return None
    state = hashlib.sha256(json.dumps([r.id, r.telefone, r.clinica_id, sorted(patients)]).encode()).hexdigest()
    return Selection('LEGADO', None, None, r.clinica_id, None, None, None,
        r.id, emitter, sender, message_id, None, (), state, tuple(sorted(set(patients))))


def propose(db, emitter, sender, content, message_id, context_wamid=None):
    if content.strip().upper() == 'PARAR':
        return 'PARAR_NAO_INTEGRADO', None, ()
    if context_wamid is not None:
        row = reference.evidence(db, emitter, context_wamid)
        if row is None:
            return 'REFERENCIA_DESCONHECIDA', None, ()
        kind, cid = ('MENTAL', row.conversa_contextual_id) if row.conversa_contextual_id else ('LEGADO', row.conversa_legada_id)
        if cid is None:
            return 'SEM_VINCULO_ASSISTENCIAL', None, ()
        c = db.get(Mental if kind == 'MENTAL' else Legacy, cid, populate_existing=True)
        if c is None or not reference.identity_matches(db, row, sender, c.telefone):
            return 'IDENTIDADE_RECUSADA', None, (row.id,)
        from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel as Evidence
        field = Evidence.conversa_contextual_id if kind == 'MENTAL' else Evidence.conversa_legada_id
        rows = list(db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter, field == cid)))
        if multi.identity(rows, sender, c.telefone)[0] != 'OK':
            return 'IDENTIDADE_RECUSADA', None, (row.id,)
        if kind == 'LEGADO' and c.etapa_atual in ('INICIO', 'SELECIONAR_PACIENTE'):
            from dataclasses import replace
            menu = navigation(db, emitter, sender, message_id, (multi.Candidate('LEGADO', c.id, (row.id,), 'NAVEGACAO'),))
            if menu and row.legado_estado_sha256 == legacy_state(c):
                return 'NAVEGACAO', replace(menu, context_wamid=context_wamid), (row.id,)
            return 'SEM_VINCULO_ASSISTENCIAL', None, (row.id,)
        from app.services.whatsapp_mental import now_utc
        reason = multi.mental_reason(db, c, now_utc(db)) if kind == 'MENTAL' else multi.legacy_reason(db, c, [row], date.today())
        if kind == 'LEGADO' and row.legado_estado_sha256 != legacy_state(c):
            reason = 'REFERENCIA_DESATUALIZADA'
        if reason != 'OK':
            return reason, None, (row.id,)
        return 'SELECIONADA', selection(db, kind, cid, emitter, sender, message_id, context_wamid, (row.id,)), (row.id,)
    decision = multi.resolve(db, emitter, sender, content)
    if decision.selected:
        kind, cid = decision.selected
        candidate = next(c for c in decision.candidates if (c.kind, c.conversation_id) == decision.selected)
        return 'SELECIONADA', selection(db, kind, cid, emitter, sender, message_id, None, candidate.evidence_ids), decision.candidates
    if decision.outcome == 'FALLBACK_SEGURO':
        menu = fresh_navigation(db, emitter, sender, message_id, decision.fallback_responsible_id)
        if menu is not None: return 'NAVEGACAO_NOVA', menu, decision.candidates
    if decision.outcome == 'INDISPONIVEL':
        menu = navigation(db, emitter, sender, message_id, decision.candidates)
        if menu is not None: return 'NAVEGACAO', menu, decision.candidates
    return decision.outcome, None, decision.candidates


def _phones(db, proposal, sender):
    result = {sender}
    chosen = proposal[1]
    if chosen and chosen.conversation_id is not None:
        c = db.get(Mental if chosen.kind == 'MENTAL' else Legacy, chosen.conversation_id)
        result.add(c.telefone)
    for candidate in proposal[2]:
        if isinstance(candidate, multi.Candidate):
            c = db.get(Mental if candidate.kind == 'MENTAL' else Legacy, candidate.conversation_id)
            if c: result.add(c.telefone)
    return result


def _lock_selected(db, chosen):
    if chosen.kind == 'MENTAL':
        from app.services.whatsapp_mental import lock_execution_scope
        lock_execution_scope(db, chosen.conversation_id)
    else:
        from app.services.whatsapp_daily_record import authorized_lines
        if chosen.navigation_patients:
            from app.services.daily_record.concurrency import lock_responsible, lock_patient
            lock_responsible(db, chosen.responsible_id)
            for pid in chosen.navigation_patients: lock_patient(db, pid)
            for pid in chosen.navigation_patients: authorized_lines(db, chosen.responsible_id, pid)
        else:
            authorized_lines(db, chosen.responsible_id, chosen.patient_id)
        if chosen.conversation_id is not None:
            db.scalar(select(Legacy).where(Legacy.id == chosen.conversation_id)
                      .with_for_update().execution_options(populate_existing=True))


def process_selected(db, message_id, emitter, sender, content, context_wamid=None):
    """Selected entry point. Safe refusals and successful effects commit atomically.

    A complete transport plan precedes care locks. A changed candidate set is
    refused, never followed by acquiring a newly discovered identity lock.
    """
    if db.new or db.dirty or db.deleted:
        raise ValueError('Selected ingress requires a clean session')
    from app.services.whatsapp_transporte import wamid_valid
    if (not isinstance(message_id, str) or not 1 <= len(message_id) <= 512
            or not isinstance(emitter, str) or not emitter
            or not isinstance(sender, str) or not sender.isascii() or not sender.isdigit()
            or not 8 <= len(sender) <= 15
            or not isinstance(content, str) or not content.strip() or len(content) > 4096
            or (context_wamid is not None and not wamid_valid(context_wamid))):
        raise ValueError('Invalid inbound message')
    fingerprint = hashlib.sha256(json.dumps([emitter, sender, content, context_wamid], ensure_ascii=False).encode()).hexdigest()
    try:
        initial = propose(db, emitter, sender, content, message_id, context_wamid)
        coordinate_many(db, emitter, _phones(db, initial, sender), operation='ingress:'+message_id, identity_check=False)
        old = db.get(Receipt, message_id, populate_existing=True)
        if old:
            expected = fingerprint if old.fingerprint_versao == 2 else hashlib.sha256(json.dumps([emitter, sender, content], ensure_ascii=False).encode()).hexdigest()
            if old.phone_number_id != emitter or old.fingerprint != expected:
                raise HTTPException(409, 'Webhook identity conflict.')
            response = old.resposta
            db.commit()
            return response
        current = propose(db, emitter, sender, content, message_id, context_wamid)
        outcome, chosen = current[:2]
        if current != initial:
            outcome, chosen = 'SELECAO_ALTERADA', None
        if chosen:
            from app.services.checkin_bem_estar import CheckinInvalid, CheckinDenied
            try:
                _lock_selected(db, chosen)
            except (CheckinInvalid, CheckinDenied, ValueError):
                outcome, chosen = 'SELECAO_ALTERADA', None
            if chosen and propose(db, emitter, sender, content, message_id, context_wamid) != current:
                outcome, chosen = 'SELECAO_ALTERADA', None
        # No unsafe fallback: only a revalidated full navigation plan may create a session.
        if outcome == 'FALLBACK_SEGURO': outcome = 'NAVEGACAO_REQUER_PLANO'
        response = multi.AMBIGUOUS if outcome == 'AMBIGUA' else reference.UNAVAILABLE if context_wamid else multi.UNAVAILABLE
        if not chosen:
            from app.services.whatsapp_comunicacao import blocked
            from app.services.checkin_bem_estar import CheckinInvalid
            try:
                preventive = blocked(db, emitter, sender)
            except CheckinInvalid:
                preventive = False  # Identity refusal remains authoritative.
            if preventive:
                from app.services.whatsapp_stop import BLOCKED
                outcome, response = 'COMUNICACAO_INDISPONIVEL', BLOCKED
        if chosen:
            from app.services.checkin_bem_estar import CheckinInvalid
            try:
                require_output(db, emitter, sender, conversation_id=chosen.conversation_id if chosen.kind == 'MENTAL' else None)
            except CheckinInvalid:
                from app.services.whatsapp_stop import BLOCKED
                outcome, chosen = 'COMUNICACAO_INDISPONIVEL', None
                response = BLOCKED
        receipt = Receipt(message_id=message_id, phone_number_id=emitter, fingerprint=fingerprint,
            fingerprint_versao=2, context_wamid=context_wamid, resposta='',
            resolucao='REFERENCIA_RECUSADA' if context_wamid else 'LEGADO_SEM_CONVERSA')
        # Insert after identity/conversation locks, before clinical FK references.
        db.add(receipt); db.flush()
        if chosen:
            if chosen.kind == 'MENTAL':
                from app.services.whatsapp_mental import WhatsAppMentalService
                response = WhatsAppMentalService().receive(db, chosen.conversation_id, content, message_id=message_id)
                receipt.conversa_contextual_id = chosen.conversation_id
                receipt.resolucao = 'REFERENCIA_CONTEXTUAL' if context_wamid else 'CONTEXTUAL_ATUAL'
            else:
                from app.services.whatsapp_conversation_service import processar_mensagem
                if chosen.conversation_id is None:
                    from dataclasses import replace
                    c = Legacy(responsavel_id=chosen.responsible_id, telefone=sender,
                               etapa_atual='INICIO', respostas_json={})
                    db.add(c); db.flush()
                    chosen = replace(chosen, conversation_id=c.id)
                else:
                    c = db.get(Legacy, chosen.conversation_id)
                response = processar_mensagem(db, c.telefone, content, selected=c)
                db.flush()
                if (c.responsavel_id != chosen.responsible_id or
                        (c.paciente_id not in (None, *chosen.navigation_patients) if chosen.navigation_patients else
                         ((c.paciente_id != chosen.patient_id and not (c.paciente_id is None and c.etapa_atual == 'INICIO')) or c.care_line != chosen.care_line))):
                    raise ValueError('Selected clinical identity changed')
                receipt.conversa_legada_id = c.id
                receipt.resolucao = 'REFERENCIA_LEGADA' if context_wamid else 'LEGADO_ATUAL'
                receipt.legado_estado_sha256 = legacy_state(c)
        receipt.resposta = response
        receipt.resolucao_motivo = outcome
        candidates = [asdict(c) if isinstance(c, multi.Candidate) else {'evidence_id': c} for c in current[2]]
        executed = None
        if chosen:
            c = db.get(Mental if chosen.kind == 'MENTAL' else Legacy, chosen.conversation_id)
            executed = dict(conversation_id=c.id, patient_id=c.paciente_id,
                            care_line='MENTAL' if chosen.kind == 'MENTAL' else c.care_line)
        db.add(Audit(message_id=message_id, decisao=dict(version=1, outcome=outcome,
            candidates=candidates, selection=chosen.audit() if chosen else None, executed=executed)))
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise
