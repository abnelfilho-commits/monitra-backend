"""Stage 3A: dormant, read-only resolution. Never dispatches or authorizes writes.

Stage 3B must revalidate under harmonized locks before executing any decision.
No phone heuristics, environment switch or import from the live ingress.
"""
from dataclasses import dataclass, asdict
from datetime import date, timedelta
import hashlib
import json
from sqlalchemy import select, or_
from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel as Evidence
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Mental, AcompanhamentoWhatsApp as Follow
from app.models.whatsapp_conversa import WhatsAppConversa as Legacy
from app.models.responsavel import Responsavel
from app.services.whatsapp_conversation_service import normalizar_telefone
from app.services.whatsapp_transporte import legacy_state

UNAVAILABLE = 'Não foi possível identificar uma conversa disponível. Procure a equipe responsável.'
AMBIGUOUS = 'Há mais de uma conversa disponível. Responda diretamente à mensagem do acompanhamento que deseja continuar.'


@dataclass(frozen=True)
class Candidate:
    kind: str
    conversation_id: int
    evidence_ids: tuple
    reason: str


@dataclass(frozen=True)
class Decision:
    outcome: str
    candidates: tuple
    selected: object = None
    fallback_responsible_id: object = None

    def audit(self):
        # Internal IDs only. Never include phone, text, names or clinical values.
        return dict(version=1, outcome=self.outcome,
                    candidates=[asdict(c) for c in self.candidates],
                    selected=list(self.selected) if self.selected else None,
                    fallback_responsible_id=self.fallback_responsible_id)

    @property
    def response(self):
        return AMBIGUOUS if self.outcome == 'AMBIGUA' else UNAVAILABLE


def identity(rows, sender, phone):
    """All evidence is already restricted to one emitter AND one conversation."""
    direct = [r for r in rows if r.destinatario_solicitado == phone]
    mappings = {r.wa_id for r in direct if r.evidencia_estado == 'VALIDA'}
    if any(r.evidencia_estado == 'INVALIDA' for r in direct) or len(mappings) > 1:
        return 'IDENTIDADE_CONFLITANTE', ()
    if mappings:
        if sender not in mappings:
            return 'IDENTIDADE_CONFLITANTE', ()
        ids = tuple(sorted(r.id for r in direct if r.evidencia_estado == 'VALIDA' and r.wa_id == sender))
        return 'OK', ids
    if sender == phone:
        return 'OK', tuple(sorted(r.id for r in direct if r.evidencia_estado == 'AUSENTE'))
    return 'IDENTIDADE_NAO_COMPROVADA', ()


def mental_reason(db, c, now):
    from app.services.whatsapp_mental import valid_scope, OPEN, Context, Paciente, Pessoa
    from app.models.institucional import Instituicao, PacienteInstituicao
    from app.services.whatsapp_autorizacao import require_prior_authorization
    from app.services.checkin_bem_estar import CheckinInvalid
    a = db.get(Follow, c.acompanhamento_whatsapp_id, populate_existing=True)
    context = db.get(Context, c.contexto_assistencial_id, populate_existing=True)
    patient = db.get(Paciente, c.paciente_id, populate_existing=True)
    person = db.get(Pessoa, patient.pessoa_id, populate_existing=True) if patient and patient.pessoa_id else None
    institution = db.get(Instituicao, context.instituicao_id, populate_existing=True) if context else None
    if not a or a.telefone != c.telefone or a.paciente_id != c.paciente_id or a.contexto_assistencial_id != c.contexto_assistencial_id:
        return 'VINCULO_INCOMPATIVEL'
    if c.status not in OPEN or c.expires_at <= now:
        return 'CONVERSA_INDISPONIVEL'
    link = db.get(PacienteInstituicao, context.paciente_instituicao_id, populate_existing=True) if context else None
    if not link or not link.ativo or link.paciente_id != c.paciente_id or link.instituicao_id != context.instituicao_id or link.data_inicio > now.date() or (link.data_fim is not None and link.data_fim < now.date()):
        return 'VINCULO_INCOMPATIVEL'
    if not context or not institution or not institution.ativo or not valid_scope(db, a, context, patient, person, now):
        return 'ACOMPANHAMENTO_INDISPONIVEL'
    try:
        require_prior_authorization(db, a)
    except CheckinInvalid:
        return 'AUTORIZACAO_INDISPONIVEL'
    return 'OK'


def legacy_reason(db, c, rows, today):
    from app.services.whatsapp_daily_record import eligible_lines
    responsible = db.get(Responsavel, c.responsavel_id, populate_existing=True)
    if not responsible or not responsible.ativo or normalizar_telefone(responsible.telefone) != c.telefone or c.paciente_id is None:
        return 'VINCULO_INCOMPATIVEL'
    try:
        lines = eligible_lines(db, c.responsavel_id, c.paciente_id)
    except ValueError:
        return 'VINCULO_INCOMPATIVEL'
    navigation = {'SELECIONAR_LINHA', 'SELECIONAR_DATA', 'CONFIRMAR_ONTEM', 'CONFIRMAR_INICIO'}
    neuro = {'SONO','EVACUACAO','BRISTOL','IRRITABILIDADE','CRISE_SENSORIAL','TEMPO_TELA','SELETIVIDADE','ALIMENTO_NOVO','OBSERVACAO','CONFIRMAR_REGISTRO'}
    from app.services.whatsapp_cardio import FIELDS
    steps = navigation | (neuro if c.care_line == 'NEURO' else {'CARDIO_' + str(i) for i in range(len(FIELDS)+1)} if c.care_line == 'CARDIO' else set())
    if c.etapa_atual not in steps or (c.data_referencia is not None and c.data_referencia not in (today, today-timedelta(days=1))):
        return 'CONVERSA_INDISPONIVEL'
    if not lines or (c.care_line not in [line.code for line in lines] and c.etapa_atual != 'SELECIONAR_LINHA'):
        return 'VINCULO_INCOMPATIVEL'
    # Rows are reused: an alias bridge must not revive a previous episode.
    if rows and not any(r.legado_estado_sha256 == legacy_state(c) for r in rows):
        return 'EVIDENCIA_LEGADA_DESATUALIZADA'
    return 'OK'


def resolve(db, emitter, sender, content, *, now=None, today=None):
    """Pure candidate collection. No flush, locks, receipts, expiry or handlers.

    Caller must use a fresh consistent read transaction; selection is a proposal,
    not a capability. Historical/conflicting matches prohibit legacy fallback.
    """
    from app.services.whatsapp_mental import now_utc
    if db.new or db.dirty or db.deleted:
        raise ValueError('Resolution requires a clean session')
    if not emitter or not sender.isascii() or not sender.isdigit() or not 8 <= len(sender) <= 15:
        raise ValueError('Invalid transport identity')
    with db.no_autoflush:
        now = now or now_utc(db)
        today = today or date.today()  # Same civil-date contract as legacy receiver.
        matching = list(db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter,
            or_(Evidence.destinatario_solicitado == sender, Evidence.wa_id == sender))))
        considered = []
        for kind, model, field in (('MENTAL', Mental, 'conversa_contextual_id'), ('LEGADO', Legacy, 'conversa_legada_id')):
            ids = {getattr(r, field) for r in matching if getattr(r, field) is not None}
            conversations = db.scalars(select(model).where(or_(model.telefone == sender, model.id.in_(ids))).execution_options(populate_existing=True))
            for c in conversations:
                rows = list(db.scalars(select(Evidence).where(Evidence.phone_number_id == emitter,
                    getattr(Evidence, field) == c.id)))
                reason, evidence_ids = identity(rows, sender, c.telefone)
                if reason == 'OK':
                    if kind == 'MENTAL':
                        reason = mental_reason(db, c, now)
                    else:
                        supporting = [r for r in rows if r.id in evidence_ids]
                        reason = legacy_reason(db, c, supporting, today)
                considered.append(Candidate(kind, c.id, tuple(sorted(r.id for r in rows)), reason))
        considered = tuple(sorted(considered, key=lambda c: (c.kind, c.conversation_id)))
        if content.strip().upper() == 'PARAR':
            return Decision('PARAR_REQUER_BLOQUEIO_3B', considered)
        if any(c.reason in ('IDENTIDADE_CONFLITANTE', 'IDENTIDADE_NAO_COMPROVADA') for c in considered):
            return Decision('IDENTIDADE_RECUSADA', considered)
        eligible = [c for c in considered if c.reason == 'OK']
        if len(eligible) > 1:
            return Decision('AMBIGUA', considered)
        if len(eligible) == 1:
            c = eligible[0]
            return Decision('UNICA', considered, (c.kind, c.conversation_id))
        # Never send SIM into a newly-created legacy questionnaire. No heuristics.
        if considered or matching or db.scalar(select(Follow.id).where(Follow.telefone == sender).limit(1)) or content.strip().upper() == 'SIM':
            return Decision('INDISPONIVEL', considered)
        exact = [r for r in db.scalars(select(Responsavel).where(Responsavel.ativo.is_(True)))
                 if normalizar_telefone(r.telefone) == sender]
        # Only a fresh, bound, unique responsible can enter the legacy menu.
        if len(exact) == 1:
            from app.models.responsavel_paciente import ResponsavelPaciente
            from app.services.whatsapp_daily_record import eligible_lines
            links = db.scalars(select(ResponsavelPaciente).where(ResponsavelPaciente.responsavel_id == exact[0].id, ResponsavelPaciente.ativo.is_(True)))
            for link in links:
                try:
                    if eligible_lines(db, exact[0].id, link.paciente_id):
                        return Decision('FALLBACK_SEGURO', considered, fallback_responsible_id=exact[0].id)
                except ValueError:
                    continue
        return Decision('INDISPONIVEL', considered)


def record_proposal(db, message_id, emitter, sender, content):
    """Dormant audit integration; caller owns receipt transaction and commit.

    Serializes only duplicate proposals, NOT candidate preparation/execution.
    Replay returns the original audit even if eligibility subsequently changes.
    Requires a v2 unreferenced receipt; never alters that receipt or dispatches.
    """
    from app.models.whatsapp_mensagem import WhatsAppMensagem
    from app.models.whatsapp_resolucao import WhatsAppResolucao
    receipt = db.scalar(select(WhatsAppMensagem).where(
        WhatsAppMensagem.message_id == message_id).with_for_update())
    fingerprint = hashlib.sha256(json.dumps([emitter, sender, content, None], ensure_ascii=False).encode()).hexdigest()
    if not receipt or receipt.context_wamid is not None or receipt.fingerprint_versao != 2 or receipt.phone_number_id != emitter or receipt.fingerprint != fingerprint:
        raise ValueError('Routing receipt identity conflict')
    old = db.get(WhatsAppResolucao, message_id)
    if old is not None:
        return old.decisao
    proposal = json.loads(json.dumps(resolve(db, emitter, sender, content).audit()))
    db.add(WhatsAppResolucao(message_id=message_id, decisao=proposal))
    db.flush()
    return proposal
