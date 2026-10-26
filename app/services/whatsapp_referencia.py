"""Explicit transport references. No phone heuristics, no fallback or new episodes."""
from datetime import date, timedelta
from sqlalchemy import select
from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel as Evidence
from app.models.whatsapp_conversa import WhatsAppConversa as Legacy
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Conversation
from app.services.whatsapp_mental import lock_phone

UNAVAILABLE = 'Não foi possível vincular esta resposta a um acompanhamento disponível. Procure a equipe responsável.'


def evidence(db, emitter, reference):
    return db.scalar(select(Evidence).where(Evidence.phone_number_id == emitter,
        Evidence.wamid == reference).execution_options(populate_existing=True))


def lock_reference(db, emitter, sender, reference, *, operation=None):
    row = evidence(db, emitter, reference)
    phones = {sender}
    if row is not None:
        target = db.get(Conversation, row.conversa_contextual_id) if row.conversa_contextual_id else db.get(Legacy, row.conversa_legada_id)
        if target is not None:
            phones.add(target.telefone)
    from app.services.whatsapp_comunicacao import coordinate_many
    coordinate_many(db, emitter, phones, operation=operation, identity_check=False)


def identity_matches(db, row, sender, phone):
    if row.evidencia_estado == 'INVALIDA':
        return False
    expected = row.wa_id if row.evidencia_estado == 'VALIDA' else row.destinatario_solicitado
    if sender != expected:
        return False
    if row.destinatario_solicitado == phone:
        return True
    # Replies may be sent to wa_id instead of the originally requested spelling.
    # Require persisted Meta evidence for this exact conversation and emitter.
    return db.scalar(select(Evidence.id).where(
        Evidence.phone_number_id == row.phone_number_id,
        Evidence.conversa_contextual_id == row.conversa_contextual_id,
        Evidence.conversa_legada_id == row.conversa_legada_id,
        Evidence.evidencia_estado == 'VALIDA', Evidence.destinatario_solicitado == phone,
        Evidence.wa_id == sender).limit(1)) is not None


def refuse(observation, reason):
    observation.clear()
    observation.update(resolucao='REFERENCIA_RECUSADA', resolucao_motivo=reason)
    return UNAVAILABLE


def resolve(db, emitter, sender, reference, content, *, message_id, observation):
    row = evidence(db, emitter, reference)
    if row is None:
        return refuse(observation, 'REFERENCIA_DESCONHECIDA')
    if row.conversa_contextual_id is not None:
        from app.services.whatsapp_mental import lock_execution_scope, valid_scope, OPEN, WhatsAppMentalService
        a, conversation, context, patient, person, now = lock_execution_scope(db, row.conversa_contextual_id)
        if not identity_matches(db, row, sender, conversation.telefone):
            return refuse(observation, 'IDENTIDADE_INCOMPATIVEL')
        if a.telefone != conversation.telefone or conversation.paciente_id != a.paciente_id or conversation.contexto_assistencial_id != a.contexto_assistencial_id:
            return refuse(observation, 'VINCULO_INCOMPATIVEL')
        stop = content.strip().upper() == 'PARAR'
        if conversation.status not in OPEN or (conversation.expires_at <= now and not stop):
            return refuse(observation, 'CONVERSA_INDISPONIVEL')
        if not stop and not valid_scope(db, a, context, patient, person, now):
            return refuse(observation, 'ACOMPANHAMENTO_INDISPONIVEL')
        # The clinical receiver continues to own SIM/PARAR and all transitions.
        response = WhatsAppMentalService().receive(db, conversation.id, content, message_id=message_id)
        observation.update(resolucao='REFERENCIA_CONTEXTUAL', conversa_contextual_id=conversation.id)
        return response
    if row.conversa_legada_id is None:
        return refuse(observation, 'SEM_VINCULO_ASSISTENCIAL')
    return resolve_legacy(db, row, sender, content, observation)


def resolve_legacy(db, row, sender, content, observation):
    from app.models.responsavel import Responsavel
    from app.services.daily_record.concurrency import lock_responsible
    from app.services.whatsapp_conversation_service import processar_mensagem, normalizar_telefone
    from app.services.whatsapp_daily_record import authorized_lines
    initial = db.get(Legacy, row.conversa_legada_id)
    if initial is None:
        return refuse(observation, 'SEM_VINCULO_ASSISTENCIAL')
    lock_responsible(db, initial.responsavel_id)
    responsible = db.scalar(select(Responsavel).where(Responsavel.id == initial.responsavel_id).execution_options(populate_existing=True))
    if not responsible or not responsible.ativo or normalizar_telefone(responsible.telefone) != initial.telefone:
        return refuse(observation, 'VINCULO_INCOMPATIVEL')
    if initial.paciente_id is None:
        return refuse(observation, 'SEM_VINCULO_ASSISTENCIAL')
    try:
        lines = authorized_lines(db, initial.responsavel_id, initial.paciente_id)
    except ValueError:
        return refuse(observation, 'VINCULO_INCOMPATIVEL')
    conversation = db.scalar(select(Legacy).where(Legacy.id == initial.id).with_for_update().execution_options(populate_existing=True))
    if not identity_matches(db, row, sender, conversation.telefone):
        return refuse(observation, 'IDENTIDADE_INCOMPATIVEL')
    # Legacy rows are reused; transaction-start timestamps alone cannot identify
    # the episode under concurrent processing. Historical evidence has no backfill.
    from app.services.whatsapp_transporte import legacy_state
    if row.legado_estado_sha256 is None:
        return refuse(observation, 'EVIDENCIA_LEGADA_INSUFICIENTE')
    if row.legado_estado_sha256 != legacy_state(conversation):
        return refuse(observation, 'REFERENCIA_DESATUALIZADA')
    if conversation.etapa_atual in ('INICIO', 'CONCLUIDA', 'ENCERRADA'):
        return refuse(observation, 'CONVERSA_INDISPONIVEL')
    if conversation.data_referencia is not None and conversation.data_referencia not in (date.today(), date.today()-timedelta(days=1)):
        return refuse(observation, 'CONVERSA_INDISPONIVEL')
    if not lines or (conversation.care_line not in [line.code for line in lines] and conversation.etapa_atual != 'SELECIONAR_LINHA'):
        return refuse(observation, 'VINCULO_INCOMPATIVEL')
    response = processar_mensagem(db, conversation.telefone, content, selected=conversation)
    observation.update(resolucao='REFERENCIA_LEGADA', conversa_legada_id=conversation.id)
    return response
