"""Economic Gate A input contracts; no preview or projection."""
import unittest
from datetime import date
from pydantic import ValidationError
from app.schemas.financeiro import (ServicoCreate, TabelaCreate, VersaoCreate,
    PrecoCreate, ContratoCreate, PacienteContratoCreate, MapeamentoCreate)


class ConfigurationContractTests(unittest.TestCase):
    def test_service_catalogue_defaults(self):
        data = ServicoCreate(codigo='FONO45', descricao='Fono', ocupacao_id=1, duracao_minutos=45)
        self.assertEqual((data.tipo_atendimento,data.unidade,data.ativo),('INDIVIDUAL','SESSAO',True))
        for change in ({'duracao_minutos':0},{'tipo_atendimento':'GRUPO'},{'unidade':'HORA'}, {'codigo':' '}):
            with self.assertRaises(ValidationError): ServicoCreate(**dict(data.model_dump(),**change))

    def test_price_zero_and_invalid_values(self):
        self.assertEqual(PrecoCreate(versao_id=1,servico_id=1,valor_base='0.00').valor_base,0)
        for value in ('-0.01','NaN','Infinity','-Infinity','1.001','1000000000000.00'):
            with self.assertRaises(ValidationError): PrecoCreate(versao_id=1,servico_id=1,valor_base=value)
        with self.assertRaises(ValidationError): PrecoCreate(versao_id=1,servico_id=1)

    def test_explicit_inputs_and_periods(self):
        with self.assertRaises(ValidationError): TabelaCreate(proprietario_instituicao_id=1,codigo='T',nome='T',moeda='USD')
        for schema,extra in ((ContratoCreate,dict(pagador_instituicao_id=1,codigo='C',edicao=1,tabela_preco_id=1)),
                             (PacienteContratoCreate,dict(paciente_id=1,contrato_id=1))):
            with self.assertRaises(ValidationError):schema(inicio=date(2026,2,1),fim=date(2026,1,31),**extra)
        with self.assertRaises(ValidationError):MapeamentoCreate(agenda_cuidado_id=1,servico_id=1,clinica_id=1)
        with self.assertRaises(ValidationError):VersaoCreate(tabela_id=1,numero=1,vigente_desde=date.today(),estado='PUBLISHED')
