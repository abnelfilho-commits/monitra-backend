"""C2-M2 internal read-only capacity, using current C1 records (not history).

Amounts are monthly MINUTES formatted as decimal strings. Exact integer
numerators are retained; individual declarations are never rounded.
"""
import calendar
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext, ROUND_HALF_UP

from sqlalchemy import text


SOURCE = text('''
WITH eligible AS (
    SELECT v.id AS vinculo_id, v.instituicao_id, v.profissional_id, v.ocupacao_id,
           v.data_inicio AS vinculo_inicio, v.data_fim AS vinculo_fim
    FROM profissional_instituicoes v
    JOIN profissionais p ON p.id=v.profissional_id AND p.ativo IS TRUE
    WHERE v.instituicao_id=:institution AND v.ativo IS TRUE
      AND (CAST(:occupation AS integer) IS NULL OR v.ocupacao_id=:occupation)
      AND ((v.data_inicio<=:last AND (v.data_fim IS NULL OR v.data_fim>=:first))
           OR v.data_inicio IS NULL OR v.data_fim<v.data_inicio)
)
SELECT i.ativo AS instituicao_ativa, e.*, o.nome AS ocupacao_nome,
       o.ativo AS ocupacao_ativa, c.id AS capacidade_id,
       c.data_inicio AS capacidade_inicio, c.data_fim AS capacidade_fim,
       c.minutos_semanais
FROM instituicoes i
LEFT JOIN eligible e ON e.instituicao_id=i.id
LEFT JOIN ocupacoes_profissionais o ON o.id=e.ocupacao_id
LEFT JOIN capacidades_profissionais c ON c.profissional_instituicao_id=e.vinculo_id
    AND c.ativo IS TRUE
    AND ((c.data_inicio<=:last AND (c.data_fim IS NULL OR c.data_fim>=:first))
         OR c.data_inicio IS NULL OR c.data_fim<c.data_inicio)
WHERE i.id=:institution
ORDER BY e.ocupacao_id, e.vinculo_id, c.data_inicio, c.id
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


def _amount(numerator):
    # Precision accommodates the whole integer part plus ample division digits;
    # only this presentation conversion rounds. Summation uses exact integers.
    with localcontext() as ctx:
        ctx.prec = max(28, len(str(abs(numerator))) + 20)
        return str((Decimal(numerator) / Decimal(7)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class CapacidadeMensalService:
    def calculate(self, db, *, instituicao_id, mes_referencia, actor_id, ocupacao_id=None):
        """actor_id is mandatory security context, revalidated by the C1 gate.

        Does not grant clinical access or own commit/rollback. No autoflush.
        """
        from app.services.institucional import InstitucionalService, InstitucionalErro
        first, last = self._period(instituicao_id, mes_referencia, ocupacao_id)
        with db.no_autoflush:
            InstitucionalService._admin(db, actor_id)
            rows = db.execute(SOURCE, dict(institution=instituicao_id, occupation=ocupacao_id,
                                           first=first, last=last)).mappings().all()
        if not rows:
            raise InstitucionalErro('CAPACITY_INSTITUTION_NOT_FOUND')
        if not rows[0]['instituicao_ativa']:
            raise InstitucionalErro('CAPACITY_INSTITUTION_INACTIVE')
        return self._aggregate(rows, instituicao_id, ocupacao_id, first, last)

    @staticmethod
    def _period(institution, month, occupation):
        if not _positive(institution) or (occupation is not None and not _positive(occupation)):
            raise ValueError('Identificadores devem ser inteiros positivos.')
        if not isinstance(month, str) or re.fullmatch(r'[0-9]{4}-[0-9]{2}', month) is None:
            raise ValueError('mes_referencia deve usar AAAA-MM.')
        year, number = map(int, month.split('-'))
        return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])

    @staticmethod
    def _aggregate(rows, institution, occupation, first, last):
        groups = defaultdict(list)
        for row in rows:
            if row['vinculo_id'] is not None:
                groups[row['vinculo_id']].append(row)
        details = []
        for link_id in sorted(groups):
            records = groups[link_id]
            row = records[0]
            problems = []
            def issue(code, capacity=None, **extra):
                problems.append(dict(codigo=code, vinculo_id=link_id, capacidade_id=capacity, **extra))
            if (row['instituicao_id'] != institution or not _positive(row['profissional_id'])
                    or not _positive(row['ocupacao_id']) or not row['ocupacao_nome']
                    or (occupation is not None and row['ocupacao_id'] != occupation)):
                issue('IDENTIDADE_INCONSISTENTE')
            begin, end = _date(row['vinculo_inicio']), _date(row['vinculo_fim'])
            if begin is None or (row['vinculo_fim'] is not None and end is None) or (end and end < begin):
                issue('VIGENCIA_VINCULO_INVALIDA')
            left, right = max(first, begin or first), min(last, end or last)
            if left > right:
                issue('VINCULO_FORA_DO_RECORTE')
            # Unlocatable errors invalidate this link's whole eligible window.
            # Local errors only mask their own days (at most 31 per month).
            uncertain_window = bool(problems)
            seen, intervals = set(), []
            for record in records:
                if any(record[key] != row[key] for key in ('instituicao_id', 'profissional_id', 'ocupacao_id',
                                                            'vinculo_inicio', 'vinculo_fim')):
                    issue('IDENTIDADE_INCONSISTENTE')
                    uncertain_window = True
                cid = record['capacidade_id']
                if cid is None:
                    continue
                start, finish = _date(record['capacidade_inicio']), _date(record['capacidade_fim'])
                if (start is None or (record['capacidade_fim'] is not None and finish is None)
                        or (finish is not None and finish < start)):
                    issue('DECLARACAO_INCONSISTENTE', cid, relevancia_temporal='INDETERMINADA')
                    uncertain_window = True
                    continue
                clipped_start, clipped_end = max(left, start), min(right, finish or right)
                if clipped_start > clipped_end:
                    continue
                bounds = dict(data_inicio=clipped_start.isoformat(), data_fim=clipped_end.isoformat())
                minutes = record['minutos_semanais']
                if cid in seen:
                    issue('DECLARACAO_DUPLICADA', cid, **bounds)
                    minutes = None
                seen.add(cid)
                if not _positive(record['minutos_semanais']):
                    issue('DECLARACAO_INCONSISTENTE', cid, **bounds)
                    minutes = None
                intervals.append((clipped_start, clipped_end, cid, minutes))
            numerator = 0
            gaps = []
            if not uncertain_window:
                days = {ordinal: [] for ordinal in range(left.toordinal(), right.toordinal()+1)}
                for start, finish, cid, minutes in intervals:
                    for ordinal in range(start.toordinal(), finish.toordinal()+1):
                        days[ordinal].append((cid, minutes))
                for ordinal, declarations in days.items():
                    day = date.fromordinal(ordinal)
                    if not declarations:
                        if gaps and gaps[-1][1].toordinal()+1 == ordinal:
                            gaps[-1] = (gaps[-1][0], day)
                        else:
                            gaps.append((day, day))
                    elif len(declarations) > 1:
                        issue('DECLARACOES_SOBREPOSTAS', data_inicio=day.isoformat(), data_fim=day.isoformat(),
                              capacidades_ids=sorted({cid for cid, _ in declarations}))
                    elif declarations[0][1] is not None:
                        numerator += declarations[0][1]
                for start, finish in gaps:
                    issue('DIAS_SEM_DECLARACAO', data_inicio=start.isoformat(), data_fim=finish.isoformat(),
                          dias=(finish-start).days+1)
            quality = ('INCONSISTENTE' if any(p['codigo'] != 'DIAS_SEM_DECLARACAO' for p in problems)
                       else 'INCOMPLETO' if gaps else 'CONCLUSIVO')
            details.append(dict(vinculo_id=link_id, profissional_id=row['profissional_id'],
                ocupacao_id=row['ocupacao_id'], ocupacao_nome=row['ocupacao_nome'],
                ocupacao_ativa=bool(row['ocupacao_ativa']), numerador=numerator,
                dias_elegiveis=max(0, (right-left).days+1),
                dias_sem_declaracao=None if quality == 'INCONSISTENTE' else sum((b-a).days+1 for a,b in gaps),
                capacidade_informada=bool(intervals) and quality != 'INCONSISTENTE',
                qualidade=quality, pendencias=problems))

        def totals(items):
            numerator = sum(item['numerador'] for item in items)
            quality = ('INCONSISTENTE' if any(i['qualidade']=='INCONSISTENTE' for i in items)
                       else 'INCOMPLETO' if any(i['qualidade']=='INCOMPLETO' for i in items) else 'CONCLUSIVO')
            return dict(numerador=numerator, denominador=7, unidade='MINUTOS_MENSAIS',
                capacidade_mensal_conhecida=_amount(numerator),
                capacidade_mensal_total=_amount(numerator) if quality=='CONCLUSIVO' else None,
                vinculos=len(items), profissionais_distintos=len({i['profissional_id'] for i in items}),
                vinculos_com_capacidade=sum(i['capacidade_informada'] for i in items),
                vinculos_sem_capacidade=sum(not i['capacidade_informada'] and i['qualidade']!='INCONSISTENTE' for i in items),
                vinculos_inconsistentes=sum(i['qualidade']=='INCONSISTENTE' for i in items),
                vinculos_com_lacunas=sum(i['qualidade']=='INCOMPLETO' for i in items),
                qualidade=quality, conclusivo=quality=='CONCLUSIVO')
        occupations = defaultdict(list)
        for item in details:
            occupations[item['ocupacao_id']].append(item)
        return dict(instituicao_id=institution, mes_referencia=f'{first.year:04d}-{first.month:02d}',
            ocupacao_id=occupation, data_inicio=first.isoformat(), data_fim=last.isoformat(),
            **totals(details), ocupacoes=[dict(ocupacao_id=oid, ocupacao_nome=items[0]['ocupacao_nome'],
                ocupacao_ativa=items[0]['ocupacao_ativa'], **totals(items))
                for oid, items in sorted(occupations.items(), key=lambda pair: (pair[0] is None, pair[0]))],
            detalhes_vinculos=details, pendencias=[p for i in details for p in i['pendencias']],
            base_historica='ESTADO_CADASTRAL_ATUAL_SEM_RECONSTRUCAO')
