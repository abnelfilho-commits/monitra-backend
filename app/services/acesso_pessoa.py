"""Native person-first account provisioning. Caller owns the transaction.

PROFISSIONAL is only the existing technical compatibility default: without
clinic, professional or modules it grants no care-line access. Institutional
profiles and W1B entitlements remain independent. Never reset a reused password.
"""
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.models.usuario import Usuario
from app.models.pessoa import Pessoa
from app.models.institucional import Instituicao
from app.core.security import hash_senha
from app.services.autorizacao_institucional import AutorizacaoInstitucionalService


class AcessoPessoaErro(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class AcessoPessoaService:
    def enable(self, db, person_id, data, *, actor_id):
        canonical = AutorizacaoInstitucionalService()
        canonical._write_gate(db, actor_id)
        person = db.query(Pessoa).filter_by(id=person_id).with_for_update().populate_existing().first()
        if person is None:
            raise AcessoPessoaErro('PERSON_NOT_FOUND', 404)
        if not person.ativo:
            raise AcessoPessoaErro('PERSON_INACTIVE')
        institution = db.query(Instituicao).filter_by(id=data.instituicao_id).with_for_update(read=True).populate_existing().first()
        if institution is None:
            raise AcessoPessoaErro('INSTITUTION_NOT_FOUND', 404)
        if not institution.ativo:
            raise AcessoPessoaErro('INSTITUTION_INACTIVE')
        user = db.query(Usuario).filter_by(pessoa_id=person.id).with_for_update().populate_existing().first()
        email = str(data.email).lower()
        # Refuse collisions including legacy case variants; never claim an
        # unassociated legacy account just because its email matches.
        owners = db.query(Usuario).filter(func.lower(Usuario.email) == email.lower()).all()
        if any(row.pessoa_id != person.id for row in owners):
            raise AcessoPessoaErro('EMAIL_CONFLICT')
        if user is not None:
            if user.email.lower() != email:
                raise AcessoPessoaErro('PERSON_EMAIL_CONFLICT')
            if not user.ativo:
                raise AcessoPessoaErro('USER_INACTIVE')
        else:
            try:
                with db.begin_nested():
                    user = Usuario(nome=person.nome_completo, email=email,
                        senha_hash=hash_senha(data.senha_inicial.get_secret_value()),
                        pessoa_id=person.id, perfil='PROFISSIONAL', ativo=True,
                        clinica_id=None, profissional_id=None)
                    db.add(user)
                    db.flush()
            except IntegrityError as exc:
                if getattr(exc.orig, 'pgcode', None) == '23505':
                    raise AcessoPessoaErro('ACCOUNT_CONFLICT') from None
                raise
        access = canonical.create(db, dict(usuario_id=user.id,
            instituicao_id=data.instituicao_id, perfil_institucional=data.perfil_institucional,
            ativo=data.ativo), actor_id=actor_id)
        return dict(pessoa_id=person.id, usuario_id=user.id, email=user.email,
                    usuario_ativo=user.ativo, autorizacao=access)
