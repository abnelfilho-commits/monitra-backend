from sqlalchemy import Column, Integer, String, Text, Boolean, Date, DateTime, ForeignKey, Numeric, Time, JSON
from sqlalchemy.sql import func
from app.database import Base


class ModuloClinico(Base):
    __tablename__ = "modulos_clinicos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, server_default=func.now())


class PacienteModulo(Base):
    __tablename__ = "paciente_modulos"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id"), nullable=False)
    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=False)
    ativo = Column(Boolean, default=True)
    data_inicio = Column(Date, nullable=True)
    data_fim = Column(Date, nullable=True)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime, server_default=func.now())


class PacienteCondicaoClinica(Base):
    __tablename__ = "paciente_condicoes_clinicas"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id"), nullable=False)
    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=True)
    condicao = Column(String(100), nullable=False)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, server_default=func.now())


class FormularioModulo(Base):
    __tablename__ = "formularios_modulo"

    id = Column(Integer, primary_key=True, index=True)
    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=False)
    nome = Column(String(150), nullable=False)
    tipo = Column(String(50), nullable=False)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, server_default=func.now())


class CampoFormulario(Base):
    __tablename__ = "campos_formulario"

    id = Column(Integer, primary_key=True, index=True)
    formulario_id = Column(Integer, ForeignKey("formularios_modulo.id"), nullable=False)
    nome_campo = Column(String(100), nullable=False)
    label = Column(String(200), nullable=False)
    tipo_campo = Column(String(50), nullable=False)
    obrigatorio = Column(Boolean, default=False)
    ordem = Column(Integer, default=0)
    opcoes = Column(JSON, nullable=True)
    regra_exibicao = Column(JSON, nullable=True)
    ativo = Column(Boolean, default=True)


class RegistroLongitudinal(Base):
    __tablename__ = "registros_longitudinais"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id"), nullable=False)
    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=False)
    formulario_id = Column(Integer, ForeignKey("formularios_modulo.id"), nullable=False)
    origem = Column(String(50), nullable=False)
    data_registro = Column(Date, nullable=False)
    criado_por_usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    criado_por_responsavel_id = Column(Integer, ForeignKey("responsaveis.id"), nullable=True)
    criado_em = Column(DateTime, server_default=func.now())


class RespostaRegistro(Base):
    __tablename__ = "respostas_registro"

    id = Column(Integer, primary_key=True, index=True)
    registro_id = Column(Integer, ForeignKey("registros_longitudinais.id"), nullable=False)
    campo_id = Column(Integer, ForeignKey("campos_formulario.id"), nullable=False)
    valor_texto = Column(Text, nullable=True)
    valor_numero = Column(Numeric(12, 2), nullable=True)
    valor_booleano = Column(Boolean, nullable=True)
    valor_data = Column(Date, nullable=True)
    valor_hora = Column(Time, nullable=True)
    valor_json = Column(JSON, nullable=True)


class AvaliacaoModulo(Base):
    __tablename__ = "avaliacoes_modulo"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id"), nullable=False)
    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=False)
    data_avaliacao = Column(Date, nullable=False)
    eixo_dominante = Column(String(150), nullable=True)
    eixos_secundarios = Column(JSON, nullable=True)
    nivel_atividade = Column(String(100), nullable=True)
    sustentacao_clinica = Column(String(100), nullable=True)
    fatores_observados = Column(JSON, nullable=True)
    biomarcadores_alterados = Column(JSON, nullable=True)
    riscos_observados = Column(JSON, nullable=True)
    tendencia = Column(String(100), nullable=True)
    impacto_funcional = Column(String(100), nullable=True)
    autonomia = Column(String(100), nullable=True)
    resposta_intervencoes = Column(Text, nullable=True)
    status_validacao = Column(String(100), nullable=True)
    score_interno = Column(Numeric(8, 2), nullable=True)
    detalhes_internos = Column(JSON, nullable=True)
    criado_em = Column(DateTime, server_default=func.now())
