"""Gate B read-only orchestration; authorization is a separate caller obligation.

The caller must authorize both clinical patient access and the explicit economic
context. Neither a selected contract nor PacienteContrato grants access.
Use a dedicated clean Session in a PostgreSQL REPEATABLE READ READ ONLY transaction.
This module never commits, rolls back, flushes, schedules or persists a preview.
"""
from collections import defaultdict

from sqlalchemy import text
from app.models.financeiro import PacienteContrato
from app.schemas.financeiro import (PreviewRequest, PreviewResponse,
    PreviewCoverage, PreviewPending, ServiceTotal, MonthTotal)
from app.services.financeiro.neuro_reader import read_neuro
from app.services.financeiro.calculator import summarize
from app.services.financeiro.resolution import economic_context, economic_inputs, resolve_items, rows



def require_snapshot(db):
    if db.new or db.dirty or db.deleted:
        raise ValueError('Preview exige sessão sem alterações pendentes')
    if db.get_bind().dialect.name != 'postgresql':
        raise ValueError('Preview exige PostgreSQL com snapshot consistente')
    if (db.scalar(text('SHOW transaction_isolation')) != 'repeatable read'
            or db.scalar(text('SHOW transaction_read_only')) != 'on'):
        raise ValueError('Preview exige transação REPEATABLE READ READ ONLY do chamador')


class FinancialProjectionService:
    def preview(self, db, payload):
        request = PreviewRequest.model_validate(payload)
        with db.no_autoflush:
            require_snapshot(db)
            return self._preview(db, request)

    def _preview(self, db, request):
        plan = read_neuro(db, request)
        contract, table = economic_context(db, request)
        links = rows(db, PacienteContrato, PacienteContrato.paciente_id == request.paciente_id,
                     PacienteContrato.contrato_id == request.contrato_id) if table else []
        items = resolve_items(plan, contract, table, links,
                              economic_inputs(db, request, plan, table))
        by_service, by_month = defaultdict(list), defaultdict(list)
        for item in items:
            by_month[item.data_economica.strftime('%Y-%m')].append(item)
            if item.servico_id is not None:
                by_service[item.servico_id].append(item)
        totals = summarize(items)
        return PreviewResponse(
            **request.model_dump(), itens=tuple(items),
            totais_por_servico=tuple(ServiceTotal(servico_id=k, **summarize(v)) for k, v in sorted(by_service.items())),
            totais_por_mes=tuple(MonthTotal(mes=k, **summarize(v)) for k, v in sorted(by_month.items())),
            subtotal_precificado=totals['subtotal_precificado'],
            cobertura=PreviewCoverage(sessoes_elegiveis=len(items),
                sessoes_mapeadas=sum(i.mapeamento_id is not None for i in items),
                sessoes_precificadas=totals['quantidade_precificada'],
                sessoes_pendentes=totals['quantidade_pendente'],
                agendas_sem_sessoes_elegiveis=plan.agendas_without_sessions,
                aplicabilidade='APLICAVEL' if items else 'N/A'),
            pendencias=tuple(PreviewPending(sessao_id=i.sessao_id, codigo=i.pendencia)
                             for i in items if i.pendencia is not None))
