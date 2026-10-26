"""WhatsApp is a channel for BEM_ESTAR_V1, not a clinical scoring engine."""
import hashlib
from datetime import timedelta
from sqlalchemy import select, func, text, or_
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation
from app.models.contexto_assistencial import ContextoAssistencial as Context, ContextoAssistencialLinha as Line
from app.models.paciente import Paciente
from app.models.pessoa import Pessoa
from app.services.whatsapp_conversation_service import normalizar_telefone
from app.services.checkin_contract import FIELDS, YES_NO
from app.services.checkin_bem_estar import CheckinBemEstarService, CheckinDenied, CheckinInvalid
from app.services.permissao_assistencial import PermissaoAssistencialService

OPEN = ('AGUARDANDO_ACEITE', 'EM_ANDAMENTO')
QUESTIONS = {n: (label, options) for n, label, options in FIELDS}
ORDER = [n for n, _, options in FIELDS if options]


def now_utc(db):
    return db.scalar(select(func.clock_timestamp()))


def lock_phone(db, phone):
    key = int.from_bytes(hashlib.sha256(normalizar_telefone(phone).encode()).digest()[:8], 'big', signed=True)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})


def locked(db, model, identity):
    return db.scalar(select(model).where(model.id == identity).with_for_update().execution_options(populate_existing=True))


def lock_care(db, context_id):
    # Same institution serializer as W1B. Identity parents precede context roles.
    initial = db.get(Context, context_id)
    if initial is None:
        raise CheckinDenied('CHECKIN_UNAVAILABLE')
    PermissaoAssistencialService.lock_institution(db, initial.instituicao_id)
    patient = db.get(Paciente, initial.paciente_id)
    person = locked(db, Pessoa, patient.pessoa_id) if patient and patient.pessoa_id else None
    context = locked(db, Context, context_id)
    patient = locked(db, Paciente, context.paciente_id)
    db.execute(select(Line).where(Line.contexto_assistencial_id == context_id,
                                 Line.modulo_id == 3).with_for_update()).all()
    return context, patient, person


def lock_execution_scope(db, identity):
    initial = db.get(Conversation, identity)
    if initial is None:
        raise CheckinDenied('CHECKIN_UNAVAILABLE')
    lock_phone(db, initial.telefone)
    c, patient, person = lock_care(db, initial.contexto_assistencial_id)
    a = locked(db, Follow, initial.acompanhamento_whatsapp_id)
    conversation = locked(db, Conversation, identity)
    return a, conversation, c, patient, person, now_utc(db)


def valid_scope(db, a, c, patient, person, now):
    return bool(a and a.status == 'ATIVO' and a.consentimento_status != 'REVOGADO'
        and c.ativo and c.data_inicio <= now.date() and c.data_fim is None
        and patient and person and person.ativo and patient.pessoa_id == person.id
        and c.paciente_id == patient.id == a.paciente_id and c.id == a.contexto_assistencial_id
        and db.scalar(select(Line.id).where(Line.contexto_assistencial_id == c.id,
                                            Line.modulo_id == 3, Line.ativo.is_(True))))


def question(step):
    label, options = QUESTIONS[step]
    if not options:
        return label + '. Envie PULAR para continuar sem descrição.'
    return label + '\n' + '\n'.join(f'{i}. {label}' for i, (_, label) in enumerate(options, 1))


def choice(content, options):
    value = content.strip().casefold()
    if options == YES_NO:
        if value in ('sim', 's'): return 'SIM'
        if value in ('não', 'nao', 'n'): return 'NAO'
    if value.isascii() and value.isdigit() and 1 <= int(value) <= len(options):
        return options[int(value)-1][0]
    return None


class WhatsAppMentalService:
    def authorized(self, db, *, actor, institution, person, context, write=True):
        checkin = CheckinBemEstarService()
        if write:
            lock_care(db, context)
            allowed = checkin.can_write(db, actor=actor, institution=institution, person=person, context=context)
        else:
            allowed = db.scalar(checkin._scope(actor, institution, person, context, 'ASSISTENCIAL_LER')) is not None
        if not allowed:
            raise CheckinDenied('CHECKIN_UNAVAILABLE')

    def read(self, db, **scope):
        self.authorized(db, write=False, **scope)
        return db.scalar(select(Follow).where(Follow.contexto_assistencial_id == scope['context']))

    def configure(self, db, phone, **scope):
        phone = normalizar_telefone(phone)
        if not phone.isascii() or not phone.isdigit() or not 8 <= len(phone) <= 15:
            raise CheckinInvalid('INVALID_PHONE')
        old = db.scalar(select(Follow).where(Follow.contexto_assistencial_id == scope['context']))
        # Deterministic order when changing destinations; never alter execution snapshots.
        for number in sorted({phone, old.telefone if old else phone}): lock_phone(db, number)
        self.authorized(db, **scope)
        c = db.get(Context, scope['context'])
        a = db.scalar(select(Follow).where(Follow.contexto_assistencial_id == c.id).with_for_update().execution_options(populate_existing=True))
        if a is None:
            a = Follow(contexto_assistencial_id=c.id, paciente_id=c.paciente_id, telefone=phone,
                       criado_por_usuario_id=scope['actor'], status='ATIVO', consentimento_status='PENDENTE', frequencia='SEMANAL')
            db.add(a)
        elif a.status == 'ENCERRADO' or a.consentimento_status == 'REVOGADO':
            raise CheckinInvalid('FOLLOW_UP_CLOSED')
        elif a.telefone != phone:
            if db.scalar(select(Conversation.id).where(Conversation.acompanhamento_whatsapp_id == a.id, Conversation.status.in_(OPEN))):
                raise CheckinInvalid('OPEN_CONVERSATION')
            from app.services.whatsapp_autorizacao import revoke_internal
            revoke_internal(db, a, origin='TROCA_TELEFONE', reason='TROCA_TELEFONE', actor=scope['actor'])
            a.telefone = phone
            a.consentimento_status = 'PENDENTE'
            a.consentido_em = None
            a.proximo_envio_em = None
        db.flush()
        return a

    def lifecycle(self, db, action, **scope):
        initial = db.scalar(select(Follow).where(Follow.contexto_assistencial_id == scope['context']))
        if initial is None: raise CheckinInvalid('FOLLOW_UP_NOT_FOUND')
        lock_phone(db, initial.telefone)
        self.authorized(db, **scope)
        a = locked(db, Follow, initial.id)
        if action == 'reativar':
            if a.status == 'ENCERRADO' or a.consentimento_status == 'REVOGADO': raise CheckinInvalid('FOLLOW_UP_CLOSED')
            a.status = 'ATIVO'
        else:
            if action == 'encerrar':
                from app.services.whatsapp_autorizacao import revoke_internal
                revoke_internal(db, a, origin='ENCERRAMENTO', reason='ENCERRAMENTO', actor=scope['actor'])
                a.status, a.consentimento_status, a.revogado_em = 'ENCERRADO', 'REVOGADO', now_utc(db)
            elif a.status != 'ENCERRADO': a.status = 'PAUSADO'
            for conversation in db.scalars(select(Conversation).where(Conversation.acompanhamento_whatsapp_id == a.id, Conversation.status.in_(OPEN)).with_for_update()):
                conversation.status = 'CANCELADA'
        db.flush()
        return a

    def eligible_ids(self, db, limit=100):
        """Read-only selection. prepare() rechecks eligibility under locks."""
        from app.services.whatsapp_autorizacao import authorized_follow_exists
        active_line = select(Line.id).where(Line.contexto_assistencial_id == Context.id,
            Line.modulo_id == 3, Line.ativo.is_(True)).exists()
        busy_phone = select(Conversation.id).where(Conversation.telefone == Follow.telefone,
            Conversation.status.in_(OPEN), Conversation.expires_at > func.clock_timestamp()).exists()
        return tuple(db.scalars(select(Follow.id).join(Context, Context.id == Follow.contexto_assistencial_id)
            .join(Paciente, Paciente.id == Context.paciente_id).join(Pessoa, Pessoa.id == Paciente.pessoa_id)
            .where(Follow.status == 'ATIVO', Follow.consentimento_status != 'REVOGADO',
                Follow.paciente_id == Context.paciente_id, Context.ativo.is_(True), Context.data_fim.is_(None),
                Context.data_inicio <= func.current_date(), Pessoa.ativo.is_(True), active_line, ~busy_phone, authorized_follow_exists(),
                or_(Follow.proximo_envio_em.is_(None), Follow.proximo_envio_em <= func.clock_timestamp()))
            .order_by(Follow.id).limit(limit)))

    def prepare(self, db, identity, *, manual=False):
        """Caller commits before delivery. A blocked phone never advances the schedule."""
        initial = db.get(Follow, identity)
        if initial is None: raise CheckinInvalid('FOLLOW_UP_NOT_FOUND')
        phone = initial.telefone
        lock_phone(db, phone)
        c, patient, person = lock_care(db, initial.contexto_assistencial_id)
        a = locked(db, Follow, identity)
        now = now_utc(db)
        if a.telefone != phone: raise CheckinInvalid('DESTINATION_CHANGED')
        from app.services.whatsapp_manual import blocking_attempt, require_prior_authorization
        if blocking_attempt(db, phone, follow_id=identity): return None
        if not valid_scope(db, a, c, patient, person, now): return None
        try:
            require_prior_authorization(db, a)
        except CheckinInvalid:
            if manual: raise
            return None
        # Expiry closes a fixed window; replies cannot extend it.
        for old in db.scalars(select(Conversation).where(Conversation.telefone == phone, Conversation.status.in_(OPEN)).with_for_update()):
            if old.expires_at <= now: old.status = 'EXPIRADA'
        db.flush()
        if not valid_scope(db, a, c, patient, person, now): return None
        if not manual and a.proximo_envio_em is not None and a.proximo_envio_em > now: return None
        if db.scalar(select(Conversation.id).where(Conversation.telefone == phone, Conversation.status.in_(OPEN))): return None
        conversation = Conversation(acompanhamento_whatsapp_id=a.id, contexto_assistencial_id=c.id,
            paciente_id=patient.id, telefone=phone, care_line='MENTAL_HEALTH', etapa_atual='ACEITE',
            respostas_json={}, status='AGUARDANDO_ACEITE', data_referencia=now.date(),
            created_at=now, expires_at=now+timedelta(hours=24))
        db.add(conversation)
        if not manual: a.proximo_envio_em = now+timedelta(days=7)
        db.flush()
        return conversation

    def deliver_invitation(self, db, identity, *, context, explicit_retry=False):
        from app.services.whatsapp_convite_envio import deliver
        return deliver(db, identity, context, explicit_retry=explicit_retry)

    def receive(self, db, identity, content, *, message_id=None):
        a, conversation, c, patient, person, now = lock_execution_scope(db, identity)
        if conversation.status not in OPEN: return 'Esta execução já foi encerrada.'
        if content.strip().upper() == 'PARAR':
            from app.services.whatsapp_autorizacao import revoke_internal
            revoke_internal(db, a, origin='WHATSAPP_PARAR', reason='PARAR', conversation=conversation.id, message=message_id)
            a.status, a.consentimento_status, a.revogado_em = 'ENCERRADO', 'REVOGADO', now
            conversation.status = 'CANCELADA'
            db.flush()
            return 'Acompanhamento WhatsApp encerrado. Não enviaremos novos convites.'
        if conversation.expires_at <= now:
            conversation.status = 'EXPIRADA'
            db.flush()
            return 'Este check-in expirou. Nenhum check-in incompleto foi registrado.'
        if not valid_scope(db,a,c,patient,person,now):
            conversation.status = 'CANCELADA'
            db.flush()
            return 'Este check-in não está disponível.'
        if conversation.status == 'AGUARDANDO_ACEITE':
            answer = choice(content, YES_NO)
            if answer == 'NAO':
                conversation.status = 'CANCELADA'
                db.flush()
                return 'Tudo bem. Este check-in foi cancelado. Envie PARAR durante um próximo convite para encerrar o acompanhamento.'
            if answer != 'SIM': return 'Integra Care — Check-in de Bem-Estar. Aceita participar? 1. Sim 2. Não. PARAR encerra o acompanhamento.'
            a.consentimento_status = 'CONSENTIDO'
            if a.consentido_em is None: a.consentido_em = now
            conversation.status, conversation.etapa_atual = 'EM_ANDAMENTO', ORDER[0]
            db.flush()
            return question(ORDER[0])
        if a.consentimento_status != 'CONSENTIDO':
            conversation.status = 'CANCELADA'
            db.flush()
            return 'Este check-in não está disponível.'
        step = conversation.etapa_atual
        if step == 'evento_descricao':
            answer = '' if content.strip().upper() == 'PULAR' else content.strip()
            if len(answer) > 2000: return 'Use até 2000 caracteres ou envie PULAR.'
        else:
            answer = choice(content, QUESTIONS[step][1])
            if answer is None: return 'Resposta inválida.\n' + question(step)
        answers = dict(conversation.respostas_json)
        if answer: answers[step] = answer
        conversation.respostas_json = answers
        if step == 'pedido_ajuda':
            db.flush()
            CheckinBemEstarService().create_self_report(db, conversation_id=conversation.id)
            conversation.status = 'CONCLUIDA'
            db.flush()
            return 'Check-in de Bem-Estar registrado. Obrigado por participar.'
        next_step = ('evento_descricao' if step == 'evento_relevante' and answer == 'SIM'
                     else 'pedido_ajuda' if step in ('evento_relevante','evento_descricao')
                     else ORDER[ORDER.index(step)+1])
        conversation.etapa_atual = next_step
        db.flush()
        return question(next_step)


def dispatch(db, sender, content, legacy, *, message_id=None, observation=None):
    phone = normalizar_telefone(sender)
    lock_phone(db, phone)
    identity = db.scalar(select(Conversation.id).where(Conversation.telefone == phone, Conversation.status.in_(OPEN)))
    if identity is None:
        if observation is not None:
            observation['resolucao'] = 'LEGADO_SEM_CONVERSA'
        return legacy(db, sender, content)
    if observation is not None:
        observation.update(resolucao='CONTEXTUAL_ATUAL', conversa_contextual_id=identity)
    return WhatsAppMentalService().receive(db, identity, content, message_id=message_id)
