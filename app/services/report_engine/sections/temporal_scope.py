from ..sections.base_section import BaseSectionBuilder
from ..models import ReportSection, ReportComponent


class TemporalScopeSection(BaseSectionBuilder):
    code = 'TEMPORAL_SCOPE'
    required = True

    def build(self, context):
        reading = context.clinical_reading
        reference = reading.reference_date.isoformat() if reading and reading.reference_date else 'indisponível'
        text = (f'Linha: {context.care_line.display_name}. Período dos eventos: {context.period_start} a {context.period_end}, inclusivo. '
            f'Leitura clínica atual: observação de referência {reference}. A leitura atual não representa uma avaliação histórica no encerramento do período. '
            'Contextos ativos anteriores são identificados separadamente. Quando não há data clínica, a data de criação é identificada como data técnica.')
        if 'PTS_PROVIDER' in context.collected_data:
            text += ' PTS e planejamentos são selecionados por sobreposição de suas datas com o período. Seus status e objetivos representam contexto atual, sem reconstrução histórica. Sessões e avaliações são restritas ao período; o status das sessões é o registrado atualmente.'
        section = ReportSection(self.code, 'Escopo temporal e Linha de Cuidado', 1)
        section.add_component(ReportComponent('PLAIN_TEXT',text))
        for diagnosis in context.collected_data.get('DIAGNOSIS_PROVIDER', {}).get('historico', []):
            if diagnosis['temporal_scope'] == 'ACTIVE_BEFORE_PERIOD':
                section.add_component(ReportComponent('PLAIN_TEXT',
                    f"Diagnóstico ativo atualmente, anterior ao período: {diagnosis['descricao_clinica']} (data clínica: {diagnosis['data_diagnostico']}). Não é evento novo do período."))
        return section
