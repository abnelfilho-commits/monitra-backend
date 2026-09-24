"""Frozen canonical baseline. Empty public schema only; no data/seed/backfill.

The historical lineage remains in alembic/versions. Existing installations
must undergo separately approved reconciliation, never this bootstrap.
"""
import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "m0_baseline_v1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    objects = connection.execute(sa.text("""
        SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f')
          AND c.relname <> 'alembic_version'
    """)).scalars().all()
    if objects:
        raise RuntimeError("Canonical bootstrap refused: public schema is not empty")
    contract = json.loads((Path(__file__).parents[1] / "baseline_v1.json").read_text())
    # SQL identifiers/definitions below are frozen, version-controlled metadata,
    # never request/user input or reflection of mutable application Models.
    op.execute("SET LOCAL search_path TO public")
    for sequence in contract["sequences"]:
        op.execute(
            'CREATE SEQUENCE "{sequence_name}" AS {data_type} '
            'INCREMENT BY {increment_by} MINVALUE {min_value} MAXVALUE {max_value} '
            'START WITH {start_value} CACHE {cache_size} NO CYCLE'.format(**sequence)
        )
    for name, table in contract["tables"].items():
        columns = []
        for column in table["columns"]:
            definition = '"{column_name}" {formatted_type}'.format(**column)
            if column["default_expression"] is not None:
                definition += " DEFAULT " + column["default_expression"]
            if not column["nullable"]:
                definition += " NOT NULL"
            columns.append(definition)
        op.execute('CREATE TABLE public."{}" ({})'.format(name, ", ".join(columns)))
    for sequence in contract["sequences"]:
        op.execute('ALTER SEQUENCE "{sequence_name}" OWNED BY "{owner_table}"."{owner_column}"'.format(**sequence))
    # All PK/UNIQUE first, then FKs (including circular dependencies).
    for key in ("constraints", "foreign_keys"):
        for name, table in contract["tables"].items():
            for constraint in table[key]:
                op.execute('ALTER TABLE public."{}" ADD CONSTRAINT "{}" {}'.format(
                    name, constraint["constraint_name"], constraint["definition"]))
    for table in contract["tables"].values():
        for index in table["indexes"]:
            op.execute(index["definition"])
    for view in contract["views"]:
        op.execute('CREATE VIEW public."{}" AS {}'.format(view["name"], view["definition"]))


def downgrade():
    raise RuntimeError("Baseline teardown is destructive; restore an approved backup instead")
