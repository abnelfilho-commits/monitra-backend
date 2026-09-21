"""Presentation-only tests: synthetic contexts, no database access or SQL."""
import copy
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from app.services.report_engine.presentation import format_date_pt_br
from app.services.report_engine.report_composer import ReportComposer
from app.services.report_engine.renderers.pdf_renderer import PDFRenderer
from app.services.report_engine.sections.temporal_scope import TemporalScopeSection
from app.services.report_engine.sections.cardio import (
    CardioStatus, CardioDiagnoses, CardioRecords, CardioInterventions,
    CardioEvolution, CardioNarrative,
)
from app.services.report_engine.models import ReportComponent, ReportSection


class PresentationTests(unittest.TestCase):
    def context(self, line):
        event = dict(data='2026-07-08', date_basis='CREATED_AT', actor=None,
                     descricao='Texto livre 2026-06-30 preservado', origem='PROFISSIONAL',
                     tipo_evento='INTERVENTION', metadata={})
        return SimpleNamespace(
            definition=SimpleNamespace(code=line, name='Relatório '+line, version='1',
                sections=[TemporalScopeSection] + ([CardioStatus, CardioDiagnoses,
                    CardioRecords, CardioInterventions, CardioEvolution, CardioNarrative] if line=='CARDIO' else [])),
            subject={'id':1,'nome':'Paciente sintético'}, subject_id=1,
            care_line=SimpleNamespace(display_name=line), module=line,
            period_start=date(2026,7,1), period_end=date(2026,9,21),
            clinical_reading=SimpleNamespace(reference_date=date(2026,7,8),risk=None,trend=None,metadata={}),
            collected_data={'DIAGNOSIS_PROVIDER':{'historico':[dict(temporal_scope='ACTIVE_BEFORE_PERIOD',
                data_diagnostico='2026-06-30',descricao_clinica='Diagnóstico sintético',status='ATIVO')]},
                'TIMELINE_PROVIDER':[event,dict(event,date_basis='CLINICAL_DATE',tipo_evento='DAILY_RECORD')],
                'EVOLUTION_PROVIDER':[dict(data='2026-07-08',glicemia_jejum=None,pressao_sistolica=None,
                    pressao_diastolica=None,peso=None,imc=None)]},
            warnings=[],audit={},execution_id='synthetic',output_format='PDF',sections=[])

    def test_formatter(self):
        for raw,expected in [('2026-07-08','08/07/2026'),('2026-09-21','21/09/2026'),
                ('2026-06-30','30/06/2026'),('2024-02-29','29/02/2024'),
                ('2026-07-08T00:30:00+14:00','08/07/2026'),
                (date(2026,7,8),'08/07/2026'),(datetime(2026,7,8,12),'08/07/2026')]:
            with self.subTest(raw=raw): self.assertEqual(format_date_pt_br(raw),expected)
        for raw in (None,'','invalid','2026-02-30'):
            self.assertEqual(format_date_pt_br(raw),'Indisponível')

    def test_shared_scope_and_internal_contract(self):
        for line in ('NEURO','CARDIO'):
            with self.subTest(line=line):
                c=self.context(line); before=copy.deepcopy(c.collected_data)
                report=ReportComposer().compose(c)
                self.assertEqual(report.period_start,'2026-07-01')
                self.assertEqual(report.period_end,'2026-09-21')
                self.assertEqual(c.clinical_reading.reference_date,date(2026,7,8))
                self.assertEqual(c.collected_data,before)
                text=str(report.sections)
                for day in ('01/07/2026','21/09/2026','08/07/2026','30/06/2026'): self.assertIn(day,text)
                self.assertIn('anterior ao período',text)
                self.assertEqual([s.code for s in report.sections],[b.code for b in c.definition.sections])
                if line=='CARDIO':
                    self.assertIn('Data de criação (sem data clínica): 08/07/2026',text)
                    self.assertIn('Data clínica: 08/07/2026',text)
                    self.assertIn('Texto livre 2026-06-30 preservado',text)
                    self.assertIn('Tendência: Indisponível',text)

    def test_missing_reference(self):
        c=self.context('NEURO');c.clinical_reading.reference_date=None
        self.assertIn('referência indisponível',str(TemporalScopeSection().build(c)))

    def test_pdf_both_lines(self):
        from pypdf import PdfReader
        folder=Path(os.environ.get('REPORT_PRESENTATION_PDF_DIR') or tempfile.mkdtemp(prefix='report-presentation-'))
        folder.mkdir(parents=True,exist_ok=True)
        for line in ('NEURO','CARDIO'):
            report=ReportComposer().compose(self.context(line))
            report.generated_at=datetime(2026,9,21,12)
            if line=='NEURO':
                section=ReportSection('SYNTHETIC_DETAILS','Detalhes',2)
                section.add_component(ReportComponent('ASSESSMENT_SUMMARY',{'assessments':[{'instrument':'Sintético','date':'2026-07-08','score':0}]}))
                section.add_component(ReportComponent('DIAGNOSIS_SUMMARY',{'diagnosis_date':'2026-06-30'}))
                report.add_section(section)
            path=folder/(line.lower()+'.pdf'); PDFRenderer().render(report,str(path))
            text=' '.join(p.extract_text() for p in PdfReader(path).pages)
            for day in ('21/09/2026','01/07/2026','08/07/2026','30/06/2026'):self.assertIn(day,text)
            self.assertNotIn('2026-07-08',text)
            self.assertEqual(report.period_start,'2026-07-01')

    def test_endpoint_period_defaults_without_database(self):
        from unittest.mock import MagicMock, patch
        from app.routers.pacientes import baixar_relatorio_paciente_pdf
        patient=SimpleNamespace(id=1,created_at=datetime(2026,6,30))
        user=SimpleNamespace(id=9,perfil='PROFISSIONAL',clinica_id=2)
        db=MagicMock(); db.query.return_value.filter.return_value.filter.return_value.first.return_value=patient
        for line_code in ('NEURO','CARDIO'):
            line=SimpleNamespace(code=line_code)
            for start,end in ((date(2026,7,8),date(2026,9,21)),(date(2026,7,8),None),(None,date(2026,9,21)),(None,None)):
                with self.subTest(line=line_code,start=start,end=end), \
                     patch('app.services.care_lines.care_line_resolver.resolve',return_value=line), \
                     patch('app.services.care_lines.access.authorized_patient',return_value=(patient,line)), \
                     patch('app.routers.pacientes.ReportService') as service:
                    service.return_value.render.side_effect=lambda **kw:Path(kw['output_path']).write_bytes(b'%PDF-synthetic')
                    result=baixar_relatorio_paciente_pdf(1,line_code,start,end,db,user)
                    self.assertEqual(result.media_type,'application/pdf')
                    kw=service.return_value.generate.call_args.kwargs
                    self.assertEqual(kw['period_start'],start or date(2026,6,30))
                    self.assertEqual(kw['period_end'],end or date.today())
                    self.assertIsInstance(kw['period_start'],date)
        db.execute.assert_not_called()
