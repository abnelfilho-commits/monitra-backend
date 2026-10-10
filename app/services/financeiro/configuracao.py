"""Gate A configuration; caller owns authorization and the outer transaction.

No endpoint, access grant, clinical write, price resolver or implicit commit.
"""
from functools import wraps
from sqlalchemy import text, or_
from sqlalchemy.exc import IntegrityError
from app.models.financeiro import (ServicoEconomico, TabelaPreco, TabelaPrecoVersao,
    PrecoServico, ContratoFinanceiro, PacienteContrato, MapeamentoAgendaServico)
from app.models.usuario import Usuario
from app.models.institucional import Instituicao, PacienteInstituicao
from app.models.paciente import Paciente
from app.models.atividade_terapeutica import OcupacaoProfissional
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

    def _beneficiary(self, db, data):
        contract = self._row(db, ContratoFinanceiro, data.contrato_id)

        if data.inicio < contract.inicio:
            raise FinanceiroErro('BENEFICIARY_OUTSIDE_CONTRACT_PERIOD')

        if contract.fim is not None:
            if data.fim is None or data.fim > contract.fim:
                raise FinanceiroErro('BENEFICIARY_OUTSIDE_CONTRACT_PERIOD')

        patient = (
            db.query(Paciente)
            .filter(
                Paciente.id == data.paciente_id,
                Paciente.ativo.is_(True),
            )
            .first()
        )
        if patient is None:
            raise FinanceiroErro('INVALID_BENEFICIARY')

        institutional_link = (
            db.query(PacienteInstituicao.id)
            .filter(
                PacienteInstituicao.paciente_id == data.paciente_id,
                PacienteInstituicao.instituicao_id == contract.pagador_instituicao_id,
                PacienteInstituicao.ativo.is_(True),
            )
            .first()
        )
        if institutional_link is None:
            raise FinanceiroErro('BENEFICIARY_PAYER_MISMATCH')

    @atomic
    def create(self, db, model, payload):
        if model not in self.SCHEMAS:
            raise FinanceiroErro('INVALID_CONFIGURATION')
        data = self.SCHEMAS[model].model_validate(payload)
        if model is ContratoFinanceiro:
            self._payer(db, data)
        if model is PacienteContrato:
            self._beneficiary(db, data)
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

    def list_services(self, db, *, identity=None, ativo=None):
        used = or_(
            db.query(PrecoServico.id).filter(PrecoServico.servico_id == ServicoEconomico.id).exists(),
            db.query(MapeamentoAgendaServico.id).filter(MapeamentoAgendaServico.servico_id == ServicoEconomico.id).exists(),
        )
        query = db.query(ServicoEconomico, OcupacaoProfissional.nome, used).join(
            OcupacaoProfissional, OcupacaoProfissional.id == ServicoEconomico.ocupacao_id)
        if identity is not None:
            query = query.filter(ServicoEconomico.id == identity)
        if ativo is not None:
            query = query.filter(ServicoEconomico.ativo == ativo)
        return [dict({field: getattr(row, field) for field in ServicoCreate.model_fields},
                     id=row.id, ocupacao_nome=name, em_uso=in_use)
                for row, name, in_use in query.populate_existing().order_by(ServicoEconomico.codigo, ServicoEconomico.id).all()]

    def get_service(self, db, identity):
        rows = self.list_services(db, identity=identity)
        if not rows:
            raise FinanceiroErro('NOT_FOUND')
        return rows[0]

    @atomic
    def set_service_active(self, db, identity, active):
        row = self._row(db, ServicoEconomico, identity)
        payload = {field: getattr(row, field) for field in ServicoCreate.model_fields}
        payload['ativo'] = active
        return self.update_service(db, identity, payload)

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


    @staticmethod
    def read_row(db, model, identity):
        row = db.query(model).filter_by(id=identity).populate_existing().first()
        if row is None:
            raise FinanceiroErro('NOT_FOUND')
        return row

    def list_tables(self, db, *, identity=None):
        query = db.query(TabelaPreco, Instituicao).join(
            Instituicao, Instituicao.id == TabelaPreco.proprietario_instituicao_id)
        if identity is not None:
            query = query.filter(TabelaPreco.id == identity)
        return [dict({c.name: getattr(row, c.name) for c in TabelaPreco.__table__.columns},
                     proprietario_nome=owner.nome_fantasia or owner.razao_social)
                for row, owner in query.populate_existing().order_by(TabelaPreco.nome, TabelaPreco.id)]

    def get_table(self, db, identity):
        rows = self.list_tables(db, identity=identity)
        if not rows:
            raise FinanceiroErro('NOT_FOUND')
        return rows[0]

    def close_beneficiary(self, db, identity, *, fim):
        link = self._row(db, PacienteContrato, identity)

        if link.fim is not None:
            raise FinanceiroErro('BENEFICIARY_ALREADY_CLOSED')

        if fim < link.inicio:
            raise FinanceiroErro('INVALID_PERIOD')

        contract = self._row(db, ContratoFinanceiro, link.contrato_id)
        if contract.fim is not None and fim > contract.fim:
            raise FinanceiroErro('BENEFICIARY_OUTSIDE_CONTRACT_PERIOD')

        link.fim = fim
        db.flush()
        db.refresh(link)
        return link

    def list_beneficiaries(self, db, contract_id):
        self._row(db, ContratoFinanceiro, contract_id)

        rows = (
            db.query(PacienteContrato, Paciente)
            .join(
                Paciente,
                Paciente.id == PacienteContrato.paciente_id,
            )
            .filter(PacienteContrato.contrato_id == contract_id)
            .populate_existing()
            .order_by(
                Paciente.nome,
                PacienteContrato.inicio.desc(),
                PacienteContrato.id.desc(),
            )
            .all()
        )

        return [
            dict(
                {c.name: getattr(link, c.name) for c in PacienteContrato.__table__.columns},
                paciente_nome=paciente.nome,
                data_nascimento=paciente.data_nascimento,
            )
            for link, paciente in rows
        ]

    def get_beneficiary(self, db, identity):
        rows = (
            db.query(PacienteContrato, Paciente)
            .join(
                Paciente,
                Paciente.id == PacienteContrato.paciente_id,
            )
            .filter(PacienteContrato.id == identity)
            .populate_existing()
            .all()
        )

        if not rows:
            raise FinanceiroErro('NOT_FOUND')

        link, paciente = rows[0]
        return dict(
            {c.name: getattr(link, c.name) for c in PacienteContrato.__table__.columns},
            paciente_nome=paciente.nome,
            data_nascimento=paciente.data_nascimento,
        )

    def list_beneficiary_candidates(self, db, contract_id):
        contract = self._row(db, ContratoFinanceiro, contract_id)

        rows = (
            db.query(Paciente.id, Paciente.nome, Paciente.data_nascimento)
            .join(
                PacienteInstituicao,
                PacienteInstituicao.paciente_id == Paciente.id,
            )
            .filter(
                Paciente.ativo.is_(True),
                PacienteInstituicao.instituicao_id == contract.pagador_instituicao_id,
                PacienteInstituicao.ativo.is_(True),
            )
            .distinct()
            .order_by(Paciente.nome, Paciente.id)
            .all()
        )

        return [
            dict(
                paciente_id=paciente_id,
                paciente_nome=nome,
                data_nascimento=data_nascimento,
            )
            for paciente_id, nome, data_nascimento in rows
        ]

    def list_contracts(self, db, *, identity=None):
        query = db.query(ContratoFinanceiro, Instituicao, TabelaPreco).join(
            Instituicao,
            Instituicao.id == ContratoFinanceiro.pagador_instituicao_id,
        ).join(
            TabelaPreco,
            TabelaPreco.id == ContratoFinanceiro.tabela_preco_id,
        )
        if identity is not None:
            query = query.filter(ContratoFinanceiro.id == identity)
        return [
            dict(
                {c.name: getattr(row, c.name) for c in ContratoFinanceiro.__table__.columns},
                pagador_nome=instituicao.nome_fantasia or instituicao.razao_social,
                tabela_codigo=tabela.codigo,
                tabela_nome=tabela.nome,
            )
            for row, instituicao, tabela in query.populate_existing().order_by(
                Instituicao.nome_fantasia,
                ContratoFinanceiro.codigo,
                ContratoFinanceiro.edicao,
                ContratoFinanceiro.id,
            ).all()
        ]

    def get_contract(self, db, identity):
        rows = self.list_contracts(db, identity=identity)
        if not rows:
            raise FinanceiroErro('NOT_FOUND')
        return rows[0]

    def list_versions(self, db, table_id):
        self.read_row(db, TabelaPreco, table_id)
        return db.query(TabelaPrecoVersao).filter_by(tabela_id=table_id).populate_existing().order_by(
            TabelaPrecoVersao.vigente_desde.desc(), TabelaPrecoVersao.id.desc()).all()

    def list_prices(self, db, version_id):
        version = self.read_row(db, TabelaPrecoVersao, version_id)
        previous = db.query(TabelaPrecoVersao.id).filter(
            TabelaPrecoVersao.tabela_id == version.tabela_id,
            TabelaPrecoVersao.estado == 'PUBLISHED',
            TabelaPrecoVersao.vigente_desde < version.vigente_desde).order_by(
                TabelaPrecoVersao.vigente_desde.desc()).limit(1).scalar()
        rows = db.query(PrecoServico, ServicoEconomico, OcupacaoProfissional.nome).join(
            ServicoEconomico, ServicoEconomico.id == PrecoServico.servico_id).join(
            OcupacaoProfissional, OcupacaoProfissional.id == ServicoEconomico.ocupacao_id).filter(
                PrecoServico.versao_id == version_id).populate_existing().order_by(
                    ServicoEconomico.codigo, PrecoServico.id).all()
        prices = [dict({c.name: getattr(price, c.name) for c in PrecoServico.__table__.columns},
                       servico_codigo=service.codigo, servico_descricao=service.descricao,
                       ocupacao_nome=occupation, duracao_minutos=service.duracao_minutos,
                       servico_ativo=service.ativo) for price, service, occupation in rows]
        current = db.query(PrecoServico.servico_id).filter(PrecoServico.versao_id == version_id)
        omitted = (db.query(PrecoServico.id).filter(PrecoServico.versao_id == previous,
                    ~PrecoServico.servico_id.in_(current)).count() if previous is not None else 0)
        active = sum(p['servico_ativo'] for p in prices)
        return dict(precos=prices, quantidade_precos=len(prices), servicos_ativos=active,
                    servicos_inativos=len(prices)-active, versao_anterior_id=previous,
                    servicos_anteriores_sem_preco=omitted)

    def price_output(self, db, row):
        # One joined query for the written price, without loading a version's entire grid.
        s, occupation = db.query(ServicoEconomico, OcupacaoProfissional.nome).join(
            OcupacaoProfissional, OcupacaoProfissional.id == ServicoEconomico.ocupacao_id).filter(
                ServicoEconomico.id == row.servico_id).one()
        return dict({c.name: getattr(row, c.name) for c in PrecoServico.__table__.columns},
                    servico_codigo=s.codigo, servico_descricao=s.descricao, ocupacao_nome=occupation,
                    duracao_minutos=s.duracao_minutos, servico_ativo=s.ativo)
