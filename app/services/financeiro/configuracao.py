"""Gate A configuration; caller owns authorization and the outer transaction.

No endpoint, access grant, clinical write, price resolver or implicit commit.
"""
from functools import wraps
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.models.financeiro import (ServicoEconomico, TabelaPreco, TabelaPrecoVersao,
    PrecoServico, ContratoFinanceiro, PacienteContrato, MapeamentoAgendaServico)
from app.models.usuario import Usuario
from app.schemas.financeiro import (ServicoCreate, TabelaCreate, VersaoCreate,
    PrecoCreate, ContratoCreate, PacienteContratoCreate, MapeamentoCreate)


class FinanceiroErro(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def atomic(method):
    @wraps(method)
    def run(self, db, *args, **kwargs):
        if db.new or db.dirty or db.deleted:
            raise FinanceiroErro('CLEAN_SESSION_REQUIRED')
        if db.execute(text('SHOW transaction_isolation')).scalar() != 'read committed':
            raise FinanceiroErro('READ_COMMITTED_REQUIRED')
        with db.begin_nested():
            return method(self, db, *args, **kwargs)
    return run


class FinanceiroConfiguracaoService:
    SCHEMAS = {
        ServicoEconomico: ServicoCreate, TabelaPreco: TabelaCreate,
        TabelaPrecoVersao: VersaoCreate, PrecoServico: PrecoCreate,
        ContratoFinanceiro: ContratoCreate, PacienteContrato: PacienteContratoCreate,
        MapeamentoAgendaServico: MapeamentoCreate,
    }

    @staticmethod
    def _row(db, model, identity):
        row = db.query(model).filter_by(id=identity).populate_existing().with_for_update().first()
        if row is None:
            raise FinanceiroErro('NOT_FOUND')
        return row

    @staticmethod
    def _draft(row):
        if row.estado != 'DRAFT':
            raise FinanceiroErro('PUBLISHED_IMMUTABLE')

    @staticmethod
    def _publisher(db, actor_id):
        if not db.query(Usuario.id).filter_by(id=actor_id, ativo=True).first():
            raise FinanceiroErro('INVALID_PUBLISHER')

    def _payer(self, db, data):
        table = self._row(db, TabelaPreco, data.tabela_preco_id)
        if table.proprietario_instituicao_id != data.pagador_instituicao_id:
            raise FinanceiroErro('PAYER_TABLE_MISMATCH')

    @atomic
    def create(self, db, model, payload):
        if model not in self.SCHEMAS:
            raise FinanceiroErro('INVALID_CONFIGURATION')
        data = self.SCHEMAS[model].model_validate(payload)
        if model is ContratoFinanceiro:
            self._payer(db, data)
        if model is PrecoServico:
            self._draft(self._row(db, TabelaPrecoVersao, data.versao_id))
        if model is MapeamentoAgendaServico:
            existing = db.query(model).filter_by(agenda_cuidado_id=data.agenda_cuidado_id).populate_existing().first()
            if existing:
                if existing.servico_id != data.servico_id:
                    raise FinanceiroErro('MAPPING_CONFLICT')
                return existing
        try:
            with db.begin_nested():
                row = model(**data.model_dump())
                db.add(row)
                db.flush()
                return row
        except IntegrityError as exc:
            if (model is not MapeamentoAgendaServico or getattr(exc.orig, 'pgcode', None) != '23505'
                or getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None) != 'uq_mapeamento_agenda_servico'):
                raise
            row = db.query(model).filter_by(agenda_cuidado_id=data.agenda_cuidado_id).populate_existing().first()
            if row is None or row.servico_id != data.servico_id:
                raise FinanceiroErro('MAPPING_CONFLICT') from exc
            return row

    @atomic
    def update_service(self, db, identity, payload):
        data = ServicoCreate.model_validate(payload)
        row = self._row(db, ServicoEconomico, identity)
        semantic = ('codigo','ocupacao_id','duracao_minutos','tipo_atendimento','unidade')
        if any(getattr(row, f) != getattr(data, f) for f in semantic):
            used = (db.query(PrecoServico.id).filter_by(servico_id=identity).first()
                    or db.query(MapeamentoAgendaServico.id).filter_by(servico_id=identity).first())
            if used:
                raise FinanceiroErro('SERVICE_IN_USE')
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        db.flush()
        return row

    @atomic
    def update_price(self, db, identity, payload):
        data = PrecoCreate.model_validate(payload)
        row = self._row(db, PrecoServico, identity)
        for version_id in sorted({row.versao_id, data.versao_id}):
            self._draft(self._row(db, TabelaPrecoVersao, version_id))
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        db.flush()
        return row

    @atomic
    def delete_price(self, db, identity):
        row = self._row(db, PrecoServico, identity)
        self._draft(self._row(db, TabelaPrecoVersao, row.versao_id))
        db.delete(row)
        db.flush()

    @atomic
    def update_draft(self, db, model, identity, payload):
        if model not in (TabelaPrecoVersao, ContratoFinanceiro):
            raise FinanceiroErro('INVALID_CONFIGURATION')
        data = self.SCHEMAS[model].model_validate(payload)
        if model is ContratoFinanceiro:
            self._payer(db, data)
        row = self._row(db, model, identity)
        self._draft(row)
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        db.flush()
        return row

    @atomic
    def publish_version(self, db, identity, *, actor_id):
        self._publisher(db, actor_id)
        table_id = db.query(TabelaPrecoVersao.tabela_id).filter_by(id=identity).scalar()
        if table_id is None:
            raise FinanceiroErro('NOT_FOUND')
        self._row(db, TabelaPreco, table_id)
        row = self._row(db, TabelaPrecoVersao, identity)
        self._draft(row)
        if row.tabela_id != table_id:
            raise FinanceiroErro('CONCURRENT_CONFIGURATION_CHANGE')
        now = db.execute(text('SELECT clock_timestamp()')).scalar()
        utc_date = db.execute(text("SELECT (clock_timestamp() AT TIME ZONE 'UTC')::date")).scalar()
        if row.vigente_desde < utc_date:
            raise FinanceiroErro('RETROACTIVE_PUBLICATION')
        row.estado = 'PUBLISHED'
        row.publicado_em = now
        row.publicado_por_usuario_id = actor_id
        db.flush()
        db.refresh(row)
        return row

    @atomic
    def publish_contract(self, db, identity, *, actor_id):
        self._publisher(db, actor_id)
        row = self._row(db, ContratoFinanceiro, identity)
        self._draft(row)
        self._payer(db, row)
        row.estado = 'PUBLISHED'
        row.publicado_em = db.execute(text('SELECT clock_timestamp()')).scalar()
        row.publicado_por_usuario_id = actor_id
        db.flush()
        db.refresh(row)
        return row

    @atomic
    def change_mapping(self, db, identity, *, servico_id):
        row = self._row(db, MapeamentoAgendaServico, identity)
        data = MapeamentoCreate(agenda_cuidado_id=row.agenda_cuidado_id, servico_id=servico_id)
        row.servico_id = data.servico_id
        db.flush()
        return row
