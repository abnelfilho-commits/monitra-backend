"""Administrative identity unit of work. Caller commits or rolls back everything.

No authentication provisioning, clinical authorization, or institutional changes.
"""
import hashlib
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.models import Pessoa, Paciente, Profissional, Responsavel, Usuario
from app.models.atividade_terapeutica import OcupacaoProfissional
from app.models.identidade_operacao import IdentidadeOperacao
from app.schemas.identidade import IdentidadeComando, AdicionarPapel, AssociarPapelLegado, AssociarContaLegada
from app.services.pessoa import PessoaService


class IdentidadeErro(Exception):
    def __init__(self, code, fields=(), status=409):
        self.code, self.fields, self.status = code, sorted(fields), status
        super().__init__(code)


def constraint_violation(exc, name):
    return (getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None)) == "23505" and getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == name


ROLES = {"PACIENTE": (Paciente, "paciente_id"), "PROFISSIONAL": (Profissional, "profissional_id"), "RESPONSAVEL": (Responsavel, "responsavel_id")}
PERSON_FIELDS = ("nome_completo", "nome_social", "data_nascimento", "sexo", "cpf", "email", "telefone", "ativo")


class IdentidadeService:
    @staticmethod
    def _admin(db, actor):
        user = db.query(Usuario).filter_by(id=actor, ativo=True).first()
        if user is None or user.perfil != "ADMIN":
            raise IdentidadeErro("ADMIN_REQUIRED", status=403)

    @staticmethod
    def _result(op):
        return {"operacao_id": op.id, "pessoa_id": op.pessoa_id, "resultado": op.resultado,
                "paciente_id": op.paciente_id, "profissional_id": op.profissional_id,
                "responsavel_id": op.responsavel_id, "usuario_id": op.usuario_id}

    def localizar(self, db, actor, cpf):
        self._admin(db, actor)
        from app.schemas.identidade import CpfConsulta
        cpf = CpfConsulta(cpf=cpf).cpf
        person = db.query(Pessoa).filter_by(cpf=cpf).first()
        if person is None:
            return {"encontrada": False}
        return {"encontrada": True, "pessoa": {"id": person.id, **{f: getattr(person, f) for f in PERSON_FIELDS}}}

    def resultado(self, db, actor, key):
        self._admin(db, actor)
        op = db.query(IdentidadeOperacao).filter_by(chave_idempotencia=key).first()
        if op is None:
            raise IdentidadeErro("OPERATION_NOT_FOUND", status=404)
        return self._result(op)

    @staticmethod
    def _resolve_person(db, data):
        person = db.query(Pessoa).filter_by(cpf=data.cpf).populate_existing().with_for_update().first()
        created = False
        if person is None:
            try:
                with db.begin_nested():
                    person = PessoaService.create(db, data)
                created = True
            except IntegrityError as exc:
                if not constraint_violation(exc, "uq_pessoas_cpf"):
                    raise
                # READ COMMITTED statement snapshot sees the committed winner.
                person = db.query(Pessoa).filter_by(cpf=data.cpf).populate_existing().with_for_update().one()
        if not created:
            different = [f for f in data.model_fields_set if getattr(person, f) != getattr(data, f)]
            if different:
                raise IdentidadeErro("CADASTRAL_CONFLICT", different)
        return person, created

    @staticmethod
    def _context(row, requested):
        if requested is not None and row.clinica_id != requested:
            raise IdentidadeErro("INSTITUTIONAL_CONTEXT_PENDING")

    def executar(self, db, actor, command):
        """Use a clean Session; all reads/writes share its READ COMMITTED transaction."""
        if type(command) not in (IdentidadeComando, AdicionarPapel, AssociarPapelLegado, AssociarContaLegada):
            raise IdentidadeErro("INVALID_COMMAND", status=422)
        self._admin(db, actor)
        if db.execute(text("SHOW transaction_isolation")).scalar() != "read committed":
            raise IdentidadeErro("READ_COMMITTED_REQUIRED")
        kind = {IdentidadeComando: "PESSOA", AdicionarPapel: "ADICIONAR_PAPEL",
                AssociarPapelLegado: "ASSOCIAR_PAPEL", AssociarContaLegada: "ASSOCIAR_CONTA"}[type(command)]
        normalized = {"tipo": kind, "payload": command.model_dump(mode="json", exclude_unset=True)}
        # Serializes identical keys; a hash collision only serializes unrelated work.
        lock = int.from_bytes(hashlib.sha256(command.chave_idempotencia.bytes).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        prior = db.query(IdentidadeOperacao).filter_by(chave_idempotencia=command.chave_idempotencia).first()
        if prior:
            if prior.ator_usuario_id != actor or prior.requisicao_normalizada != normalized:
                raise IdentidadeErro("IDEMPOTENCY_CONFLICT")
            return self._result(prior)
        if isinstance(command, AdicionarPapel):
            if command.papel != "PROFISSIONAL" and (command.especialidade is not None or command.ocupacao_id is not None):
                raise IdentidadeErro("INVALID_ROLE_ATTRIBUTES", status=422)
        person, created = self._resolve_person(db, command.pessoa)
        target = {}; previous = None
        result = "PESSOA_CRIADA" if created else "PESSOA_REUTILIZADA"
        if kind != "PESSOA":
            model, column = (Usuario, "usuario_id") if kind == "ASSOCIAR_CONTA" else ROLES[command.papel]
            existing = db.query(model).filter_by(pessoa_id=person.id).populate_existing().with_for_update().first()
            if kind == "ADICIONAR_PAPEL":
                if existing:
                    self._context(existing, command.contexto_clinica_id)
                    if model is Profissional:
                        fields = [f for f in ("especialidade", "ocupacao_id") if f in command.model_fields_set and getattr(existing, f) != getattr(command, f)]
                        if fields:
                            raise IdentidadeErro("ROLE_ATTRIBUTES_CONFLICT", fields)
                    row = existing
                    result = "PAPEL_REUTILIZADO"
                else:
                    if model is Responsavel:
                        raise IdentidadeErro("ROLE_CREATION_UNAVAILABLE_THIS_PHASE")
                    if command.contexto_clinica_id is not None:
                        raise IdentidadeErro("INSTITUTIONAL_CONTEXT_PENDING")
                    args = dict(pessoa_id=person.id, nome=person.nome_completo, ativo=False, clinica_id=None)
                    if model is Paciente:
                        args.update(data_nascimento=person.data_nascimento, genero=None, profissional_id=None)
                    else:
                        if command.ocupacao_id is not None and not db.query(OcupacaoProfissional).filter_by(id=command.ocupacao_id, ativo=True).first():
                            raise IdentidadeErro("INVALID_OCCUPATION", status=422)
                        args.update(especialidade=command.especialidade, ocupacao_id=command.ocupacao_id)
                    row = model(**args)
                    db.add(row)
                    db.flush()
                    result = "PAPEL_CRIADO"
            else:
                row = db.query(model).filter_by(id=command.registro_id).populate_existing().with_for_update().first()
                if row is None:
                    raise IdentidadeErro("LEGACY_RECORD_NOT_FOUND", status=404)
                self._context(row, command.contexto_clinica_id)
                if row.pessoa_id not in (None, person.id) or (existing and existing.id != row.id):
                    raise IdentidadeErro("ASSOCIATION_CONFLICT")
                differences = set()
                if row.nome != person.nome_completo:
                    differences.add("nome")
                if model is Paciente and row.data_nascimento != person.data_nascimento:
                    differences.add("data_nascimento")
                if differences != set(command.divergencias_confirmadas):
                    raise IdentidadeErro("LEGACY_CADASTRAL_CONFLICT", differences)
                previous = row.pessoa_id
                row.pessoa_id = person.id
                result = "ASSOCIACAO_REUTILIZADA" if previous == person.id else "LEGADO_ASSOCIADO"
                db.flush()
            target[column] = row.id
        op = IdentidadeOperacao(chave_idempotencia=command.chave_idempotencia, ator_usuario_id=actor,
            tipo_operacao=kind, pessoa_id=person.id, pessoa_anterior_id=previous, resultado=result,
            motivo=command.motivo, tipo_evidencia=getattr(command, "tipo_evidencia", None),
            referencia_evidencia=getattr(command, "referencia_evidencia", None),
            requisicao_normalizada=normalized, **target)
        db.add(op)
        db.flush()
        return self._result(op)
