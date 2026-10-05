"""Formalize the frozen capacity contract; never repair a partial installation."""
import re
from collections import Counter
from alembic import op
import sqlalchemy as sa

revision = 'capacidade_reconciliacao_v1'
down_revision = 'w2b_checkin_v1'
branch_labels = None
depends_on = None

CAP = 'capacidades_profissionais'
IO = 'institucional_operacoes'
SEQ = 'capacidades_profissionais_id_seq'
TARGETS = ('PACIENTE_INSTITUICAO', 'PROFISSIONAL_INSTITUICAO', 'PACIENTE_PROFISSIONAL')
TARGET_COLUMNS = ('paciente_instituicao_id', 'profissional_instituicao_id', 'paciente_profissional_id')


def target_check(expanded):
    names = TARGETS + (('CAPACIDADE_PROFISSIONAL',) if expanded else ())
    cols = TARGET_COLUMNS + (('capacidade_profissional_id',) if expanded else ())
    return ' OR '.join('(' + ' AND '.join([f"tipo_alvo = '{name}'"] +
        [f'{col} IS {"NOT " if i == j else ""}NULL' for j, col in enumerate(cols)]) + ')'
        for i, name in enumerate(names))


def result_check(expanded):
    pairs = [('CREATE_LINK', 'CREATED'), ('CLOSE_LINK', 'CLOSED'), ('INVALIDATE_LINK', 'INVALIDATED')]
    if expanded:
        pairs += [('CREATE_CAPACITY', 'CREATED'), ('CLOSE_CAPACITY', 'CLOSED'), ('INVALIDATE_CAPACITY', 'INVALIDATED')]
    return ' OR '.join(f"(operacao = '{a}' AND resultado = '{b}')" for a, b in pairs)


def norm(s):
    # Only representation differences: casts inserted by PG for varchar literals,
    # whitespace/case outside literals, and parentheses enclosing AND-only groups.
    s = re.sub(r'::(?:text|character varying)', '', s)
    return ' '.join(s.split())


def pg_check(expression):
    # pg_get_constraintdef(pretty=true) omits parentheses around AND branches.
    expression = re.sub(r'\(([^()]*)\)', r'\1', expression)
    return 'CHECK (' + expression + ')'


def require(ok, label):
    if not ok:
        raise RuntimeError('CAPACITY_RECONCILIATION_STOP:' + label)


def rows(c, sql, **args):
    return c.execute(sa.text(sql), args).mappings().all()


def exists(c, name):
    return c.execute(sa.text('SELECT to_regclass(:n) IS NOT NULL'), {'n': 'public.' + name}).scalar()


def columns(c, table):
    require(not rows(c, '''SELECT 1 FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid
        JOIN pg_namespace n ON n.oid=t.typnamespace WHERE a.attrelid=to_regclass(:n)
        AND a.attnum>0 AND NOT a.attisdropped AND n.nspname<>'pg_catalog' ''', n='public.'+table), table+':custom_type')
    return [tuple(r.values()) for r in rows(c, '''SELECT a.attname,format_type(a.atttypid,a.atttypmod),
        a.attnotnull,pg_get_expr(d.adbin,d.adrelid),a.attidentity,a.attgenerated
        FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid=to_regclass(:n) AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum''', n='public.'+table)]


def constraints(c, table):
    result = rows(c, '''SELECT conname,contype,convalidated,conenforced,condeferrable,condeferred,
        pg_get_constraintdef(oid,true) AS definition FROM pg_constraint WHERE conrelid=to_regclass(:n)''', n='public.'+table)
    require(all(r['convalidated'] and r['conenforced'] and not r['condeferrable'] and not r['condeferred'] for r in result), table+':constraint_flags')
    return result


def plain_table(c, table):
    r = rows(c, '''SELECT relkind,relpersistence,relrowsecurity,relforcerowsecurity,relispartition
        FROM pg_class WHERE oid=to_regclass(:n)''', n='public.'+table)
    require(len(r)==1 and tuple(r[0].values())==('r','p',False,False,False), table+':table')
    for catalog, column, extra in [('pg_trigger','tgrelid','AND NOT tgisinternal'),('pg_policy','polrelid',''),('pg_rewrite','ev_class','')]:
        require(not rows(c, f'SELECT 1 FROM {catalog} WHERE {column}=to_regclass(:n) {extra}', n='public.'+table), table+':'+catalog)
    require(not rows(c, 'SELECT 1 FROM pg_inherits WHERE inhrelid=to_regclass(:n) OR inhparent=to_regclass(:n)', n='public.'+table), table+':inheritance')


def validate_io(c, expanded):
    plain_table(c, IO)
    expected = [
        ('id','integer',True,"nextval('institucional_operacoes_id_seq'::regclass)",'',''),
        ('ator_usuario_id','integer',True,None,'',''), ('instituicao_id','integer',True,None,'',''),
        ('operacao','character varying(32)',True,None,'',''),('tipo_alvo','character varying(32)',True,None,'',''),
        *[(x,'integer',False,None,'','') for x in TARGET_COLUMNS],
        ('motivo','text',True,None,'',''),('resultado','character varying(16)',True,None,'',''),
        ('estado_anterior','jsonb',False,None,'',''),('estado_final','jsonb',True,None,'',''),
        ('criado_em','timestamp with time zone',True,'now()','','')]
    if expanded:
        expected.append(('capacidade_profissional_id','integer',False,None,'',''))
    require(columns(c, IO)==expected, 'io:columns')
    cons = constraints(c, IO)
    expected_defs = [('p','PRIMARY KEY (id)'),('c','CHECK (length(TRIM(BOTH FROM motivo)) > 0)'),
        ('c',pg_check(target_check(expanded))),('c',pg_check(result_check(expanded)))]
    for col, target in [('ator_usuario_id','usuarios'),('instituicao_id','instituicoes'),
        ('paciente_instituicao_id','paciente_instituicoes'),('profissional_instituicao_id','profissional_instituicoes'),
        ('paciente_profissional_id','paciente_profissionais')]+([('capacidade_profissional_id',CAP)] if expanded else []):
        expected_defs.append(('f',f'FOREIGN KEY ({col}) REFERENCES {target}(id) ON DELETE RESTRICT'))
    require(Counter((r['contype'],norm(r['definition'])) for r in cons if r['contype']!='n')==Counter((t,norm(d)) for t,d in expected_defs), 'io:constraints')
    named = {r['conname']:r for r in cons}
    for name, expression in [('ck_institucional_operacao_alvo',target_check(expanded)),
                             ('ck_institucional_operacao_resultado',result_check(expanded))]:
        require(name in named and norm(named[name]['definition'])==norm(pg_check(expression)), 'io:check_name_definition')
    if expanded:
        fk=named.get('fk_institucional_operacoes_capacidade_profissional')
        require(fk is not None and fk['definition']=='FOREIGN KEY (capacidade_profissional_id) REFERENCES capacidades_profissionais(id) ON DELETE RESTRICT', 'io:fk_name_definition')
    validate_indexes(c,IO,[('institucional_operacoes_pkey','btree',True,True,['id'],None),
        ('ix_institucional_operacoes_instituicao_id','btree',False,False,['instituicao_id'],None)])


def validate_indexes(c, table, expected):
    actual=[]
    for r in rows(c, '''SELECT i.*,ic.relname,am.amname,
      pg_get_expr(i.indpred,i.indrelid,true) AS predicate,
      ARRAY(SELECT pg_get_indexdef(i.indexrelid,k,true) FROM generate_series(1,i.indnatts) k) AS keys
      FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_am am ON am.oid=ic.relam
      WHERE i.indrelid=to_regclass(:n)''', n='public.'+table):
        require(r['indisvalid'] and r['indisready'] and r['indislive'] and not r['indnullsnotdistinct']
            and r['indnkeyatts']==r['indnatts'], table+':index_flags')
        actual.append((r['relname'],r['amname'],r['indisunique'],r['indisprimary'],tuple(r['keys']),r['predicate']))
    require(set(actual)=={(a,b,d,e,tuple(f),g) for a,b,d,e,f,g in expected}, table+':indexes')


def validate_capacity(c):
    plain_table(c,CAP)
    require(columns(c,CAP)==[
        ('id','integer',True,"nextval('capacidades_profissionais_id_seq'::regclass)",'',''),
        ('profissional_instituicao_id','integer',True,None,'',''),('minutos_semanais','integer',True,None,'',''),
        ('data_inicio','date',True,None,'',''),('data_fim','date',False,None,'',''),
        ('ativo','boolean',True,'true','',''),('criado_em','timestamp with time zone',True,'now()','',''),
        ('atualizado_em','timestamp with time zone',True,'now()','','')], 'capacity:columns')
    cons=constraints(c,CAP)
    expected=[('p','PRIMARY KEY (id)'),('f','FOREIGN KEY (profissional_instituicao_id) REFERENCES profissional_instituicoes(id) ON DELETE RESTRICT'),
        ('c','CHECK (minutos_semanais > 0)'),('c','CHECK (data_fim IS NULL OR data_fim >= data_inicio)'),
        ('x',"EXCLUDE USING gist (profissional_instituicao_id WITH =, daterange(data_inicio, data_fim, '[]'::text) WITH &&) WHERE (ativo)")]
    require(Counter((r['contype'],norm(r['definition'])) for r in cons if r['contype']!='n')==Counter((t,norm(d)) for t,d in expected), 'capacity:constraints')
    require(any(r['conname']=='ex_capacidade_profissional_vigencia' and r['contype']=='x' for r in cons), 'capacity:exclude_name')
    validate_indexes(c,CAP,[('capacidades_profissionais_pkey','btree',True,True,['id'],None),
        ('ix_capacidades_profissionais_profissional_instituicao_id','btree',False,False,['profissional_instituicao_id'],None),
        ('ex_capacidade_profissional_vigencia','gist',False,False,['profissional_instituicao_id',"daterange(data_inicio, data_fim, '[]'::text)"],'ativo')])
    seq=rows(c, '''SELECT format_type(s.seqtypid,NULL) AS type,s.seqstart,s.seqincrement,s.seqmin,s.seqmax,s.seqcache,s.seqcycle,
        d.refobjid::regclass::text AS owner_table,a.attname,d.deptype
        FROM pg_sequence s JOIN pg_depend d ON d.classid='pg_class'::regclass AND d.objid=s.seqrelid
          AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i')
        JOIN pg_attribute a ON a.attrelid=d.refobjid AND a.attnum=d.refobjsubid
        WHERE s.seqrelid=to_regclass(:n)''', n='public.'+SEQ)
    require(len(seq)==1 and tuple(seq[0].values())==('integer',1,1,1,2147483647,1,False,CAP,'id','a'), 'capacity:sequence')
    require(not rows(c, '''SELECT 1 FROM pg_depend d JOIN pg_rewrite r ON d.classid='pg_rewrite'::regclass AND d.objid=r.oid
        JOIN pg_class c ON c.oid=r.ev_class WHERE d.refclassid='pg_class'::regclass
        AND d.refobjid=to_regclass(:n) AND c.relkind IN ('v','m')''', n='public.'+CAP), 'capacity:dependent_view')
    incoming=rows(c, '''SELECT conrelid::regclass::text AS source,conname FROM pg_constraint
        WHERE contype='f' AND confrelid=to_regclass(:n)''', n='public.'+CAP)
    require([tuple(x.values()) for x in incoming]==[(IO,'fk_institucional_operacoes_capacidade_profissional')], 'capacity:incoming_fk')
    owned=rows(c, '''SELECT d.objid::regclass::text AS sequence FROM pg_depend d
        JOIN pg_class s ON s.oid=d.objid AND s.relkind='S'
        WHERE d.classid='pg_class'::regclass AND d.refclassid='pg_class'::regclass
        AND d.refobjid=to_regclass(:n) AND d.deptype IN ('a','i')''', n='public.'+CAP)
    require([r['sequence'] for r in owned]==[SEQ], 'capacity:owned_sequences')
    # User-defined expression functions would change the frozen contract.
    require(not rows(c, '''WITH objects AS (
        SELECT 'pg_attrdef'::regclass AS classid,oid FROM pg_attrdef WHERE adrelid=to_regclass(:n)
        UNION SELECT 'pg_constraint'::regclass,oid FROM pg_constraint WHERE conrelid=to_regclass(:n)
        UNION SELECT 'pg_class'::regclass,indexrelid FROM pg_index WHERE indrelid=to_regclass(:n))
        SELECT 1 FROM objects o JOIN pg_depend d ON d.classid=o.classid AND d.objid=o.oid
        JOIN pg_proc p ON d.refclassid='pg_proc'::regclass AND p.oid=d.refobjid
        JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname<>'pg_catalog' ''', n='public.'+CAP), 'capacity:custom_function')
    validate_io(c,True)


def create_capacity(c):
    c.exec_driver_sql('''CREATE TABLE public.capacidades_profissionais (
        id SERIAL PRIMARY KEY,
        profissional_instituicao_id integer NOT NULL REFERENCES public.profissional_instituicoes(id) ON DELETE RESTRICT,
        minutos_semanais integer NOT NULL CHECK (minutos_semanais > 0),
        data_inicio date NOT NULL, data_fim date,
        ativo boolean NOT NULL DEFAULT true,
        criado_em timestamptz NOT NULL DEFAULT now(), atualizado_em timestamptz NOT NULL DEFAULT now(),
        CHECK (data_fim IS NULL OR data_fim >= data_inicio),
        CONSTRAINT ex_capacidade_profissional_vigencia EXCLUDE USING gist
        (profissional_instituicao_id WITH =, daterange(data_inicio,data_fim,'[]') WITH &&) WHERE (ativo))''')
    c.exec_driver_sql('CREATE INDEX ix_capacidades_profissionais_profissional_instituicao_id ON public.capacidades_profissionais (profissional_instituicao_id)')
    c.exec_driver_sql('ALTER TABLE public.institucional_operacoes ADD COLUMN capacidade_profissional_id integer NULL')
    c.exec_driver_sql('ALTER TABLE public.institucional_operacoes ADD CONSTRAINT fk_institucional_operacoes_capacidade_profissional FOREIGN KEY (capacidade_profissional_id) REFERENCES public.capacidades_profissionais(id) ON DELETE RESTRICT')
    for name, expression in [('ck_institucional_operacao_alvo',target_check(True)),('ck_institucional_operacao_resultado',result_check(True))]:
        c.exec_driver_sql(f'ALTER TABLE public.institucional_operacoes DROP CONSTRAINT {name}')
        c.exec_driver_sql(f'ALTER TABLE public.institucional_operacoes ADD CONSTRAINT {name} CHECK ({expression})')


def upgrade():
    c=op.get_bind()
    require(c.dialect.name=='postgresql', 'postgresql_required')
    require(c.exec_driver_sql('SHOW transaction_isolation').scalar()=='read committed', 'read_committed_required')
    require(int(c.exec_driver_sql('SHOW server_version_num').scalar())//10000>=18,'postgresql18_required')
    c.exec_driver_sql('SET LOCAL search_path TO public, pg_catalog')
    c.exec_driver_sql('LOCK TABLE public.institucional_operacoes, public.profissional_instituicoes IN ACCESS EXCLUSIVE MODE')
    require(bool(c.exec_driver_sql("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='btree_gist')").scalar()), 'btree_gist')
    if exists(c,CAP):
        c.exec_driver_sql('LOCK TABLE public.capacidades_profissionais IN ACCESS EXCLUSIVE MODE')
        validate_capacity(c)
    else:
        require(not exists(c,SEQ) and not exists(c,'ix_capacidades_profissionais_profissional_instituicao_id')
            and not exists(c,'ex_capacidade_profissional_vigencia'), 'orphan_capacity_objects')
        validate_io(c,False)
        create_capacity(c)
        validate_capacity(c)


def downgrade():
    raise RuntimeError('CAPACITY_RECONCILIATION_DOWNGRADE_BLOCKED: adopted provenance cannot be discarded automatically')
