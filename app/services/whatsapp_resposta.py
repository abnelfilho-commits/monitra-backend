"""Durable text execution. Never retry an uncertain external result."""
import os
from sqlalchemy import select
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.models.whatsapp_comunicacao import WhatsAppRespostaExecucao as Execution
from app.services.whatsapp_comunicacao import coordinate, require_output
from app.services.whatsapp_mental import now_utc
from app.services.checkin_bem_estar import CheckinInvalid


def deliver(db, identity, sender):
    from app.services.whatsapp_sender_service import WhatsAppSenderService, MetaInvitationRejected
    from app.services.whatsapp_convite_envio import capture_wamid
    emitter = os.getenv('WHATSAPP_PHONE_NUMBER_ID','')
    try:
        coordinate(db,emitter,sender,operation='reply:'+identity)
        initial=db.get(Receipt,identity)
        if initial is None or initial.phone_number_id != emitter:
            raise CheckinInvalid('RECEIPT_IDENTITY_CONFLICT')
        # Care locks before receipt/execution rows, no stronger legacy identity locks.
        if initial.conversa_contextual_id:
            from app.services.whatsapp_mental import lock_execution_scope
            lock_execution_scope(db,initial.conversa_contextual_id)
        receipt=db.scalar(select(Receipt).where(Receipt.message_id==identity).with_for_update())
        prior=db.get(Execution,identity)
        if prior is not None:
            if prior.phone_number_id != emitter or prior.destinatario != sender:
                raise CheckinInvalid('EXECUTION_IDENTITY_CONFLICT')
            db.rollback();return False  # PREPARADO also requires explicit reconciliation.
        if receipt.enviado_em is not None or not receipt.resposta:
            db.rollback();return False
        require_output(db,emitter,sender,conversation_id=receipt.conversa_contextual_id)
        values=dict(conversa_contextual_id=receipt.conversa_contextual_id,conversa_legada_id=receipt.conversa_legada_id)
        execution=Execution(mensagem_id=identity,phone_number_id=emitter,destinatario=sender,
            estado='PREPARADO',origem='SAUDE_MENTAL' if receipt.conversa_contextual_id else 'LEGADO' if receipt.conversa_legada_id else 'NAVEGACAO',**values)
        db.add(execution);db.commit()
        # Revalidate barrier after first durable boundary, before authorizing IO.
        coordinate(db,emitter,sender,operation='reply:'+identity)
        if values['conversa_contextual_id']:
            from app.services.whatsapp_mental import lock_execution_scope
            lock_execution_scope(db,values['conversa_contextual_id'])
        require_output(db,emitter,sender,conversation_id=values['conversa_contextual_id'])
        receipt=db.scalar(select(Receipt).where(Receipt.message_id==identity).with_for_update())
        execution=db.scalar(select(Execution).where(Execution.mensagem_id==identity).with_for_update())
        if execution.estado != 'PREPARADO': db.rollback();return False
        body, snapshot = receipt.resposta, receipt.legado_estado_sha256
        execution.estado='EM_EXECUCAO';execution.iniciado_em=now_utc(db)
        db.commit()
    except CheckinInvalid as exc:
        db.rollback()
        if str(exc) in ('WHATSAPP_INTERROMPIDO','COMMUNICATION_NOT_AUTHORIZED','PRIOR_WHATSAPP_AUTHORIZATION_REVOKED','PRIOR_WHATSAPP_AUTHORIZATION_ABSENT'):
            return False
        raise
    except Exception:
        db.rollback();raise
    observed_wamid = None
    try:
        # No ORM access or transaction during HTTP. No external retries here.
        result=WhatsAppSenderService.enviar_texto(sender,body,expected_phone_id=emitter)
        wamid=capture_wamid(result)
        observed_wamid=wamid
        from app.services.whatsapp_convite_status import lock_message
        lock_message(db,emitter,wamid)
        receipt=db.scalar(select(Receipt).where(Receipt.message_id==identity).with_for_update())
        execution=db.scalar(select(Execution).where(Execution.mensagem_id==identity).with_for_update())
        execution.wamid=wamid;execution.estado='CONFIRMADO';execution.graph_http_status=200
        execution.concluido_em=now_utc(db);receipt.enviado_em=execution.concluido_em.replace(tzinfo=None)
        if values['conversa_contextual_id'] or values['conversa_legada_id']:
            from app.services.whatsapp_transporte import capture
            capture(db,result,emitter=emitter,requested=sender,contextual=values['conversa_contextual_id'],
                    legacy=values['conversa_legada_id'],origin='META_RESPOSTA',legacy_snapshot=snapshot)
        db.commit();return True
    except Exception as exc:
        # A lost commit response may already have CONFIRMADO. Never overwrite it.
        db.rollback()
        try:
            execution=db.scalar(select(Execution).where(Execution.mensagem_id==identity).with_for_update())
            if execution and execution.estado=='EM_EXECUCAO':
                execution.estado='FALHA_DEFINITIVA' if isinstance(exc,MetaInvitationRejected) else 'INCERTO'
                execution.graph_http_status=exc.http_status if isinstance(exc,MetaInvitationRejected) else (200 if observed_wamid else None)
                if observed_wamid is not None:
                    execution.wamid=observed_wamid
                execution.concluido_em=now_utc(db)
                db.commit()
            else: db.rollback()
        except Exception: db.rollback() # Durable EM_EXECUCAO still blocks retries.
        raise


def evidence(db, identity):
    """Internal read-only reconciliation. Never upgrades execution from delivery status."""
    from app.models.whatsapp_convite import WhatsAppConviteStatusEvento as Status
    row=db.get(Execution,identity)
    if row is None: return None
    events=list(db.scalars(select(Status).where(Status.phone_number_id==row.phone_number_id,
        Status.wamid==row.wamid).order_by(Status.evento_em,Status.id))) if row.wamid else []
    return dict(estado=row.estado,wamid=row.wamid,eventos=[dict(status=e.status,evento_em=e.evento_em,codigo=e.meta_error_code) for e in events])
