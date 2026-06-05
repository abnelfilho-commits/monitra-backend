from alembic import op
import sqlalchemy as sa

revision = '26e0eeea73e1'
down_revision = '26a411d2e5b6'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'modulos_clinicos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nome', sa.String(length=150), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('slug')
    )

    op.create_table(
        'paciente_modulos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('paciente_id', sa.Integer(), sa.ForeignKey('pacientes.id'), nullable=False),
        sa.Column('modulo_id', sa.Integer(), sa.ForeignKey('modulos_clinicos.id'), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('data_inicio', sa.Date(), server_default=sa.text('CURRENT_DATE')),
        sa.Column('data_fim', sa.Date(), nullable=True),
        sa.Column('observacao', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now())
    )

    op.create_table(
        'paciente_condicoes_clinicas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('paciente_id', sa.Integer(), sa.ForeignKey('pacientes.id'), nullable=False),
        sa.Column('modulo_id', sa.Integer(), sa.ForeignKey('modulos_clinicos.id'), nullable=True),
        sa.Column('condicao', sa.String(length=100), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now())
    )

    op.create_table(
        'formularios_modulo',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('modulo_id', sa.Integer(), sa.ForeignKey('modulos_clinicos.id'), nullable=False),
        sa.Column('nome', sa.String(length=150), nullable=False),
        sa.Column('tipo', sa.String(length=50), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now())
    )

    op.create_table(
        'campos_formulario',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('formulario_id', sa.Integer(), sa.ForeignKey('formularios_modulo.id'), nullable=False),
        sa.Column('nome_campo', sa.String(length=100), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('tipo_campo', sa.String(length=50), nullable=False),
        sa.Column('obrigatorio', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('ordem', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('opcoes', sa.JSON(), nullable=True),
        sa.Column('regra_exibicao', sa.JSON(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=True, server_default=sa.text('true'))
    )

    op.create_table(
        'registros_longitudinais',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('paciente_id', sa.Integer(), sa.ForeignKey('pacientes.id'), nullable=False),
        sa.Column('modulo_id', sa.Integer(), sa.ForeignKey('modulos_clinicos.id'), nullable=False),
        sa.Column('formulario_id', sa.Integer(), sa.ForeignKey('formularios_modulo.id'), nullable=False),
        sa.Column('origem', sa.String(length=50), nullable=False),
        sa.Column('data_registro', sa.Date(), nullable=False),
        sa.Column('criado_por_usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('criado_por_responsavel_id', sa.Integer(), sa.ForeignKey('responsaveis.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now())
    )

    op.create_table(
        'respostas_registro',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('registro_id', sa.Integer(), sa.ForeignKey('registros_longitudinais.id'), nullable=False),
        sa.Column('campo_id', sa.Integer(), sa.ForeignKey('campos_formulario.id'), nullable=False),
        sa.Column('valor_texto', sa.Text(), nullable=True),
        sa.Column('valor_numero', sa.Numeric(12, 2), nullable=True),
        sa.Column('valor_booleano', sa.Boolean(), nullable=True),
        sa.Column('valor_data', sa.Date(), nullable=True),
        sa.Column('valor_hora', sa.Time(), nullable=True),
        sa.Column('valor_json', sa.JSON(), nullable=True)
    )

    op.create_table(
        'avaliacoes_modulo',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('paciente_id', sa.Integer(), sa.ForeignKey('pacientes.id'), nullable=False),
        sa.Column('modulo_id', sa.Integer(), sa.ForeignKey('modulos_clinicos.id'), nullable=False),
        sa.Column('data_avaliacao', sa.Date(), nullable=False),
        sa.Column('eixo_dominante', sa.String(length=150), nullable=True),
        sa.Column('eixos_secundarios', sa.JSON(), nullable=True),
        sa.Column('nivel_atividade', sa.String(length=100), nullable=True),
        sa.Column('sustentacao_clinica', sa.String(length=100), nullable=True),
        sa.Column('fatores_observados', sa.JSON(), nullable=True),
        sa.Column('biomarcadores_alterados', sa.JSON(), nullable=True),
        sa.Column('riscos_observados', sa.JSON(), nullable=True),
        sa.Column('tendencia', sa.String(length=100), nullable=True),
        sa.Column('impacto_funcional', sa.String(length=100), nullable=True),
        sa.Column('autonomia', sa.String(length=100), nullable=True),
        sa.Column('resposta_intervencoes', sa.Text(), nullable=True),
        sa.Column('status_validacao', sa.String(length=100), nullable=True),
        sa.Column('score_interno', sa.Numeric(8, 2), nullable=True),
        sa.Column('detalhes_internos', sa.JSON(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now())
    )


def downgrade():
    op.drop_table('avaliacoes_modulo')
    op.drop_table('respostas_registro')
    op.drop_table('registros_longitudinais')
    op.drop_table('campos_formulario')
    op.drop_table('formularios_modulo')
    op.drop_table('paciente_condicoes_clinicas')
    op.drop_table('paciente_modulos')
    op.drop_table('modulos_clinicos')
