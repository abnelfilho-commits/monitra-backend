"""Characterization of existing Neuro behavior, not new clinical expectations."""
import unittest
from datetime import date
from types import SimpleNamespace
from app.services.neuro_clinical_rules import avaliar_regras


class NeuroPreservationTests(unittest.TestCase):
    def test_no_records(self):
        result = avaliar_regras([])
        self.assertEqual(result['prioridade'], 'BAIXA')
        self.assertEqual(result['alertas'], [])
        self.assertEqual(result['interpretacao'], 'Sem registros suficientes.')

    def test_sensory_threshold(self):
        for irritability, crisis, expected in ((2, 2, 'BAIXA'), (3, 1, 'BAIXA'), (3, 2, 'ALTA')):
            with self.subTest(irritability=irritability, crisis=crisis):
                result = avaliar_regras([SimpleNamespace(data=date(2026, 1, 1),
                                        irritabilidade=irritability, crise_sensorial=crisis)])
                self.assertEqual(result['prioridade'], expected)
                self.assertEqual('Sinais de desregulação sensorial.' in result['alertas'], expected == 'ALTA')

    def test_combined_observations(self):
        result = avaliar_regras([SimpleNamespace(data=date(2026, 1, 1), sono_qualidade=2,
            tempo_tela='2_4H', seletividade_alimentar='GRAVE', aceitou_alimento_novo=False,
            consistencia_fezes=1)])
        self.assertEqual(result['alertas'], [
            'Possível comprometimento da higiene do sono associado ao tempo de tela.',
            'Persistência de seletividade alimentar.', 'Alteração do padrão intestinal.'])
        self.assertEqual(result['prioridade'], 'BAIXA')
