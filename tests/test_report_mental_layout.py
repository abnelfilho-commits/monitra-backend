"""Synthetic visual fixtures; no patient data or database required."""
import os
import re
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace as NS
from pypdf import PdfReader
from app.services.report_engine.sections.mental_health import MENTAL_SECTIONS
from app.services.report_engine.models import CanonicalReport
from app.services.report_engine.renderers.pdf_renderer import PDFRenderer


def context(long=False):
    day = date(2026, 11, 9)
    narrative = ('Evolução sintética: atenção, vínculo, compreensão e comunicação. <texto> & conteúdo preservado. ' * (120 if long else 1))
    checkin = NS(id=1, data_hora=day, baseline=True, respostas={'pedido_ajuda': 'SIM'},
        modalidade='AUTORRELATO', canal='WHATSAPP', respondente_pessoa_id=5, registrador_profissional_id=None)
    assessments = {}
    for i, name in enumerate(['PHQ-9', 'GAD-7', 'CBI']):
        result = dict(instrumento_label=name, versao='1', interpretacao=f'Interpretação oficial sintética de {name}, sem recálculo.', alertas=['Alerta oficial sintético.'])
        if name == 'CBI':
            result['dominios'] = [dict(codigo='PESSOAL', nome='Burnout Pessoal', score=25),
                                  dict(codigo='TRABALHO', nome='Relacionado ao Trabalho', score=40),
                                  dict(codigo='CLIENTES', nome='Relacionado aos Clientes', score=50)]
        else:
            result.update(score=3, classificacao='Classificação oficial sintética')
        assessments[name] = {'applications':[dict(result=result,instrument=name,recorded_at='2026-11-09T12:00:00Z',application_id=i+1,record_id=i+10,author=dict(usuario_id=7,profissional_id=4))]}
    data = dict(checkins=[checkin], assessments=assessments,
        diagnoses=[NS(id=2,data_diagnostico=day,tipo='REGISTRO',status='ATIVO',cid=None,descricao_clinica=narrative,medico_nome='Profissional sintético',registrador_usuario_id=7,registrador_profissional_id=4)],
        interventions=[NS(id=3,data_intervencao=day,tipo='Acompanhamento',descricao=narrative,registrador_usuario_id=7,registrador_profissional_id=4)],
        plans=[NS(id=4,objetivo_geral='Objetivo sintético',data_inicio=day,data_fim=None,status='ATIVO',objetivos=[NS(id=5,descricao='Objetivo específico',status='ATIVO')])],
        planning=[NS(id=6,pts_id=4,objetivo_id=5,atividade_nome='Atividade sintética',ocupacao_nome='Psicólogo',profissional_nome='Profissional sintético',data_inicio=day,data_fim=None,frequencia_semanal=1,duracao_minutos=50,quantidade_sessoes=4,status='PLANEJADO')],
        sessions=[NS(id=i+7,agenda_cuidado_id=6,status='REALIZADA',data_agendada=day,data_realizacao=day,profissional_nome='Profissional sintético',narrativa=narrative,autor_usuario_id=7,autor_nome='Autor sintético') for i in range(3 if long else 1)])
    return NS(subject=dict(name='Pessoa sintética - atenção e saúde',pessoa_id=5,instituicao='Instituição sintética',instituicao_id=3,contexto_assistencial_id=2),period_start=day,period_end=day,clinical_reading=NS(summary='Síntese oficial sintética.', reference_date=day),collected_data={'MENTAL_HEALTH_PROVIDER':data})


def report(c):
    return CanonicalReport(report_code='CLN-MENTAL-001',report_name='Relatório Longitudinal Assistencial de Saúde Mental',report_version='1',subject=c.subject,period_start='2026-11-09',period_end='2026-11-09',generated_at=datetime(2026,11,9),sections=[b().build(c) for b in MENTAL_SECTIONS])


class MentalLayoutTests(unittest.TestCase):
    def test_record_groups_and_provenance(self):
        r=report(context())
        self.assertEqual(len(r.sections),12)
        self.assertTrue(all(c.type in ('MENTAL_TEXT', 'MENTAL_RECORD', 'MENTAL_METRICS') for s in r.sections for c in s.components))
        instruments=r.get_section('MENTAL_ASSESSMENTS').components
        self.assertEqual(len(instruments),3)
        self.assertNotIn('Resultado oficial:',str(instruments[2].data))
        self.assertIn('25/100',str(instruments[2].data))
        provenance=r.get_section('MENTAL_PROVENANCE')
        self.assertTrue(all(c.data['compact'] for c in provenance.components))
        self.assertIn('WHATSAPP',str(provenance))
        self.assertIn('Pessoa respondente #5',str(provenance))

    def test_short_long_pdf_content_and_pagination(self):
        folder=Path(os.environ.get('F24_PDF_DIR') or tempfile.mkdtemp(prefix='f24-'))
        folder.mkdir(parents=True,exist_ok=True)
        for long in (False,True):
            r=report(context(long));path=folder/('mental-long.pdf' if long else 'mental-short.pdf')
            PDFRenderer().render(r,str(path))
            pages=PdfReader(path).pages
            text=' '.join(re.sub(r'Página \d+', '', p.extract_text()).replace('Relatório Longitudinal - Saúde Mental', '').replace('Integra Care Health Platform', '') for p in pages)
            normalized=' '.join(text.split())
            for section in r.sections:
                for component in section.components:
                    d = component.data
                    values = d.get('paragraphs', []) + [str(v) for _, v in d.get('fields', [])]
                    values += [str(v) for _, v in d.get('metrics', [])]
                    for value in values:
                        content = normalized
                        if d.get('heading'):
                            content = ' '.join(line for line in text.splitlines() if line.strip() != d['heading'])
                            content = ' '.join(content.split())
                        self.assertIn(' '.join(value.split()), content)
            first_page = pages[0].extract_text()
            for heading in ('Resumo Executivo', 'Situação Atual', 'Indicadores da Jornada'):
                self.assertIn(heading, first_page)
            if not long:
                for instrument in ('PHQ-9', 'GAD-7', 'CBI'):
                    self.assertTrue(any(instrument in page.extract_text()
                        and ('Resultado oficial' if instrument != 'CBI' else 'Burnout Pessoal') in page.extract_text()
                        and f'Interpretação oficial sintética de {instrument}, sem recálculo.' in page.extract_text()
                        for page in pages), instrument)
            self.assertNotIn('Risco atual', text)
            self.assertNotIn('Tendência', text)
            for n,p in enumerate(pages,1):
                t=p.extract_text()
                self.assertIn('Relatório Longitudinal - Saúde Mental',t)
                self.assertIn(f'Página {n}',t)
                self.assertGreater(len(t),150)
                self.assertNotIn(t.strip().splitlines()[-1], [s.title for s in r.sections])
            self.assertLess(len(pages),35)
            if long:self.assertGreater(len(pages),3)

    def test_empty_sections(self):
        c=context();d=c.collected_data['MENTAL_HEALTH_PROVIDER']
        for key in d:d[key]={} if key=='assessments' else []
        r=report(c)
        for code in ('MENTAL_WELLBEING','MENTAL_ASSESSMENTS','MENTAL_PLANS','MENTAL_SESSIONS'):
            self.assertIn('Sem registros elegíveis no período.',str(r.get_section(code)))

    def test_structured_fields_and_factual_counts(self):
        c = context(); r = report(c)
        summary = r.get_section('MENTAL_SUMMARY')
        metrics = next(x.data['metrics'] for x in summary.components if x.type == 'MENTAL_METRICS')
        self.assertEqual(dict(metrics), {'Check-ins': 1, 'Aplicações': 3, 'Objetivos PTS': 1,
                                        'Planejamentos': 1, 'Sessões': 1})
        plans = r.get_section('MENTAL_PLANS').components
        self.assertEqual(dict(plans[0].data['fields'])['Objetivo geral'], 'Objetivo sintético')
        self.assertEqual(dict(plans[1].data['fields'])['PTS / Objetivo'], '#4 / #5')
        self.assertEqual(dict(plans[1].data['fields'])['Sessões previstas no planejamento integral'], 4)
        sessions = r.get_section('MENTAL_SESSIONS').components
        self.assertEqual(dict(sessions[0].data['fields'])['Agenda'], '#6')
        self.assertIn('Registro de atendimento:', sessions[0].data['paragraphs'][0])
        instruments = r.get_section('MENTAL_ASSESSMENTS').components
        self.assertEqual(instruments[0].data['metrics'], [('Resultado oficial', 3)])
        self.assertEqual(instruments[2].data['metrics'], [('Burnout Pessoal', '25/100'),
            ('Relacionado ao Trabalho', '40/100'), ('Relacionado aos Clientes', '50/100')])
        self.assertLess(summary.order, r.get_section('MENTAL_WELLBEING').order)
        self.assertLess(r.get_section('MENTAL_NARRATIVE').order, r.get_section('MENTAL_PROVENANCE').order)

    def test_long_objective_and_missing_values(self):
        import copy
        c = context(); d = c.collected_data['MENTAL_HEALTH_PROVIDER']
        d['plans'][0].objetivos[0].descricao = 'Objetivo extenso com atenção e vínculo. ' * 180
        d['sessions'][0].profissional_nome = None
        d['assessments']['PHQ-9']['applications'][0]['result']['score'] = 0
        d['assessments']['CBI']['applications'][0]['result']['dominios'][1]['score'] = 0
        before = copy.deepcopy(d)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'extended.pdf'
            PDFRenderer().render(report(c), str(path))
            pages = PdfReader(path).pages
            text = ' '.join(p.extract_text() for p in pages)
            for expected in ('Não informado', 'Relacionado ao Trabalho', 'Relacionado aos Clientes', '0/100', '50/100'):
                self.assertIn(expected, text)
            self.assertTrue(all(len(p.extract_text()) > 150 for p in pages))
        self.assertEqual(d, before)
