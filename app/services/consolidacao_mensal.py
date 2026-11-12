"""Internal ADMIN-only monthly management projection; no individual data output.

A separate PostgreSQL connection owns a read-only REPEATABLE READ transaction.
Only committed data is read; the caller's transaction and pending ORM state are
never flushed, committed, rolled back or reconfigured. No public endpoint.
"""
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal, localcontext, ROUND_HALF_UP

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.services.capacidade_mensal import CapacidadeMensalService
from app.services.demanda_mensal import DemandaMensalService, SOURCE as DEMAND_SOURCE


@contextmanager
def _snapshot(db):
    bind = db.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine
    if engine.dialect.name != 'postgresql':
        raise ValueError('MONTHLY_SNAPSHOT_REQUIRES_POSTGRESQL')
    # Options apply to this checked-out connection, not the application's engine.
    with engine.connect() as raw:
        connection = raw.execution_options(isolation_level='REPEATABLE READ', postgresql_readonly=True)
        transaction = connection.begin()
        try:
            with Session(bind=connection, autoflush=False, expire_on_commit=False) as reader:
                yield reader
        finally:
            if transaction.is_active:
                transaction.rollback()


def _decimal(value):
    return str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _indicators(demand, capacity):
    projected = demand['total_minutos_vigentes_projetados']
    numerator = capacity['numerador']
    capacity_ok = capacity['capacidade_mensal_total'] is not None
    qualities = (demand['qualidade'], capacity['qualidade'])
    quality = next(q for q in ('INCONSISTENTE', 'INCOMPLETO', 'ESTIMADO', 'CONCLUSIVO') if q in qualities)
    with localcontext() as ctx:
        ctx.prec = max(40, len(str(abs(numerator))) + len(str(abs(projected or 0))) + 20)
        equivalent = Decimal(numerator) / Decimal(7)
        balance = equivalent - Decimal(projected) if capacity_ok and projected is not None else None
        utilization = (Decimal(projected) * 700 / Decimal(numerator)
                       if capacity_ok and numerator > 0 and projected is not None else None)
        reason = ('CAPACIDADE_ZERO' if capacity_ok and numerator == 0 else
                  'CAPACIDADE_NAO_CONCLUSIVA' if not capacity_ok else
                  'DEMANDA_NAO_CALCULAVEL' if projected is None else None)
        counts = Counter((source, p['codigo']) for source, result in
                         (('DEMANDA', demand), ('CAPACIDADE', capacity)) for p in result['pendencias'])
        return dict(unidade='MINUTOS_MENSAIS', demanda_mensal_projetada=projected,
            demanda_persistida_conhecida=demand['minutos_vigentes_persistidos'],
            demanda_estimada_conhecida=demand['minutos_vigentes_estimados'],
            demanda_subtotal_parcial=demand['subtotais_parciais'],
            capacidade_mensal_conhecida=_decimal(equivalent),
            capacidade_mensal_equivalente=_decimal(equivalent) if capacity_ok else None,
            capacidade_subtotal_parcial=not capacity_ok,
            saldo_mensal=_decimal(balance) if balance is not None else None,
            utilizacao_percentual=_decimal(utilization) if utilization is not None else None,
            motivo_utilizacao_nula=reason, qualidade=quality,
            qualidade_demanda=qualities[0], qualidade_capacidade=qualities[1],
            conclusivo=quality == 'CONCLUSIVO',
            pendencias=[dict(origem=source, codigo=code, quantidade=count)
                        for (source, code), count in sorted(counts.items())])


class ConsolidacaoMensalService:
    def calculate(self, db, *, instituicao_id, mes_referencia, actor_id, ocupacao_id=None):
        from app.services.institucional import InstitucionalService, InstitucionalErro
        # Validate transport values without touching the caller's connection.
        CapacidadeMensalService._period(instituicao_id, mes_referencia, ocupacao_id)
        with _snapshot(db) as reader:
            InstitucionalService._admin(reader, actor_id)
            active = reader.execute(text('SELECT ativo FROM instituicoes WHERE id=:id'),
                                    {'id': instituicao_id}).first()
            if active is None:
                raise InstitucionalErro('CAPACITY_INSTITUTION_NOT_FOUND')
            if not active[0]:
                raise InstitucionalErro('CAPACITY_INSTITUTION_INACTIVE')
            args = dict(instituicao_id=instituicao_id, mes_referencia=mes_referencia,
                        ocupacao_id=ocupacao_id)
            demand_engine, capacity_engine = DemandaMensalService(), CapacidadeMensalService()
            demand = demand_engine.calculate(reader, **args)
            capacity = capacity_engine.calculate(reader, actor_id=actor_id, **args)
            if ocupacao_id is not None:
                occupations = [ocupacao_id]
            else:
                # Reuse M1's source population, not a second eligibility algorithm.
                # Unassignable legacy records never define institutional occupations.
                query = text('SELECT DISTINCT ocupacao_id FROM (' + str(DEMAND_SOURCE) +
                             ') AS demand_population WHERE instituicao_id IS NOT NULL AND ocupacao_id > 0')
                occupations = sorted(set(reader.execute(query, {'institution': instituicao_id,
                    'occupation': None}).scalars()) | {o['ocupacao_id'] for o in capacity['ocupacoes']
                                                       if o['ocupacao_id'] is not None})
            groups = []
            for occupation in occupations:
                if ocupacao_id is not None:
                    d, c = demand, capacity
                else:
                    filtered = dict(args, ocupacao_id=occupation)
                    d = demand_engine.calculate(reader, **filtered)
                    c = capacity_engine.calculate(reader, actor_id=actor_id, **filtered)
                groups.append(dict(ocupacao_id=occupation, **_indicators(d, c)))
            return dict(instituicao_id=instituicao_id, mes_referencia=mes_referencia,
                        ocupacao_id=ocupacao_id, **_indicators(demand, capacity), ocupacoes=groups,
                        base_historica='ESTADO_CADASTRAL_ATUAL_SEM_RECONSTRUCAO')
