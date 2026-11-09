"""Factual formatting of canonical DTOs and official readings, without scoring."""
from app.services.checkin_contract import FIELDS
from ..models import ReportSection, ReportComponent
from .base_section import BaseSectionBuilder


def section(code, title, order, paragraphs):
    result = ReportSection(code, title, order)
    for i, paragraph in enumerate(paragraphs or ['Sem registros elegíveis no período.']):
        result.add_component(ReportComponent('MENTAL_TEXT', {
            'paragraphs': [paragraph], 'compact': code == 'MENTAL_PROVENANCE',
        }, order=i))
    return result


def record(result, title, fields=(), paragraphs=(), metrics=()):
    result.add_component(ReportComponent('MENTAL_RECORD', {
        'heading': title, 'fields': list(fields), 'paragraphs': list(paragraphs),
        'metrics': list(metrics),
    }, order=len(result.components)))


def empty(result):
    if not result.components:
        record(result, 'Sem registros elegíveis no período.')
    return result


def data(c):
    return c.collected_data['MENTAL_HEALTH_PROVIDER']


def date_text(value):
    return value.strftime('%d/%m/%Y') if value else 'Não informado'


class Identification(BaseSectionBuilder):
    code = 'MENTAL_IDENTIFICATION'
    def build(self, c):
        s = c.subject
        return section(self.code, 'Identificação e contexto assistencial', 0, [
            f"Pessoa: {s['name']} (#{s['pessoa_id']}). Instituição: {s['instituicao']} (#{s['instituicao_id']}).",
            f"Contexto Assistencial #{s['contexto_assistencial_id']}. Linha: Saúde Mental."])


class Period(BaseSectionBuilder):
    code = 'MENTAL_PERIOD'
    def build(self, c):
        return section(self.code, 'Escopo temporal e limitações', 9, [
            f'{date_text(c.period_start)} a {date_text(c.period_end)}, inclusive; timestamps considerados em UTC.',
            'A síntese oficial utiliza somente as evidências selecionadas neste período. Não reconstrói um prontuário histórico imutável.',
            'PTS e planejamentos: sobreposição com o período; status, objetivos e dados cadastrais são os atuais, sem reconstrução histórica. Sessões usam data de realização quando existente; caso contrário, data agendada.'])


class Summary(BaseSectionBuilder):
    code = 'MENTAL_SUMMARY'
    def build(self, c):
        d = data(c)
        result = section(self.code, 'Resumo Executivo', 1,
                         [c.clinical_reading.summary or 'Síntese indisponível.'])
        latest = max((r.data_hora for r in d['checkins']), default=None)
        record(result, 'Situação Atual', [
            ('Referência da leitura oficial', date_text(getattr(c.clinical_reading, 'reference_date', None))),
            ('Último check-in no período', date_text(latest)),
            ('Status atuais dos PTS selecionados', ', '.join(sorted({r.status for r in d['plans']})) or 'Sem PTS no recorte'),
        ])
        result.add_component(ReportComponent('MENTAL_METRICS', {
            'heading': 'Indicadores da Jornada',
            'metrics': [('Check-ins', len(d['checkins'])),
                        ('Aplicações', sum(len(g['applications']) for g in d['assessments'].values())),
                        ('Objetivos PTS', sum(len(r.objetivos) for r in d['plans'])),
                        ('Planejamentos', len(d['planning'])),
                        ('Sessões', len(d['sessions']))],
            'paragraphs': ['Contagens dos registros selecionados; não representam escores clínicos.'],
        }, order=len(result.components)))
        return result


class Wellbeing(BaseSectionBuilder):
    code = 'MENTAL_WELLBEING'
    def build(self, c):
        paragraphs = []
        for r in data(c)['checkins']:
            paragraphs.append(f'Check-in #{r.id} — {date_text(r.data_hora)}. ' + ('Baseline inicial.' if r.baseline else 'Acompanhamento.'))
            for key, label, options in FIELDS:
                if key in r.respostas:
                    label = 'Solicitação de apoio autorreferida' if key == 'pedido_ajuda' else label
                    paragraphs.append(f'{label}: {dict(options).get(r.respostas[key], r.respostas[key])}')
        return section(self.code, 'Check-ins detalhados de bem-estar', 8, paragraphs)


class Assessments(BaseSectionBuilder):
    code = 'MENTAL_ASSESSMENTS'
    def build(self, c):
        result = ReportSection(self.code, 'Instrumentos de rastreamento', 2)
        for group in data(c)['assessments'].values():
            for application in group['applications']:
                r = application['result']
                metrics = []
                if r.get('score') is not None:
                    metrics.append(('Resultado oficial', r['score']))
                metrics.extend((domain.get('nome', domain.get('label', domain['codigo'])),
                                f"{domain['score']}/100") for domain in r.get('dominios', []))
                fields = [('Data/hora registrada', application['recorded_at']),
                          ('Aplicação', f"#{application['application_id']}"),
                          ('Versão', r.get('versao', 'não informada'))]
                if r.get('score') is not None:
                    fields.append(('Classificação do instrumento', r.get('classificacao', 'não informada')))
                paragraphs = ([r['interpretacao']] if r.get('interpretacao') else []) + r.get('alertas', [])
                record(result, r.get('instrumento_label', application['instrument']), fields, paragraphs, metrics)
        return empty(result)


class Diagnoses(BaseSectionBuilder):
    code = 'MENTAL_DIAGNOSES'
    def build(self, c):
        result = ReportSection(self.code, 'Diagnósticos', 3)
        for r in data(c)['diagnoses']:
            record(result, f'Diagnóstico #{r.id}', [
                ('Data', date_text(r.data_diagnostico)), ('Tipo', r.tipo), ('Status', r.status),
                ('CID', r.cid or 'Não informado'), ('Profissional informado', r.medico_nome),
            ], [r.descricao_clinica])
        return empty(result)


class Interventions(BaseSectionBuilder):
    code = 'MENTAL_INTERVENTIONS'
    def build(self, c):
        result = ReportSection(self.code, 'Intervenções', 4)
        for r in data(c)['interventions']:
            record(result, f'Intervenção #{r.id}', [('Data', date_text(r.data_intervencao)),
                   ('Tipo', r.tipo)], [r.descricao or ''])
        return empty(result)


class Plans(BaseSectionBuilder):
    code = 'MENTAL_PLANS'
    def build(self, c):
        result = ReportSection(self.code, 'PTS e planejamento assistencial', 5)
        for r in data(c)['plans']:
            record(result, f'PTS #{r.id}', [('Objetivo geral', r.objetivo_geral or 'Não informado'),
                ('Início', date_text(r.data_inicio)), ('Término', date_text(r.data_fim)),
                ('Status atual', r.status)] + [(f'Objetivo #{o.id} - {o.status}', o.descricao) for o in r.objetivos])
        for r in data(c)['planning']:
            record(result, f'Planejamento #{r.id}', [
                ('PTS / Objetivo', f'#{r.pts_id} / #{r.objetivo_id}'), ('Atividade', r.atividade_nome),
                ('Ocupação', r.ocupacao_nome), ('Profissional', r.profissional_nome),
                ('Início', date_text(r.data_inicio)), ('Término', date_text(r.data_fim)),
                ('Frequência semanal', f'{r.frequencia_semanal}/semana'),
                ('Duração', f'{r.duracao_minutos} minutos'),
                ('Sessões previstas no planejamento integral', r.quantidade_sessoes), ('Status atual', r.status)])
        return empty(result)


class Sessions(BaseSectionBuilder):
    code = 'MENTAL_SESSIONS'
    def build(self, c):
        result = ReportSection(self.code, 'Sessões e acompanhamento', 6)
        for r in data(c)['sessions']:
            record(result, f'Sessão #{r.id}', [('Agenda', f'#{r.agenda_cuidado_id}'), ('Status', r.status),
                ('Agendada', date_text(r.data_agendada)), ('Realizada', date_text(r.data_realizacao)),
                ('Profissional', r.profissional_nome or 'Não informado')],
                ['Registro de atendimento: ' + r.narrativa] if r.narrativa else [])
        return empty(result)


class Narrative(BaseSectionBuilder):
    code = 'MENTAL_NARRATIVE'
    def build(self, c):
        d = data(c)
        events = [(r.data_hora.isoformat()[:10], f'Check-in de Bem-Estar #{r.id}') for r in d['checkins']]
        events += [(r.data_diagnostico.isoformat(), f'{r.tipo} #{r.id}: {r.descricao_clinica}') for r in d['diagnoses']]
        events += [(r.data_intervencao.isoformat()[:10], f'Intervenção #{r.id}: {r.tipo}') for r in d['interventions']]
        events += [(r['recorded_at'][:10], f"{r['instrument']} — aplicação #{r['application_id']}") for g in d['assessments'].values() for r in g['applications']]
        events += [((r.data_realizacao or r.data_agendada).isoformat(), f'Sessão #{r.id}: {r.status}') for r in d['sessions']]
        return section(self.code, 'Narrativa longitudinal factual', 7, [f'{day}: {text}.' for day, text in sorted(events)])


class Considerations(BaseSectionBuilder):
    code = 'MENTAL_CONSIDERATIONS'
    def build(self, c):
        return section(self.code, 'Considerações assistenciais', 10, [
            'Check-ins são descritivos. Instrumentos de rastreamento não constituem diagnóstico. Ausência de registros não significa ausência de sintomas.',
            'Solicitação de apoio autorreferida descreve a resposta da Pessoa; não estabelece risco, urgência, encaminhamento ou atendimento solicitado. Nenhuma recomendação adicional é produzida por este relatório.'])


class Provenance(BaseSectionBuilder):
    code = 'MENTAL_PROVENANCE'
    def build(self, c):
        d = data(c)
        paragraphs = []
        for r in d['checkins']:
            recorder = (f'Pessoa respondente #{r.respondente_pessoa_id}' if r.modalidade == 'AUTORRELATO' else
                        f'Profissional #{r.registrador_profissional_id}')
            paragraphs.append(f'Check-in #{r.id}: canal {r.canal}; modalidade {r.modalidade}; respondente Pessoa #{r.respondente_pessoa_id}; registrador: {recorder}.')
        for key in ('diagnoses', 'interventions'):
            for r in d[key]:
                paragraphs.append(f'{"Diagnóstico" if key == "diagnoses" else "Intervenção"} #{r.id}: usuário registrador #{r.registrador_usuario_id}; profissional #{r.registrador_profissional_id}.')
        for group in d['assessments'].values():
            for r in group['applications']:
                paragraphs.append(f"{r['instrument']} #{r['application_id']}: registro #{r['record_id']}; usuário #{r['author']['usuario_id']}; profissional #{r['author']['profissional_id']}.")
        for r in d['sessions']:
            if r.autor_usuario_id is not None: paragraphs.append(f'Sessão #{r.id}: autor usuário #{r.autor_usuario_id}; {r.autor_nome or "nome não informado"}.')
        return section(self.code, 'Proveniência', 11, paragraphs)


MENTAL_SECTIONS = [Identification, Period, Summary, Wellbeing, Assessments, Diagnoses,
                   Interventions, Plans, Sessions, Narrative, Considerations, Provenance]
