"""Read-only contextual transport evidence; never derive clinical consent."""
from sqlalchemy import select
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Conversa
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio, WhatsAppConviteStatusEvento as Evento
from app.services.whatsapp_mental import WhatsAppMentalService


def evidence(row):
    # Never return arbitrary upstream text, even from historical stored rows.
    return dict(id=row.id, status=row.status, evento_em=row.evento_em,
                recebido_em=row.recebido_em, meta_error_code=row.meta_error_code,
                meta_error_subcode=row.meta_error_subcode,
                motivo=('META_ERROR_'+str(row.meta_error_code)) if row.meta_error_code is not None
                else ('META_DELIVERY_FAILED' if row.status == 'failed' else None))


def diagnose(db, **scope):
    follow = WhatsAppMentalService().read(db, **scope)
    result = dict(acompanhamento_id=follow.id if follow else None, conversas=[])
    if follow is None:
        return result
    result['assistencial'] = dict(status=follow.status, consentimento=follow.consentimento_status,
                                 consentido_em=follow.consentido_em, revogado_em=follow.revogado_em)
    conversations = db.scalars(select(Conversa).where(
        Conversa.acompanhamento_whatsapp_id == follow.id,
        Conversa.contexto_assistencial_id == scope['context']).order_by(Conversa.id)).all()
    for conversation in conversations:
        attempts = db.scalars(select(Envio).where(Envio.conversa_id == conversation.id)
                              .order_by(Envio.tentativa)).all()
        legacy = conversation.convite_enviado_em is not None and not any(a.wamid for a in attempts)
        item = dict(conversa_id=conversation.id, estado_assistencial=conversation.status,
                    criado_em=conversation.created_at, expira_em=conversation.expires_at,
                    convite_enviado_em=conversation.convite_enviado_em,
                    ausencia_rastreabilidade_historica=legacy,
                    observacao_historica='Aceitação local histórica conhecida; entrega não confirmada.' if legacy else None,
                    tentativas=[])
        for attempt in attempts:
            rows = db.scalars(select(Evento).where(Evento.envio_id == attempt.id,
                Evento.phone_number_id == attempt.phone_number_id, Evento.wamid == attempt.wamid)
                .order_by(Evento.evento_em, Evento.id)).all()
            states = {r.status for r in rows}
            strongest = next((s for s in ('read', 'delivered', 'sent') if s in states), None)
            item['tentativas'].append(dict(id=attempt.id, tentativa=attempt.tentativa,
                estado=attempt.estado, wamid=attempt.wamid,
                aceito_meta=attempt.estado == 'ACEITO', rejeitado_meta=attempt.estado == 'REJEITADO',
                resultado_incerto=attempt.estado in ('EM_EXECUCAO', 'INCERTO'),
                preparado_em=attempt.preparado_em, iniciado_em=attempt.iniciado_em,
                confirmado_em=attempt.confirmado_em, graph_http_status=attempt.graph_http_status,
                meta_error_code=attempt.meta_error_code, meta_error_subcode=attempt.meta_error_subcode,
                ultimo_evento=evidence(rows[-1]) if rows else None,
                maior_confirmacao_observada=strongest,
                envio_informado='sent' in states, entrega_confirmada=bool(states & {'delivered','read'}),
                leitura_informada='read' in states, falha_informada='failed' in states,
                evidencia_contraditoria='failed' in states and bool(states & {'sent','delivered','read'}),
                eventos=[evidence(r) for r in rows]))
        result['conversas'].append(item)
    return result
