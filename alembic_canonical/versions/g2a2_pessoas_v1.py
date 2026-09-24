"""Canonical identity foundation only. No people, association, or backfill."""
from alembic import op
import sqlalchemy as sa

revision = "g2a2_pessoas_v1"
down_revision = "g1_institucional_v1"
branch_labels = None
depends_on = None

DOMAINS = ("pacientes", "profissionais", "usuarios", "responsaveis")


def upgrade():
    op.create_table(
        "pessoas",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("nome_completo", sa.Text(), nullable=False),
        sa.Column("nome_social", sa.Text()),
        sa.Column("data_nascimento", sa.Date()),
        sa.Column("sexo", sa.String(32)),
        sa.Column("cpf", sa.String(11)),
        sa.Column("email", sa.Text()),
        sa.Column("telefone", sa.String(32)),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cpf", name="uq_pessoas_cpf"),
        sa.CheckConstraint("nome_completo = trim(nome_completo) AND length(nome_completo) > 0", name="ck_pessoas_nome_completo"),
        *(sa.CheckConstraint(f"{field} IS NULL OR ({field} = trim({field}) AND length({field}) > 0)", name=f"ck_pessoas_{field}")
          for field in ("nome_social", "sexo", "email", "telefone")),
        sa.CheckConstraint("cpf IS NULL OR cpf ~ '^[0-9]{11}$'", name="ck_pessoas_cpf_formato"),
        sa.CheckConstraint("atualizado_em >= criado_em", name="ck_pessoas_timestamps"),
        schema="public",
    )
    for table in DOMAINS:
        op.add_column(table, sa.Column("pessoa_id", sa.Integer(), nullable=True), schema="public")
        op.create_foreign_key(f"fk_{table}_pessoa_id", table, "pessoas", ["pessoa_id"], ["id"],
                              source_schema="public", referent_schema="public", ondelete="RESTRICT")
        op.create_index(f"ix_{table}_pessoa_id", table, ["pessoa_id"], unique=False, schema="public")


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SHOW transaction_isolation")).scalar() != "read committed":
        raise RuntimeError("G2.A.2 downgrade exige READ COMMITTED para verificar dados após o lock")
    # Hold locks until the caller's transaction ends; close the check/drop race.
    connection.execute(sa.text("LOCK TABLE public.pessoas, public.pacientes, public.profissionais, public.usuarios, public.responsaveis IN ACCESS EXCLUSIVE MODE"))
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM public.pessoas)")).scalar():
        raise RuntimeError("G2.A.2 downgrade bloqueado: existem Pessoas canônicas")
    for table in DOMAINS:
        if connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM public.{table} WHERE pessoa_id IS NOT NULL)")).scalar():
            raise RuntimeError("G2.A.2 downgrade bloqueado: existem associações canônicas")
    for table in reversed(DOMAINS):
        op.drop_index(f"ix_{table}_pessoa_id", table_name=table, schema="public")
        op.drop_constraint(f"fk_{table}_pessoa_id", table, type_="foreignkey", schema="public")
        op.drop_column(table, "pessoa_id", schema="public")
    op.drop_table("pessoas", schema="public")
