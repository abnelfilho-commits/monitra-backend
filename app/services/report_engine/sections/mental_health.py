"""Factual formatting of canonical DTOs and official readings, without scoring."""
from app.services.checkin_contract import FIELDS
from ..models import ReportSection, ReportComponent
from .base_section import BaseSectionBuilder


def section(code, title, order, paragraphs):
    result = ReportSection(code, title, order)
    for i, paragraph in enumerate(paragraphs or ['Sem registros elegíveis no período.']):
        result.add_component(ReportComponent('PLAIN_TEXT', paragraph, order=i))
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
        return section(self.code, 'Período analisado', 1, [
            f'{date_text(c.period_start)} a {date_text(c.period_end)}, inclusive; timestamps considerados em UTC.',
            'A síntese oficial utiliza somente as evidências selecionadas neste período. Não reconstrói um prontuário histórico imutável.',
            'PTS e planejamentos: sobreposição com o período; status, objetivos e dados cadastrais são os atuais, sem reconstrução histórica. Sessões usam data de realização quando existente; caso contrário, data agendada.'])


class Summary(BaseSectionBuilder):
    code = 'MENTAL_SUMMARY'
    def build(self, c):
        return section(self.code, 'Síntese assistencial', 2, [c.clinical_reading.summary or 'Síntese indisponível.'])


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
        return section(self.code, 'Bem-estar longitudinal', 3, paragraphs)


class Assessments(BaseSectionBuilder):
    code = 'MENTAL_ASSESSMENTS'
    def build(self, c):
        paragraphs = []
        for group in data(c)['assessments'].values():
            for application in group['applications']:
                r = application['result']
                paragraphs.append(f"{r.get('instrumento_label', application['instrument'])} — {application['recorded_at']}; aplicação #{application['application_id']}; versão {r.get('versao', 'não informada')}.")
                if r.get('score') is not None:
                    paragraphs.append(f"Resultado oficial: {r['score']}. Classificação do instrumento: {r.get('classificacao', 'não informada')}.")
                for domain in r.get('dominios', []):
                    paragraphs.append(f"{domain.get('nome', domain.get('label', domain['codigo']))}: {domain['score']}/100.")
                if r.get('interpretacao'): paragraphs.append(r['interpretacao'])
                paragraphs.extend(r.get('alertas', []))
        return section(self.code, 'Instrumentos de rastreamento', 4, paragraphs)


class Diagnoses(BaseSectionBuilder):
    code = 'MENTAL_DIAGNOSES'
    def build(self, c):
        return section(self.code, 'Diagnósticos', 5, [
            f'{date_text(r.data_diagnostico)} — #{r.id}; {r.tipo}; {r.status}; CID: {r.cid or "Não informado"}. {r.descricao_clinica}. Profissional informado: {r.medico_nome}.'
            for r in data(c)['diagnoses']])


class Interventions(BaseSectionBuilder):
    code = 'MENTAL_INTERVENTIONS'
    def build(self, c):
        return section(self.code, 'Intervenções', 6, [
            f'{date_text(r.data_intervencao)} — #{r.id}; {r.tipo}. {r.descricao or ""}' for r in data(c)['interventions']])


class Plans(BaseSectionBuilder):
    code = 'MENTAL_PLANS'
    def build(self, c):
        paragraphs = []
        for r in data(c)['plans']:
            paragraphs.append(f'PTS #{r.id}: {r.objetivo_geral or "Não informado"}. {date_text(r.data_inicio)} a {date_text(r.data_fim)}; status atual: {r.status}.')
            for o in r.objetivos: paragraphs.append(f'Objetivo #{o.id}: {o.descricao}. Status atual: {o.status}.')
        for r in data(c)['planning']:
            paragraphs.append(f'Planejamento #{r.id}, PTS #{r.pts_id}, objetivo #{r.objetivo_id}: {r.atividade_nome}; {r.ocupacao_nome}; {r.profissional_nome}. '
                f'{date_text(r.data_inicio)} a {date_text(r.data_fim)}; {r.frequencia_semanal}/semana; {r.duracao_minutos} minutos; {r.quantidade_sessoes} sessões previstas no planejamento integral. Status atual: {r.status}.')
        return section(self.code, 'PTS e planejamento assistencial', 7, paragraphs)


class Sessions(BaseSectionBuilder):
    code = 'MENTAL_SESSIONS'
    def build(self, c):
        paragraphs = []
        for r in data(c)['sessions']:
            paragraphs.append(f'Sessão #{r.id}, agenda #{r.agenda_cuidado_id}: {r.status}. Agendada: {date_text(r.data_agendada)}; realizada: {date_text(r.data_realizacao)}. Profissional: {r.profissional_nome or "Não informado"}.')
            if r.narrativa: paragraphs.append('Registro de atendimento: ' + r.narrativa)
        return section(self.code, 'Sessões e acompanhamento', 8, paragraphs)


class Narrative(BaseSectionBuilder):
    code = 'MENTAL_NARRATIVE'
    def build(self, c):
        d = data(c)
        events = [(r.data_hora.isoformat()[:10], f'Check-in de Bem-Estar #{r.id}') for r in d['checkins']]
        events += [(r.data_diagnostico.isoformat(), f'{r.tipo} #{r.id}: {r.descricao_clinica}') for r in d['diagnoses']]
        events += [(r.data_intervencao.isoformat()[:10], f'Intervenção #{r.id}: {r.tipo}') for r in d['interventions']]
        events += [(r['recorded_at'][:10], f"{r['instrument']} — aplicação #{r['application_id']}") for g in d['assessments'].values() for r in g['applications']]
        events += [((r.data_realizacao or r.data_agendada).isoformat(), f'Sessão #{r.id}: {r.status}') for r in d['sessions']]
        return section(self.code, 'Narrativa longitudinal factual', 9, [f'{day}: {text}.' for day, text in sorted(events)])


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
