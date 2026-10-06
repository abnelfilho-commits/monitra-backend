"""Minimal operational metadata and adapters. No role-based clinical shortcut."""
from app.models.usuario import Usuario
from app.models.pessoa import Pessoa
from app.models.profissional import Profissional
from app.models.institucional import Instituicao, ProfissionalInstituicao
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Root
from app.models.contexto_assistencial import ContextoAssistencial as Context, ContextoAssistencialLinha as Line
from app.models.modular import ModuloClinico
from app.models.permissao_assistencial import AutoridadeDelegacao as Authority, ConcessaoAssistencial as Grant, ContextoProfissional as Participation
from app.schemas.permissao_assistencial import ConcessaoAssistencialRecord, AutoridadeDelegacaoRecord, ContextoProfissionalRecord
from app.schemas.contexto_assistencial import ContextoLinhaOut
from app.services.permissao_assistencial import PermissaoAssistencialService, PermissaoAssistencialErro
from app.services.contexto_assistencial import ContextoAssistencialService

CAPABILITIES = ('CONTEXTO_ADMINISTRAR', 'ASSISTENCIAL_LER', 'ASSISTENCIAL_REGISTRAR')


class OperacaoAssistencialService(PermissaoAssistencialService):
    def actor(self, db, actor_id):
        actor = self._row(db, Usuario, actor_id)
        if not actor.ativo:
            raise PermissaoAssistencialErro('ACTOR_INACTIVE')
        if actor.perfil != 'ADMIN':
            self._person(db, actor)
        return actor

    def rights(self, db, actor, institution, context):
        # The same domain predicates decide rendering and command enforcement.
        caps = []
        try:
            self._person(db, actor)
        except PermissaoAssistencialErro:
            return caps, False
        for cap in CAPABILITIES:
            try:
                self._authority(db, actor.id, institution, cap, 'CONTEXTO', context)
                caps.append(cap)
            except PermissaoAssistencialErro as exc:
                if exc.code != 'AUTHORITY_DENIED':
                    raise
        try:
            self._participation_authority(db, actor.id, institution, context)
            participation = True
        except PermissaoAssistencialErro as exc:
            if exc.code != 'CONTEXT_ADMINISTRATION_DENIED':
                raise
            participation = False
        return caps, participation

    def scope(self, db, actor_id, institution, context):
        actor = self.actor(db, actor_id)
        inst = self._row(db, Instituicao, institution)
        if not inst.ativo:
            raise PermissaoAssistencialErro('INSTITUTION_INACTIVE')
        row = self._context(db, context, institution)
        caps, participation = self.rights(db, actor, institution, context)
        if actor.perfil != 'ADMIN' and not caps and not participation:
            raise PermissaoAssistencialErro('OPERATION_DENIED')
        return actor, row, caps, participation

    def institutions(self, db, actor_id):
        actor = self.actor(db, actor_id)
        rows = db.query(Instituicao).filter_by(ativo=True).order_by(Instituicao.id).all()
        if actor.perfil != 'ADMIN':
            allowed = {r.instituicao_id for r in db.query(Root).filter_by(usuario_id=actor.id, ativo=True)}
            rows = [r for r in rows if r.id in allowed and any(
                any(self.rights(db, actor, r.id, c.id)) for c in db.query(Context).filter_by(instituicao_id=r.id, ativo=True))]
        return [dict(id=r.id, nome=r.nome_fantasia or r.razao_social) for r in rows]

    def contexts(self, db, actor_id, institution):
        actor = self.actor(db, actor_id)
        if not self._row(db, Instituicao, institution).ativo:
            raise PermissaoAssistencialErro('INSTITUTION_INACTIVE')
        rows = db.query(Context).filter_by(instituicao_id=institution, ativo=True).order_by(Context.id).all()
        # Structural metadata only: no person names, clinical history or record payloads.
        return [dict(id=r.id, data_inicio=r.data_inicio.isoformat(), data_fim=r.data_fim.isoformat() if r.data_fim else None)
                for r in rows if actor.perfil == 'ADMIN' or any(self.rights(db, actor, institution, r.id))]

    def state(self, db, actor_id, institution, context):
        actor, row, caps, participation = self.scope(db, actor_id, institution, context)
        is_admin = actor.perfil == 'ADMIN'
        eligible = self._eligible_authorities(db, institution)
        history = db.query(Authority.id).filter_by(instituicao_id=institution).first() is not None
        recoverable = [cap for cap in CAPABILITIES if not any(a.capacidade_delegavel == cap and
                       (a.envelope_tipo == 'INSTITUICAO' or a.contexto_assistencial_id == context) for a in eligible)]
        roots = db.query(Root, Usuario).join(Usuario, Usuario.id == Root.usuario_id).join(Pessoa, Pessoa.id == Usuario.pessoa_id).filter(
            Root.instituicao_id == institution, Root.ativo.is_(True), Usuario.ativo.is_(True), Pessoa.ativo.is_(True)).order_by(Root.id).all()
        accounts = [dict(id=r.id, nome=u.nome) for r, u in roots if u.id != actor_id]
        # Eligible clinical target = explicit canonical person equality, never numeric-id matching.
        today = self._now().date()
        professionals = []
        for root, user in roots:
            for link, professional in db.query(ProfissionalInstituicao, Profissional).join(Profissional).filter(
                    ProfissionalInstituicao.instituicao_id == institution, ProfissionalInstituicao.ativo.is_(True),
                    Profissional.ativo.is_(True), Profissional.pessoa_id == user.pessoa_id).order_by(ProfissionalInstituicao.id):
                if link.data_inicio <= today and (link.data_fim is None or link.data_fim >= today):
                    professionals.append(dict(id=link.id, profissional=professional.nome, usuario_instituicao_acesso_id=root.id,
                        data_inicio=link.data_inicio.isoformat(), data_fim=link.data_fim.isoformat() if link.data_fim else None,
                        pode_receber_grant=user.id != actor_id))
        grants = db.query(Grant).filter_by(instituicao_id=institution, contexto_assistencial_id=context).order_by(Grant.id).all()
        authorities = db.query(Authority).filter(Authority.instituicao_id == institution,
            (Authority.contexto_assistencial_id == context) | (Authority.envelope_tipo == 'INSTITUICAO')).order_by(Authority.id).all()
        participations = db.query(Participation).filter_by(instituicao_id=institution, contexto_assistencial_id=context).order_by(Participation.id).all()
        line = db.query(Line).filter_by(contexto_assistencial_id=context, modulo_id=3).one_or_none()
        catalog = db.query(ModuloClinico).filter_by(id=3, slug='saude_mental', ativo=True).first()
        names = {r.id: u.nome for r, u in roots}
        return dict(instituicao_id=institution, contexto_id=context, linha=ContextoLinhaOut.model_validate(line).model_dump() if line else None,
            acoes=dict(ativar_linha=is_admin and row.data_fim is None and bool(catalog) and line is not None and not line.ativo,
                       desativar_linha=is_admin and line is not None and line.ativo,
                       bootstrap=is_admin and not history, recovery_capacidades=recoverable if is_admin and history else [],
                       conceder_capacidades=caps, administrar_participacao=participation),
            contas=accounts if is_admin or caps else [], profissionais=professionals if caps or participation else [],
            autoridades=[dict(AutoridadeDelegacaoRecord.model_validate(a).model_dump(mode='json'), nome=names.get(a.usuario_instituicao_acesso_id)) for a in authorities],
            grants=[dict(ConcessaoAssistencialRecord.model_validate(g).model_dump(mode='json'), nome=names.get(g.usuario_instituicao_acesso_id), pode_revogar=g.capacidade in caps and g.revogado_em is None) for g in grants],
            participacoes=[ContextoProfissionalRecord.model_validate(p).model_dump(mode='json') for p in participations])

    def line(self, db, actor_id, institution, context, active):
        self._gate(db, actor_id, institution, admin=True)
        self._context(db, context, institution)
        line = db.query(Line).filter_by(contexto_assistencial_id=context, modulo_id=3).one_or_none()
        if line is None:
            raise PermissaoAssistencialErro('RESOURCE_NOT_FOUND')
        service = ContextoAssistencialService()
        if active:
            return service.activate_line(db, context, line.id, instituicao_id=institution)
        return service.deactivate_line(db, context, line.id)

    def nominate(self, db, actor_id, institution, context, data, recovery=False):
        self._context(db, context, institution)
        payload = dict(instituicao_id=institution, usuario_instituicao_acesso_id=data.usuario_instituicao_acesso_id,
            motivo=data.motivo, envelopes=[dict(capacidade_delegavel=c, envelope_tipo='CONTEXTO', contexto_assistencial_id=context) for c in data.capacidades])
        return (self.recovery if recovery else self.bootstrap)(db, payload, actor_id=actor_id)

    def contextual_grant(self, db, actor_id, institution, context, data):
        return self.grant(db, dict(data.model_dump(), instituicao_id=institution, contexto_assistencial_id=context, escopo_tipo='CONTEXTO'), actor_id=actor_id)

    def contextual_participation(self, db, actor_id, institution, context, data):
        return self.create_participation(db, dict(data.model_dump(), instituicao_id=institution, contexto_assistencial_id=context), actor_id=actor_id)

    def contextual_revoke(self, db, actor_id, institution, context, identity, data):
        row = self._row(db, Grant, identity)
        if row.instituicao_id != institution or row.contexto_assistencial_id != context:
            raise PermissaoAssistencialErro('INSTITUTION_MISMATCH')
        return self.revoke(db, dict(id=identity, instituicao_id=institution, motivo=data.motivo), actor_id=actor_id)
