"""C2-M1: internal, read-only monthly demand calculation.

This is not an authorization boundary. Only a future authorized caller may expose
its output. No clinical narrative or names are selected. Current flags are not a
historical reconstruction. A complete persisted collection is structurally valid,
not independent evidence of a historical confirmation event.
"""
import calendar
import re
import logging
import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)


STATES = ('AGENDADA', 'CONFIRMADA', 'EM_ANDAMENTO', 'REALIZADA', 'FALTOU',
          'CANCELADA', 'REAGENDADA')
EXCLUDED = frozenset(('CANCELADA', 'REAGENDADA'))

# One selection, no clinical execution tables, no collection joins other than
# sessions. Load the whole schedule, not just its monthly fragment, to check it.
SOURCE = text('''
SELECT a.id AS agenda_id, a.pts_id, a.objetivo_id, a.atividade_id,
       a.ocupacao_id, a.profissional_id, a.frequencia_semanal,
       a.quantidade_sessoes, a.duracao_minutos,
       a.data_inicio AS agenda_inicio, a.data_fim AS agenda_fim,
       p.paciente_id, p.modulo_id, p.contexto_assistencial_id AS contexto_id,
       p.data_inicio AS pts_inicio, p.data_fim AS pts_fim,
       o.pts_id AS objetivo_pts_id,
       c.paciente_id AS contexto_paciente_id, c.instituicao_id,
       c.paciente_instituicao_id AS vinculo_id, c.ativo AS contexto_ativo,
       c.data_inicio AS contexto_inicio, c.data_fim AS contexto_fim,
       v.paciente_id AS vinculo_paciente_id, v.instituicao_id AS vinculo_instituicao_id,
       v.ativo AS vinculo_ativo, v.data_inicio AS vinculo_inicio, v.data_fim AS vinculo_fim,
       s.id AS sessao_id, s.numero_sessao, s.data_agendada,
       s.hora_inicio, s.hora_fim, s.duracao_minutos AS sessao_duracao,
       s.status AS sessao_estado, s.paciente_id AS sessao_paciente_id,
       s.profissional_id AS sessao_profissional_id, s.sessao_origem_id
FROM agenda_cuidados a
JOIN pts p ON p.id=a.pts_id
JOIN pts_objetivos o ON o.id=a.objetivo_id
LEFT JOIN contextos_assistenciais c ON c.id=p.contexto_assistencial_id
LEFT JOIN paciente_instituicoes v ON v.id=c.paciente_instituicao_id
LEFT JOIN sessoes_assistenciais s ON s.agenda_cuidado_id=a.id
WHERE p.status='ATIVO' AND o.status='ABERTO' AND a.status='PLANEJADO'
  AND (:occupation IS NULL OR a.ocupacao_id=:occupation)
  AND (c.instituicao_id=:institution OR v.instituicao_id=:institution OR c.id IS NULL)
''')


def _date(value):
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return None


def _positive(value):
    return type(value) is int and value > 0


def _clock(value):
    from datetime import time
    if isinstance(value, str):
        try:
            value = time.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, time) and value.tzinfo is None:
        return value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1000000
    return None


class DemandaMensalService:
    """All output counts and minutes are integers; blocked totals are None.

    Invalid agendas contribute no partial numbers. Valid subtotals remain visible
    but are marked partial whenever the requested slice cannot be concluded.
    Unassignable legacy plans produce a separate technical log, never an
    institutional completeness warning or an inferred institutional assignment.
    """

    def calculate(self, db, *, instituicao_id, mes_referencia, ocupacao_id=None):
        start, end = self._period(instituicao_id, mes_referencia, ocupacao_id)
        with db.no_autoflush:
            institution = db.execute(text('SELECT ativo FROM instituicoes WHERE id=:id'),
                                     dict(id=instituicao_id)).first()
            if institution is None or not institution[0]:
                raise ValueError('Instituição inexistente ou inativa.')
            rows = db.execute(SOURCE, dict(institution=instituicao_id,
                                           occupation=ocupacao_id)).mappings().all()
        return self._calculate(rows, instituicao_id, ocupacao_id, start, end)

    @staticmethod
    def _period(institution, month, occupation):
        if not _positive(institution) or (occupation is not None and not _positive(occupation)):
            raise ValueError('Identificadores devem ser inteiros positivos.')
        if not isinstance(month, str) or re.fullmatch(r'\d{4}-\d{2}', month) is None:
            raise ValueError('mes_referencia deve usar AAAA-MM.')
        year, number = map(int, month.split('-'))
        start = date(year, number, 1)
        return start, date(year, number, calendar.monthrange(year, number)[1])

    def _calculate(self, rows, institution, occupation, start, end):
        pending, groups = [], defaultdict(list)
        unassigned = set()
        def issue(code, agenda=None, session=None, incomplete=False):
            item = dict(codigo=code, agenda_id=agenda, sessao_id=session,
                        qualidade='INCOMPLETO' if incomplete else 'INCONSISTENTE')
            if item not in pending:
                pending.append(item)

        for source in rows:
            row = dict(source)
            # Unassigned data must not disclose cross-institution identifiers.
            if row['instituicao_id'] is None:
                unassigned.add(row['agenda_id'])
                continue
            if row['instituicao_id'] != institution and row['vinculo_instituicao_id'] != institution:
                continue
            if occupation is not None and row['ocupacao_id'] != occupation:
                continue
            groups[row['agenda_id']].append(row)

        if unassigned:
            logger.warning('C2_M1_CONTEXTO_NAO_ATRIBUIVEL quantidade_planejamentos=%d', len(unassigned))

        status = {state: dict(quantidade=0, minutos=0) for state in STATES}
        persisted = estimated = estimated_count = 0
        depends_on_estimate = False
        accepted, signatures = [], defaultdict(list)
        for agenda, records in groups.items():
            a = records[0]
            dates = [_date(a[key]) for key in ('agenda_inicio', 'agenda_fim')]
            session_dates = [_date(r['data_agendada']) for r in records if r['sessao_id'] is not None]
            overlaps = dates[0] is None or (dates[0] <= end and (dates[1] is None or dates[1] >= start))
            if not overlaps and not any(d is None or start <= d <= end for d in session_dates):
                continue
            before = len(pending)
            if (a['instituicao_id'] != institution or a['vinculo_instituicao_id'] != institution
                    or a['contexto_id'] is None or a['vinculo_id'] is None
                    or not _positive(a['modulo_id'])
                    or a['objetivo_pts_id'] != a['pts_id']
                    or a['paciente_id'] != a['contexto_paciente_id']
                    or a['paciente_id'] != a['vinculo_paciente_id']):
                issue('ANCESTRALIDADE_INCONSISTENTE', agenda)
            intervals = []
            for prefix in ('agenda', 'pts', 'contexto', 'vinculo'):
                begin, finish = _date(a[prefix + '_inicio']), _date(a[prefix + '_fim'])
                if begin is None or (a[prefix + '_fim'] is not None and finish is None):
                    issue('VIGENCIA_INCOMPLETA', agenda, incomplete=True)
                elif finish is not None and finish < begin:
                    issue('VIGENCIA_INVALIDA', agenda)
                else:
                    intervals.append((begin, finish))
            for key in ('quantidade_sessoes', 'duracao_minutos', 'frequencia_semanal', 'ocupacao_id'):
                if not _positive(a[key]):
                    issue('PLANEJAMENTO_QUANTITATIVO_INVALIDO', agenda, incomplete=a[key] is None)
            if len(pending) != before:
                continue
            if not a['contexto_ativo'] or not a['vinculo_ativo']:
                # Current inactive scope is not eligible; do not invent history.
                continue
            sessions = [r for r in records if r['sessao_id'] is not None]
            occurrences = []
            estimate_counts = {}
            if sessions:
                ids = [s['sessao_id'] for s in sessions]
                numbers = [s['numero_sessao'] for s in sessions]
                if len(ids) != len(set(ids)):
                    issue('OCORRENCIA_MULTIPLICADA', agenda)
                if (len(sessions) != a['quantidade_sessoes'] or any(not _positive(n) for n in numbers)
                        or sorted(numbers) != list(range(1, a['quantidade_sessoes'] + 1))):
                    issue('CRONOGRAMA_INCOMPLETO_OU_CONTRADITORIO', agenda,
                          incomplete=len(sessions) < a['quantidade_sessoes'])
                by_id = {s['sessao_id']: s for s in sessions}
                origins = defaultdict(list)
                for s in sessions:
                    sid, day = s['sessao_id'], _date(s['data_agendada'])
                    if (s['sessao_paciente_id'] != a['paciente_id']
                            or s['sessao_profissional_id'] != a['profissional_id']):
                        issue('SESSAO_ANCESTRALIDADE_INCONSISTENTE', agenda, sid)
                    if s['sessao_estado'] not in STATES:
                        issue('ESTADO_DESCONHECIDO', agenda, sid)
                    if day is None or s['sessao_duracao'] != a['duracao_minutos']:
                        issue('DATA_OU_DURACAO_INCONSISTENTE', agenda, sid)
                    times = s['hora_inicio'], s['hora_fim']
                    if any(t is not None for t in times):
                        left, right = map(_clock, times)
                        if left is None or right is None or right - left != a['duracao_minutos'] * 60:
                            issue('HORARIO_INCONSISTENTE', agenda, sid)
                    origin = s['sessao_origem_id']
                    if origin is not None:
                        origins[origin].append(sid)
                        old = by_id.get(origin)
                        # No inference about replacement outside this schedule or
                        # chains/cycles that the existing model cannot attest.
                        if (old is None or origin == sid or old['sessao_estado'] != 'REAGENDADA'
                                or old['sessao_origem_id'] is not None):
                            issue('SUBSTITUICAO_NAO_COMPROVADA', agenda, sid)
                    occurrences.append((day, s['sessao_estado'], sid))
                if any(len(children) > 1 for children in origins.values()):
                    issue('SUBSTITUICAO_AMBIGUA', agenda)
                if all(_positive(s['numero_sessao']) and _date(s['data_agendada']) is not None for s in sessions):
                    ordered_dates = [_date(s['data_agendada']) for s in sorted(sessions, key=lambda s: s['numero_sessao'])]
                    if ordered_dates != sorted(ordered_dates):
                        issue('SEQUENCIA_TEMPORAL_INCONSISTENTE', agenda)
            else:
                depends_on_estimate = True
                estimate_counts, error = self._estimate(a, intervals, start, end)
                if error:
                    issue(error, agenda)
                    continue
                occurrences = [(day, None, None) for day in estimate_counts]
            for day, state, sid in occurrences:
                if day is not None and not all(begin <= day and (finish is None or day <= finish)
                                               for begin, finish in intervals):
                    issue('OCORRENCIA_FORA_DA_VIGENCIA', agenda, sid)
            if len(pending) != before:
                continue
            monthly = [(d, st, sid) for d, st, sid in occurrences if start <= d <= end]
            # A duplicate suspicion is not automatic deduplication: block both.
            # Objective IDs intentionally excluded: duplicate objectives must not
            # silently legitimize two otherwise identical plans.
            signature = (a['contexto_id'], a['paciente_id'], a['modulo_id'], a['atividade_id'],
                         a['ocupacao_id'], a['profissional_id'], a['duracao_minutos'])
            # Different explicit time slots are distinct occurrences even when
            # two plans share a date. Missing times cannot prove this distinction.
            by_session = {s['sessao_id']: s for s in sessions}
            slots = set()
            for d, st, sid in monthly:
                if st not in EXCLUDED:
                    s = by_session.get(sid)
                    slots.add((d, _clock(s['hora_inicio']) if s else None,
                               _clock(s['hora_fim']) if s else None))
            for d, begin, finish in slots:
                signatures[signature + (d,)].append((agenda, begin, finish))
            accepted.append((agenda, a['duracao_minutos'], monthly, estimate_counts))

        duplicates = set()
        for plans in signatures.values():
            for index, (agenda, begin, finish) in enumerate(plans):
                for other, other_begin, other_finish in plans[index + 1:]:
                    if agenda != other and (begin is None or other_begin is None
                                            or (begin < other_finish and other_begin < finish)):
                        duplicates.update((agenda, other))
        for agenda in sorted(duplicates):
            issue('POSSIVEL_DUPLICIDADE_SEMANTICA', agenda)
        for agenda, minutes, occurrences, estimate_counts in accepted:
            if agenda in duplicates:
                continue
            for day, state, sid in occurrences:
                if state is None:
                    estimated += minutes * estimate_counts[day]
                    estimated_count += estimate_counts[day]
                else:
                    status[state]['quantidade'] += 1
                    status[state]['minutos'] += minutes
                    if state not in EXCLUDED:
                        persisted += minutes
        quality = ('INCONSISTENTE' if any(p['qualidade'] == 'INCONSISTENTE' for p in pending)
                   else 'INCOMPLETO' if pending else 'ESTIMADO' if depends_on_estimate else 'CONCLUSIVO')
        return dict(instituicao_id=institution, ocupacao_id=occupation,
                    mes_referencia=start.strftime('%Y-%m'), data_inicio=start.isoformat(), data_fim=end.isoformat(),
                    minutos_vigentes_persistidos=persisted, minutos_vigentes_estimados=estimated,
                    total_minutos_vigentes_projetados=None if pending else persisted + estimated,
                    por_status=status, quantidade_ocorrencias_estimadas=estimated_count,
                    qualidade=quality, conclusivo=quality == 'CONCLUSIVO',
                    subtotais_parciais=bool(pending), pendencias=pending,
                    base_historica='ESTADO_ATUAL_SEM_RECONSTRUCAO_HISTORICA')

    @staticmethod
    def _estimate(a, intervals, start, end):
        """Stream the existing engine's float recurrence, without allocating N
        sessions. Store at most 31 daily counts. Validate the entire proposal
        before publishing any count. Runtime is linear in the declared quantity;
        elapsed time never changes the result or imposes a quantity ceiling.
        """
        counts = defaultdict(int)
        try:
            step = 7 / a['frequencia_semanal']
            if not math.isfinite(step) or step <= 0:
                return {}, 'ESTIMATIVA_PRECISAO_NUMERICA_INSUFICIENTE'
            accumulated = 0.0
            beginning = _date(a['agenda_inicio'])
            # Preflight guaranteed minimum offset: every positive addition is
            # nonnegative. The second occurrence already outside dates needs no
            # materialization. Later limits are checked before constructing dates.
            available = (date.max - beginning).days
            for index in range(a['quantidade_sessoes']):
                if index:
                    previous = accumulated
                    accumulated += step
                    if accumulated == previous:
                        return {}, 'ESTIMATIVA_PRECISAO_NUMERICA_INSUFICIENTE'
                offset = math.floor(accumulated)
                if offset > available:
                    return {}, 'ESTIMATIVA_LIMITE_DE_DATAS'
                day = beginning + timedelta(days=offset)
                if not all(left <= day and (right is None or day <= right) for left, right in intervals):
                    return {}, 'OCORRENCIA_FORA_DA_VIGENCIA'
                if start <= day <= end:
                    counts[day] += 1
        except (OverflowError, ValueError, ZeroDivisionError):
            return {}, 'ESTIMATIVA_DADOS_NAO_REPRESENTAVEIS'
        return dict(counts), None
