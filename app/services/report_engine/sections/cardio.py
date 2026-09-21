from ..presentation import format_date_pt_br
"""Cardio composition: factual presentation, no clinical rules or scoring."""
from ..sections.base_section import BaseSectionBuilder
from ..models import ReportSection, ReportComponent


def shown(value):
    return 'Indisponível' if value is None or value == '' else str(value)


def section(code, title, order, paragraphs):
    result = ReportSection(code,title,order)
    for i,paragraph in enumerate(paragraphs):
        result.add_component(ReportComponent('PLAIN_TEXT',paragraph,order=i))
    return result


def event_text(e):
    basis = 'Data clínica' if e['date_basis']=='CLINICAL_DATE' else 'Data de criação (sem data clínica)'
    actor=e.get('actor') or {}
    author=actor.get('name') or (str(actor.get('namespace'))+' #'+str(actor.get('id')) if actor else 'Não informado')
    return f"{basis}: {format_date_pt_br(e['data'])}. {e['descricao']}. Origem: {shown(e['origem'])}. Autoria: {author}."


class CardioSummary(BaseSectionBuilder):
    code='EXECUTIVE_SUMMARY'
    def build(self,c):
        return section(self.code,'Resumo executivo',2,[c.clinical_reading.summary or 'Leitura clínica atual indisponível.',
            f"Eventos no período: {len(c.collected_data['TIMELINE_PROVIDER'])}. A presença de eventos não constitui classificação de risco ou continuidade."])


class CardioStatus(BaseSectionBuilder):
    code='CURRENT_STATUS'
    def build(self,c):
        r=c.clinical_reading
        return section(self.code,'Situação atual',3,[f'Leitura clínica atual - referência: {format_date_pt_br(r.reference_date)}.',
            f'Risco Cardio: {shown(r.risk)}. Tendência: {shown(r.trend)}.',
            f"Score Cardio: {shown(r.metadata.get('score'))}. Protocolo Cardio: {shown(r.metadata.get('protocol'))}."])


class CardioDiagnoses(BaseSectionBuilder):
    code='DIAGNOSES'
    def build(self,c):
        rows=c.collected_data['DIAGNOSIS_PROVIDER']['historico']
        return section(self.code,'Diagnósticos Cardio',4,[
            ('Ativo atualmente, anterior ao período' if d['temporal_scope']=='ACTIVE_BEFORE_PERIOD' else 'Registrado no período')+
            f". Data clínica: {format_date_pt_br(d['data_diagnostico'])}. CID: {shown(d.get('cid'))}. {d['descricao_clinica']}. Status atual: {d['status']}."
            for d in rows] or ['Nenhum diagnóstico elegível para este contexto.'])


class CardioRecords(BaseSectionBuilder):
    code='LONGITUDINAL_RECORDS'
    def build(self,c):
        rows=[e for e in c.collected_data['TIMELINE_PROVIDER'] if e['tipo_evento']=='DAILY_RECORD']
        paragraphs=[]
        for e in rows:
            paragraphs.append(event_text(e))
            for answer in e['metadata'].get('answers',[]):
                paragraphs.append(answer['name']+': '+', '.join(shown(v) for v in answer['values'].values()))
            note=e['metadata'].get('observacoes')
            if note: paragraphs.append('Observações complementares: '+note)
        return section(self.code,'Acompanhamento longitudinal',5,paragraphs or ['Sem Registro Diário no período.'])


class CardioInterventions(BaseSectionBuilder):
    code='INTERVENTIONS'
    def build(self,c):
        return section(self.code,'Intervenções',6,[event_text(e) for e in c.collected_data['TIMELINE_PROVIDER']
            if e['tipo_evento']=='INTERVENTION'] or ['Sem intervenções no período.'])


class CardioEvolution(BaseSectionBuilder):
    code='EVOLUTION'
    def build(self,c):
        return section(self.code,'Evolução cardiometabólica',7,[
            f"Data clínica: {format_date_pt_br(r['data'])}. Glicemia em jejum: {shown(r['glicemia_jejum'])}; pressão sistólica: {shown(r['pressao_sistolica'])}; "
            f"diastólica: {shown(r['pressao_diastolica'])}; peso: {shown(r['peso'])}; IMC: {shown(r['imc'])}."
            for r in c.collected_data['EVOLUTION_PROVIDER']] or ['Sem medições no período.'])


class CardioInterpretation(BaseSectionBuilder):
    code='CLINICAL_INTERPRETATION'
    def build(self,c):
        return section(self.code,'Interpretação clínica Cardio atual',8,[c.clinical_reading.summary or 'Interpretação clínica indisponível.'])


class CardioNarrative(BaseSectionBuilder):
    code='LONGITUDINAL_NARRATIVE'
    def build(self,c):
        return section(self.code,'Narrativa longitudinal',9,[event_text(e) for e in reversed(c.collected_data['TIMELINE_PROVIDER'])]
                       or ['Nenhum evento elegível no período.'])


class CardioConsiderations(BaseSectionBuilder):
    code='CONSIDERATIONS'
    def build(self,c):
        return section(self.code,'Considerações',10,[
            'Este relatório apresenta registros e a leitura clínica atual produzida pelo engine Cardio. Não reconstrói uma avaliação clínica histórica.',
            'Não são geradas recomendações clínicas adicionais. Ausência de dados não representa baixo risco, normalidade ou estabilidade.',
            'IMC exige peso e altura da mesma observação e unidades explícitas; altura cadastral não é utilizada.'])
