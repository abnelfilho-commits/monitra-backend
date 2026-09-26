"""Institutional preview: explicit economic population, batch reads, one snapshot.

Authorization remains the caller's responsibility. run() ends its read-only
transaction before returning the immutable result; drill-down never queries SQL.
No persistence, scheduling, automatic mapping or clinical access is provided.
"""
from collections import defaultdict
from decimal import Decimal, localcontext

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.financeiro import PacienteContrato
from app.schemas.financeiro import (
    InstitutionalPreviewRequest, InstitutionalPreviewResult, InstitutionalSummary,
    InstitutionalItem, ResolutionEvidence, LinkEvidence, PatientTotal,
    MonthTotal, ServiceTotal, PendingTotal,
)
from app.services.care_lines.registry import NEURO
from app.services.financeiro.contracts import NeuroPlan
from app.services.financeiro.neuro_reader import read_neuro_batch
from app.services.financeiro.resolution import economic_context, economic_inputs, resolve_items, rows
from app.services.financeiro.calculator import summarize
from app.services.financeiro.projection import require_snapshot


class InstitutionalProjectionService:
    def run(self, engine, payload, *, batch_size=200):
        """Own and close the snapshot. No transaction survives user navigation."""
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                with Session(bind=connection) as db:
                    return self.preview(db, payload, batch_size=batch_size)
            finally:
                transaction.rollback()

    def preview(self, db, payload, *, batch_size=200):
        """For callers already owning a clean RR/RO snapshot; never closes theirs."""
        request = InstitutionalPreviewRequest.model_validate(payload)
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError('batch_size must be a positive integer')
        if request.modulo_id != NEURO.module_id:
            raise ValueError('Módulo sem contrato assistencial de projeção implementado')
        with db.no_autoflush:
            require_snapshot(db)
            return self._preview(db, request, batch_size)

    def _preview(self, db, request, batch_size):
        contract, table = economic_context(db, request)
        if contract is None or table is None:
            raise ValueError('Contexto econômico institucional inválido')
        start = max(request.data_inicio, contract['inicio'])
        end = min(request.data_fim, contract['fim'] or request.data_fim)
        population = tuple(db.scalars(select(PacienteContrato.paciente_id).where(
            PacienteContrato.contrato_id == request.contrato_id,
            PacienteContrato.inicio <= end,
            or_(PacienteContrato.fim.is_(None), PacienteContrato.fim >= start)
        ).distinct().order_by(PacienteContrato.paciente_id))) if start <= end else ()
        details, patients = [], []
        for offset in range(0, len(population), batch_size):
            ids = population[offset:offset + batch_size]
            plans = read_neuro_batch(db, ids, request)
            links = defaultdict(list)
            for link in sorted(rows(db, PacienteContrato,
                                    PacienteContrato.contrato_id == request.contrato_id,
                                    PacienteContrato.paciente_id.in_(ids)), key=lambda r: r['id']):
                links[link['paciente_id']].append(link)
            combined = NeuroPlan(tuple(s for plan in plans.values() for s in plan.sessions), ())
            inputs = economic_inputs(db, request, combined, table)
            mappings, services, _, _ = inputs
            for pid in ids:
                plan = plans[pid]
                items = resolve_items(plan, contract, table, links[pid], inputs)
                patients.append(PatientTotal(paciente_id=pid, **summarize(items),
                                             agendas_sem_sessoes_elegiveis=plan.agendas_without_sessions))
                for session, item in zip(plan.sessions, items):
                    mapping = mappings.get(session.agenda_id)
                    service = services.get(mapping['servico_id']) if mapping else None
                    evidence = dict(contrato_inicio=contract['inicio'], contrato_fim=contract['fim'],
                                    vinculos=tuple(LinkEvidence(id=r['id'], inicio=r['inicio'], fim=r['fim'])
                                                   for r in links[pid]), duracao_agenda=session.duracao_agenda)
                    if service:
                        for field in ('ativo', 'unidade', 'tipo_atendimento', 'ocupacao_id', 'duracao_minutos'):
                            evidence['servico_' + field] = service[field]
                    details.append(InstitutionalItem(
                        instituicao_id=request.instituicao_id, contrato_id=request.contrato_id,
                        modulo_id=request.modulo_id, paciente_id=pid, item=item,
                        evidencia=ResolutionEvidence(**evidence)))
        details.sort(key=lambda d: (d.item.data_economica, d.paciente_id, d.item.sessao_id))
        items = tuple(d.item for d in details)
        totals = summarize(items)
        by_month, by_service, pending = defaultdict(list), defaultdict(list), defaultdict(list)
        for item in items:
            by_month[item.data_economica.strftime('%Y-%m')].append(item)
            if item.servico_id is not None:
                by_service[item.servico_id].append(item)
            if item.pendencia is not None:
                pending[item.pendencia].append(item)
        with localcontext() as ctx:
            ctx.prec = 28
            coverage = (Decimal(totals['quantidade_precificada']) * 100 / len(items)) if items else None
        return InstitutionalPreviewResult(
            **request.model_dump(), detalhes=tuple(details), pacientes=tuple(patients),
            resumo=InstitutionalSummary(
                **totals, pacientes_economicos=len(population),
                pacientes_com_sessoes=sum(p.quantidade_considerada > 0 for p in patients),
                pacientes_com_itens_precificados=sum(p.quantidade_precificada > 0 for p in patients),
                pacientes_somente_pendentes=sum(p.quantidade_considerada > 0 and p.quantidade_precificada == 0 for p in patients),
                pacientes_sem_sessoes=sum(p.quantidade_considerada == 0 for p in patients),
                sessoes_mapeadas=sum(i.mapeamento_id is not None for i in items),
                cobertura_percentual=coverage,
                completude='SEM_SESSOES' if not items else 'COM_PENDENCIAS' if pending else 'PRECIFICADO'),
            totais_por_mes=tuple(MonthTotal(mes=k, **summarize(v)) for k, v in sorted(by_month.items())),
            totais_por_servico=tuple(ServiceTotal(servico_id=k, **summarize(v)) for k, v in sorted(by_service.items())),
            pendencias=tuple(PendingTotal(codigo=k, **summarize(v)) for k, v in sorted(pending.items())))
