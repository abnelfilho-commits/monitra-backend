"""Identity provenance and one canonical association per domain. No backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "g2a3_identidade_v1"
down_revision = "g2a2_pessoas_v1"
branch_labels = None
depends_on = None
DOMAINS = ("pacientes", "profissionais", "responsaveis", "usuarios")


def upgrade():
    c = op.get_bind()
    if c.execute(sa.text("SHOW transaction_isolation")).scalar() != "read committed":
        raise RuntimeError("G2.A.3 preflight exige READ COMMITTED")
    c.execute(sa.text("LOCK TABLE public.pacientes, public.profissionais, public.responsaveis, public.usuarios IN ACCESS EXCLUSIVE MODE"))
    for table in DOMAINS:
        if c.execute(sa.text(f"SELECT EXISTS (SELECT pessoa_id FROM public.{table} WHERE pessoa_id IS NOT NULL GROUP BY pessoa_id HAVING count(*) > 1)")).scalar():
            raise RuntimeError(f"G2.A.3 STOP_DUPLICATE_ASSOCIATION: {table}")
    for table in DOMAINS:
        op.create_unique_constraint(f"uq_{table}_pessoa_id", table, ["pessoa_id"], schema="public")
    op.create_table(
        "identidade_operacoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chave_idempotencia", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ator_usuario_id", sa.Integer(), sa.ForeignKey("public.usuarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tipo_operacao", sa.String(32), nullable=False),
        sa.Column("pessoa_id", sa.Integer(), sa.ForeignKey("public.pessoas.id", ondelete="RESTRICT"), nullable=False),
        *(sa.Column(column, sa.Integer(), sa.ForeignKey(f"public.{table}.id", ondelete="RESTRICT"))
          for column, table in (("paciente_id", "pacientes"), ("profissional_id", "profissionais"), ("responsavel_id", "responsaveis"), ("usuario_id", "usuarios"), ("pessoa_anterior_id", "pessoas"))),
        sa.Column("resultado", sa.String(32), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("tipo_evidencia", sa.Text()),
        sa.Column("referencia_evidencia", sa.Text()),
        sa.Column("requisicao_normalizada", postgresql.JSONB(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("chave_idempotencia", name="uq_identidade_operacao_chave"),
        sa.CheckConstraint("tipo_operacao IN ('PESSOA', 'ADICIONAR_PAPEL', 'ASSOCIAR_PAPEL', 'ASSOCIAR_CONTA')", name="ck_identidade_operacao_tipo"),
        sa.CheckConstraint("resultado IN ('PESSOA_CRIADA', 'PESSOA_REUTILIZADA', 'PAPEL_CRIADO', 'PAPEL_REUTILIZADO', 'LEGADO_ASSOCIADO', 'ASSOCIACAO_REUTILIZADA')", name="ck_identidade_operacao_resultado"),
        sa.CheckConstraint("num_nonnulls(paciente_id, profissional_id, responsavel_id, usuario_id) = CASE WHEN tipo_operacao = 'PESSOA' THEN 0 ELSE 1 END", name="ck_identidade_operacao_alvo"),
        sa.CheckConstraint("(tipo_operacao = 'ASSOCIAR_CONTA' AND usuario_id IS NOT NULL) OR (tipo_operacao <> 'ASSOCIAR_CONTA' AND usuario_id IS NULL)", name="ck_identidade_operacao_conta"),
        sa.CheckConstraint("tipo_operacao NOT IN ('ASSOCIAR_PAPEL', 'ASSOCIAR_CONTA') OR (tipo_evidencia IS NOT NULL AND length(trim(tipo_evidencia)) > 0 AND referencia_evidencia IS NOT NULL AND length(trim(referencia_evidencia)) > 0)", name="ck_identidade_operacao_evidencia"),
        sa.CheckConstraint("length(trim(motivo)) > 0", name="ck_identidade_operacao_motivo"),
        schema="public",
    )


def downgrade():
    c = op.get_bind()
    if c.execute(sa.text("SHOW transaction_isolation")).scalar() != "read committed":
        raise RuntimeError("G2.A.3 downgrade exige READ COMMITTED")
    c.execute(sa.text("LOCK TABLE public.identidade_operacoes IN ACCESS EXCLUSIVE MODE"))
    if c.execute(sa.text("SELECT EXISTS (SELECT 1 FROM public.identidade_operacoes)")).scalar():
        raise RuntimeError("G2.A.3 downgrade bloqueado: proveniência existente")
    op.drop_table("identidade_operacoes", schema="public")
    for table in reversed(DOMAINS):
        op.drop_constraint(f"uq_{table}_pessoa_id", table, type_="unique", schema="public")
