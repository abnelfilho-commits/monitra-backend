"""Gate B read-only orchestration; authorization is a separate caller obligation.

The caller must authorize both clinical patient access and the explicit economic
context. Neither a selected contract nor PacienteContrato grants access.
Use a dedicated clean Session in a PostgreSQL REPEATABLE READ READ ONLY transaction.
This module never commits, rolls back, flushes, schedules or persists a preview.
"""
from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict

from sqlalchemy import select, text
from app.models.financeiro import (ContratoFinanceiro, TabelaPreco, PacienteContrato,
    MapeamentoAgendaServico, ServicoEconomico, TabelaPrecoVersao, PrecoServico)
from app.models.institucional import Instituicao
from app.schemas.financeiro import (PreviewRequest, PreviewResponse, PreviewItem,
    PreviewCoverage, PreviewPending, ServiceTotal, MonthTotal)
from app.services.financeiro.neuro_reader import read_neuro
from app.services.financeiro.calculator import subtotal, summarize


def rows(db, model, *conditions):
    return db.execute(select(model.__table__).where(*conditions)).mappings().all()


class FinancialProjectionService:
    def preview(self, db, payload):
        request = PreviewRequest.model_validate(payload)
        if db.new or db.dirty or db.deleted:
            raise ValueError('Preview exige sessão sem alterações pendentes')
        with db.no_autoflush:
            if db.get_bind().dialect.name != 'postgresql':
                raise ValueError('Preview exige PostgreSQL com snapshot consistente')
            if (db.scalar(text('SHOW transaction_isolation')) != 'repeatable read'
                    or db.scalar(text('SHOW transaction_read_only')) != 'on'):
                raise ValueError('Preview exige transação REPEATABLE READ READ ONLY do chamador')
            return self._preview(db, request)

    def _preview(self, db, request):
        plan = read_neuro(db, request)
        contracts = rows(db, ContratoFinanceiro,
                         ContratoFinanceiro.id == request.contrato_id,
                         ContratoFinanceiro.pagador_instituicao_id == request.instituicao_id,
                         ContratoFinanceiro.estado == 'PUBLISHED')
        institution = db.scalar(select(Instituicao.id).where(
            Instituicao.id == request.instituicao_id, Instituicao.ativo.is_(True)))
        contract = contracts[0] if contracts and institution is not None else None
        table = None
        if contract:
            tables = rows(db, TabelaPreco, TabelaPreco.id == contract['tabela_preco_id'],
                          TabelaPreco.proprietario_instituicao_id == request.instituicao_id,
                          TabelaPreco.moeda == 'BRL')
            table = tables[0] if tables else None
        links = rows(db, PacienteContrato, PacienteContrato.paciente_id == request.paciente_id,
                     PacienteContrato.contrato_id == request.contrato_id) if table else []
        agendas = {s.agenda_id for s in plan.sessions}
        mappings = {r['agenda_cuidado_id']: r for r in rows(
            db, MapeamentoAgendaServico, MapeamentoAgendaServico.agenda_cuidado_id.in_(agendas))}
        services = {r['id']: r for r in rows(db, ServicoEconomico,
                    ServicoEconomico.id.in_({m['servico_id'] for m in mappings.values()}))}
        versions = sorted(rows(db, TabelaPrecoVersao,
                          TabelaPrecoVersao.tabela_id == table['id'],
                          TabelaPrecoVersao.estado == 'PUBLISHED',
                          TabelaPrecoVersao.vigente_desde <= request.data_fim),
                          key=lambda r: (r['vigente_desde'], r['id'])) if table else []
        prices = {(r['versao_id'], r['servico_id']): r for r in rows(
            db, PrecoServico, PrecoServico.versao_id.in_([v['id'] for v in versions]),
            PrecoServico.servico_id.in_(services))}
        dates = [v['vigente_desde'] for v in versions]
        items = []
        for session in plan.sessions:
            data = asdict(session)
            data.pop('duracao_agenda')
            mapping = mappings.get(session.agenda_id)
            service = services.get(mapping['servico_id']) if mapping else None
            if mapping:
                data.update(mapeamento_id=mapping['id'], servico_id=mapping['servico_id'])
            if service:
                data['servico_codigo'] = service['codigo']
            day = session.data_economica
            pending = None
            if (not contract or not table or day < contract['inicio']
                    or (contract['fim'] is not None and day > contract['fim'])
                    or not any(link['inicio'] <= day and (link['fim'] is None or day <= link['fim']) for link in links)):
                pending = 'NO_CONTRACT'
            else:
                data['tabela_id'] = table['id']
                if not mapping:
                    pending = 'NO_ECONOMIC_SERVICE_MAPPING'
                elif (not service or not service['ativo'] or service['unidade'] != 'SESSAO'
                      or service['tipo_atendimento'] != 'INDIVIDUAL'
                      or service['ocupacao_id'] != session.ocupacao_id
                      or service['duracao_minutos'] != session.duracao_minutos
                      or service['duracao_minutos'] != session.duracao_agenda):
                    pending = 'INCOMPATIBLE_ECONOMIC_SERVICE_MAPPING'
                else:
                    pos = bisect_right(dates, day) - 1
                    if pos < 0:
                        pending = 'NO_APPLICABLE_PRICE_TABLE_VERSION'
                    else:
                        version = versions[pos]
                        data.update(versao_id=version['id'], versao_numero=version['numero'],
                                    vigente_desde=version['vigente_desde'])
                        price = prices.get((version['id'], service['id']))
                        if price is None:
                            pending = 'NO_PRICE'
                        else:
                            data.update(preco_id=price['id'], codigo_externo=price['codigo_externo'],
                                        preco_unitario=price['valor_base'], subtotal=subtotal(price['valor_base']))
            items.append(PreviewItem(**data, estado='PENDENTE' if pending else 'CALCULADO', pendencia=pending))
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
