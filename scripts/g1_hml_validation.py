"""Read-only PostgreSQL 18 operational validation shared by executor/tests."""
from collections import Counter
from sqlalchemy import text

SOURCE = 'm0_baseline_v1'
TARGET = 'g1_institucional_v1'
TABLES = ('instituicoes', 'instituicao_papeis', 'paciente_instituicoes',
          'profissional_instituicoes', 'paciente_profissionais')
VIEWS = ('vw_demanda_capacidade', 'vw_dimensionamento_equipe',
         'vw_dimensionamento_ocupacao', 'vw_timeline_paciente')
EXPECTED_CONSTRAINTS = {
    'instituicoes': {'p': 1, 'f': 1, 'c': 4, 'u': 1, 'n': 6},
    'instituicao_papeis': {'p': 1, 'f': 1, 'c': 1, 'u': 1, 'n': 5},
    'paciente_instituicoes': {'p': 1, 'f': 2, 'c': 2, 'x': 1, 'n': 8},
    'profissional_instituicoes': {'p': 1, 'f': 3, 'c': 1, 'x': 1, 'n': 8},
    'paciente_profissionais': {'p': 1, 'f': 2, 'c': 1, 'x': 1, 'n': 7},
}
EXPECTED_INDEX_COUNTS = {
    'instituicoes': 2, 'instituicao_papeis': 3,
    'paciente_instituicoes': 4, 'profissional_instituicoes': 5,
    'paciente_profissionais': 4,
}


EXPECTED_NOT_NULL = {
    'instituicoes': {'id', 'razao_social', 'tipo_instituicao', 'ativo', 'criado_em', 'atualizado_em'},
    'instituicao_papeis': {'id', 'instituicao_id', 'papel', 'ativo', 'criado_em'},
    'paciente_instituicoes': {'id', 'paciente_id', 'instituicao_id', 'tipo_vinculo', 'data_inicio', 'ativo', 'criado_em', 'atualizado_em'},
    'profissional_instituicoes': {'id', 'profissional_id', 'instituicao_id', 'ocupacao_id', 'data_inicio', 'ativo', 'criado_em', 'atualizado_em'},
    'paciente_profissionais': {'id', 'paciente_id', 'profissional_instituicao_id', 'data_inicio', 'ativo', 'criado_em', 'atualizado_em'},
}


def expect(emit, check, expected, actual):
    """Only pass structural metadata or booleans, never URLs/credentials."""
    if actual != expected:
        emit('VALIDATION_MISMATCH', check=check, expected=expected, actual=actual)
        raise RuntimeError(check)


def identity(c, emit):
    row = c.execute(text('SELECT current_database(), current_user, current_schema()')).one()
    expect(emit, 'Identidade HML divergente',
           ('monitra_postgresql_hml', 'monitra_postgresql_hml_user', 'public'), tuple(row))
    return tuple(row)


def revisions(c):
    return list(c.execute(text('SELECT version_num FROM public.alembic_version')).scalars())


def views(c, emit):
    result = {}
    for name in VIEWS:
        row = c.execute(text('''
            SELECT c.oid, c.relkind, pg_get_viewdef(c.oid, true)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = :name AND c.relkind = 'v'
        '''), {'name': name}).one_or_none()
        expect(emit, 'View esperada ausente: ' + name, True, row is not None)
        result[name] = tuple(row)
    return result


def validate_result(c, prior_views, emit):
    expect(emit, 'Revision final divergente', [TARGET], revisions(c))
    expect(emit, 'Views alteradas', prior_views, views(c, emit))
    ext = c.execute(text('''
        SELECT e.extversion, n.nspname
        FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
        WHERE e.extname = 'btree_gist'
    ''')).one_or_none()
    expect(emit, 'btree_gist ausente', True, ext is not None)
    expect(emit, 'Versão btree_gist divergente', '1.8', ext.extversion)
    emit('BASELINE_VALIDATED', revision=TARGET, extension=tuple(ext), views=prior_views)
    for name in TABLES:
        params = {'qualified': 'public.' + name}
        kind = c.execute(text('''
            SELECT relkind FROM pg_class WHERE oid = to_regclass(:qualified)
        '''), params).scalar()
        expect(emit, 'Tabela G1 ausente/incompatível: ' + name, 'r', kind)
        constraints = c.execute(text('''
            SELECT conname, contype, convalidated, pg_get_constraintdef(oid) AS definition,
                   ARRAY(SELECT a.attname::text FROM unnest(conkey) WITH ORDINALITY AS k(num, ord)
                         JOIN pg_attribute a ON a.attrelid = conrelid AND a.attnum = k.num
                         ORDER BY k.ord) AS columns
            FROM pg_constraint WHERE conrelid = to_regclass(:qualified) ORDER BY conname
        '''), params).mappings().all()
        expect(emit, 'Conjunto de constraints divergente: ' + name,
               EXPECTED_CONSTRAINTS[name], dict(Counter(r['contype'] for r in constraints)))
        expected_columns = sorted(EXPECTED_NOT_NULL[name])
        actual_columns = sorted(tuple(r['columns']) for r in constraints if r['contype'] == 'n')
        expect(emit, 'Colunas NOT NULL divergentes: ' + name,
               [(column,) for column in expected_columns], actual_columns)
        attributes = list(c.execute(text('''
            SELECT attname::text FROM pg_attribute
            WHERE attrelid = to_regclass(:qualified) AND attnum > 0
              AND NOT attisdropped AND attnotnull ORDER BY attname
        '''), params).scalars())
        expect(emit, 'Nullability física divergente: ' + name, expected_columns, attributes)
        expect(emit, 'Constraints não validadas: ' + name, [],
               [r['conname'] for r in constraints if not r['convalidated']])
        indexes = c.execute(text('''
            SELECT i.relname, x.indisvalid, x.indisready, pg_get_indexdef(i.oid) AS definition
            FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
            WHERE x.indrelid = to_regclass(:qualified) ORDER BY i.relname
        '''), params).mappings().all()
        expect(emit, 'Quantidade de índices divergente: ' + name, EXPECTED_INDEX_COUNTS[name], len(indexes))
        expect(emit, 'Índice inválido: ' + name, [],
               [r['relname'] for r in indexes if not (r['indisvalid'] and r['indisready'])])
        emit('TABLE_VALIDATED', table=name,
             constraints=[dict(r) for r in constraints], indexes=[dict(r) for r in indexes])
