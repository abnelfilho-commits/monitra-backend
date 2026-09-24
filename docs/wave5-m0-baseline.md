# Wave 5 — M0 — FINAL

**STATUS: M0_PASS — formalmente aprovado.**

Este documento consolida os Checkpoints A–D.4. A adoção HML foi executada
pelo operador humano; suas evidências foram fornecidas pela ponte operacional.
O fechamento não autoriza G1, commit, push ou deploy.

## Escopo e proveniência

Base: `7051b8b12293d18fd9b2f8692a4e86cc80985968`, detached worktree
`/private/tmp/integra-wave5-baseline`. Nenhuma modificação de regras clínicas,
routers, serviços assistenciais ou contratos de API. Nenhum G1.

Fonte física: inventário estrutural TC-02 fornecido pelo operador
`wave5_tc02_hml_schema.txt` (PostgreSQL 18.4). **A coleta não ocorreu em
transação READ ONLY**: houve reconexão e `transaction_read_only=off`.
O inventário contém metadados. As comprovações HML posteriores vieram da ponte
operacional humana; o agente não repetiu a adoção nem acessou HML nesses checkpoints.
As linhas 75–395 contêm colunas, 396–489 PK/FK/UNIQUE, 620–723 índices/sequences,
724–737 views/dependências. Sem comentários de coluna/tabela, RLS, policies,
triggers de usuário ou particionamento registrados no escopo.

Exceção de proveniência: existência de `whatsapp_mensagens` consta do inventário,
mas suas seis colunas não foram detalhadas. Sua definição congelada vem da
revision histórica `8c01a0d1a004` e Model correspondente, que coincidem.
A coleta D.1 e a comprovação final por `\d public.whatsapp_mensagens` fecharam
essa lacuna: seis colunas compatíveis, PK btree em message_id, sem FK, UNIQUE
adicional ou outro índice apresentado. A confirmação física é de D.1, não TC-02.

## Checkpoint A — inventário final e decisões

### Consumidores e limites

| Objeto | Evidência local | Decisão M0 |
|---|---|---|
| pacientes.profissional_id | `app/routers/pacientes.py:45,155,236,257`; relações em paciente/profissional | Preservar coluna e join ORM explícito. Sem FK física, sem novo vínculo/backfill. LEGADO TRANSITÓRIO. |
| capacidade_instalada | `app/main.py:32,99`; `app/routers/capacidade_instalada.py:24,39,87,120,158`; frontend DimensionamentoEquipe | Model/router preservados. Tabela ausente HML, excluída da baseline. CRUD dessa tabela continua uma limitação anterior; M0 não a torna funcional. View de demanda existente preservada. |
| vw_dimensionamento_ocupacao | `app/routers/dimensionamento.py:31` | Preservar transitoriamente. |
| vw_demanda_capacidade | `app/routers/capacidade_instalada.py:158` | Preservar transitoriamente, inclusive sem reinterpretar seus valores constantes. |
| vw_dimensionamento_equipe | Nenhum consumidor no código ativo encontrado | Ausente da instalação nova; LEGADO ADICIONAL / PRESERVAÇÃO TRANSITÓRIA em HML. EXTERNAL_CONSUMER_NOT_PROVABLE. NÃO remover nesta M0. |
| vw_timeline_paciente | `app/routers/copia_timeline.py:106`, router não registrado; script manual legado | Sem consumidor ativo comprovado. Ausente da instalação nova; LEGADO ADICIONAL / PRESERVAÇÃO TRANSITÓRIA em HML. EXTERNAL_CONSUMER_NOT_PROVABLE. NÃO remover nesta M0. |
| agenda_cuidados | `app/models/agenda_cuidado.py`; scheduling/care-plan/session services | Planejamento PTS atual. Sem UNIQUE funcional adicional; apenas PK. Não existe planejamento_atividades. |
| sessoes_assistenciais | `app/models/sessao_assistencial.py`, `app/services/session_service.py` | Agenda ancestral obrigatória e UNIQUE(agenda_cuidado_id,numero_sessao) preservadas. |
| registros_diarios | `app/routers/registros.py:27,63,77`; schemas/registro.py | LEGADO NEURO — PRESERVAÇÃO TRANSITÓRIA / CONTRATO RECONCILIADO. |

`registros_diarios`: removidos somente atributos ORM fisicamente inexistentes
`tempo_tela`, `seletividade_alimentar`, `aceitou_alimento_novo`.
O router legado cria/edita apenas seus campos antigos, não estes três atributos.
O router alternativo `registros_diarios.py` referencia módulos inexistentes e não
está registrado; não foi promovido como caminho ativo.
Os três campos continuam em `app/schemas/registro.py`, provider Neuro e
`app/routers/responsavel_registros.py:61,134`; o motor reconstrói-os por
`app/services/neuro_engine.py:129–193` de respostas/campos longitudinais.
Nenhum consumidor ativo necessário dos três atributos do **objeto legado** foi encontrado.

### As 13 colunas longitudinais

| Coluna | Classificação / fonte | Tratamento |
|---|---|---|
| observacoes | Canônica, texto complementar do evento | Preservada física e explicitada ORM. |
| score_clinico | Snapshot histórico derivado | Preservado físico, sem promovê-lo a leitura atual. |
| risco | Snapshot histórico derivado | Idem. |
| protocolo | Snapshot histórico derivado | Idem. |
| leitura_clinica | Snapshot histórico derivado | Idem. |
| glicemia_jejum | Projeção derivada; respostas são canônicas | Preservada fisicamente, fora do ORM; nenhuma remoção/backfill. |
| glicemia_pos_prandial | Idem | Idem. |
| pressao_sistolica | Idem | Idem. |
| pressao_diastolica | Idem | Idem. |
| peso | Idem | Idem. |
| sono | Idem | Idem. |
| humor | Idem | Idem. |
| modulo | Duplicação legada; modulo_id é identidade canônica | Preservado físico; não usado para inferir Linha. |

Consumidores históricos: `daily_record/providers/cardio.py` escreve somente
snapshots/observacoes; `longitudinal/adapters/registro.py` lê interpretação do
próprio evento; `routers/responsavel_cardio.py` mantém histórico e reconstrói
medições via respostas. `cardio_evolution.py` e provider ClinicalReading não foram
modificados. Sem evidência que autorize descartar informação exclusiva das
projeções antigas. Nenhuma dessas colunas foi removida.

### Varredura estrutural global e correções declarativas

- `usuarios.profissional_id`: FK opcional ON DELETE SET NULL.
- `pacientes.profissional_id`: remover declaração de FK, preservar relações com `foreign()`.
- `profissionais.clinica_id`: nullable; índice físico representado.
- `atividade_ocupacao`: UNIQUE existente refletida no ORM.
- `registros_diarios`: tipos varchar/boolean aprovados, origem nullable;
  alimentacao varchar; FK paciente CASCADE; UNIQUE(paciente_id,data); índice origem.
- `formularios_modulo.codigo`: varchar(50) nullable conforme HML, não varchar(100)
  do Model nem NOT NULL da migration histórica. Sem alteração de dados/formulários.
- Defaults físicos declarados onde ausentes (ativos, status, ordem,
  obrigatorio, principal e CURRENT_DATE), preservados defaults Python existentes.
- Removidas declarações de índices redundantes em PKs que não existem em HML.
- Representados índices físicos de avaliações e diagnóstico por paciente/Linha.
- Nome da UNIQUE profissional_modulos reconciliado.
- Nenhum novo CHECK, FK assistencial ou regra de unicidade foi inventado.
- Constraints/FKs/índices/defaults dos Models são comparados ao catálogo criado.
- Exceções explícitas ao mapeamento ORM completo: capacidade_instalada excluída;
  12 colunas longitudinais transitórias mantidas só fisicamente; intervenção
  Cardio já usa projeção SQLAlchemy própria, preservada (sem autoria inferida).

Nenhum novo conflito funcional humano foi identificado nessa varredura.

## Checkpoint B — estratégia

Nova cadeia independente em `alembic_canonical/`, configuração
`alembic-canonical.ini`, head único `m0_baseline_v1`, sem down_revision histórica.
A cadeia `alembic/versions` e `alembic.ini` permanecem byte a byte intactas com
head `8c01a0d1a004` para instalações ainda não reconciliadas.
**Não misturar as duas configurações nem executar ambas na mesma instalação.**

`baseline_v1.json` é o contrato estrutural congelado, sem dados pessoais,
sem contadores correntes de sequences e sem seed. A migration não importa
Models nem gera tabelas a partir de metadata mutável. Alterações futuras devem
ser novas revisions; não reescrever este snapshot depois de publicado.

Instalação nova: URL explícita `M0_DATABASE_URL`, PostgreSQL com public vazio,
`python -m alembic -c alembic-canonical.ini upgrade head`.
Recusa schema existente, exige online para esse guard e não carrega `.env`.
Downgrade destrutivo da baseline é recusado. O template permite futuras revisions
explícitas; autogenerate não foi habilitado sobre metadata parcial/legada.
Nenhuma mudança em comando de deploy/infraestrutura foi feita.

## Objetos exatos da instalação nova

30 tabelas de domínio, 294 colunas, 55 FKs, 30 PKs, 7 UNIQUEs,
37 índices adicionais (74 índices incluindo suportes PK/UNIQUE), 29 sequences,
2 views transitórias. Além disso, Alembic cria sua tabela técnica de versionamento.

| Tabela | Colunas | FKs |
|---|---:|---:|
| `agenda_cuidados` | 17 | 5 |
| `atividade_ocupacao` | 3 | 2 |
| `atividades_terapeuticas` | 7 | 1 |
| `avaliacoes_clinicas` | 19 | 0 |
| `avaliacoes_modulo` | 19 | 2 |
| `campos_formulario` | 10 | 1 |
| `clinicas` | 7 | 0 |
| `diagnosticos` | 15 | 2 |
| `formularios_modulo` | 7 | 1 |
| `intervencoes` | 8 | 3 |
| `intervencoes_cardiometabolicas` | 7 | 2 |
| `modulos_clinicos` | 6 | 0 |
| `ocupacoes_profissionais` | 3 | 0 |
| `paciente_condicoes_clinicas` | 6 | 2 |
| `paciente_modulos` | 8 | 2 |
| `pacientes` | 11 | 1 |
| `profissionais` | 8 | 2 |
| `profissional_modulos` | 4 | 2 |
| `pts` | 11 | 3 |
| `pts_objetivos` | 7 | 1 |
| `registros_diarios` | 15 | 2 |
| `registros_longitudinais` | 22 | 5 |
| `responsaveis` | 9 | 1 |
| `responsavel_paciente` | 7 | 2 |
| `respostas_registro` | 9 | 2 |
| `sessoes_assistenciais` | 21 | 5 |
| `usuarios` | 8 | 2 |
| `vinculos` | 4 | 2 |
| `whatsapp_conversas` | 10 | 2 |
| `whatsapp_mensagens` | 6 | 0 |

Views: `vw_dimensionamento_ocupacao`, `vw_demanda_capacidade`.
Sem seeds de módulos/formulários/usuários: instalação estrutural não equivale a
ambiente funcional populado. Configuração de domínio posterior exige processo
próprio; não importar massa HML nem inferir dados nesta M0.

## Checkpoint C — validação local

Ver `tests/test_m0_baseline.py`: bootstrap em novo banco PG18 por execução,
comparação catálogo × snapshot (tipos, ordem, nullability, defaults, constraints,
índices, views, sequences/propriedade), domínio inicialmente vazio, segunda
execução idempotente, recusa schema não vazio, Models × catálogo, joins legados,
router alimentacao e leitura Neuro dos três campos de respostas.

As fixtures antigas que criavam `observacoes` manualmente agora recebem a coluna
do Model; somente os quatro snapshots continuam adicionados nessas fixtures.
Nenhuma fixture passou a fabricar campos estruturados Cardio.

Resultados e comandos executados estão registrados na seção de validação local abaixo.

## Checkpoint D — adoção HML concluída (D.1–D.4)

### D.1 — equivalência estrutural aprovada

O confronto TC-02 + D.1 + comprovação final de whatsapp_mensagens confirmou o
contrato canônico. Nenhum drift material não classificado permaneceu nas evidências.
A seção vazia de constraints da primeira coleta D.1 não foi interpretada como
PK ausente; a evidência posterior por psql comprovou `whatsapp_mensagens_pkey`
PRIMARY KEY, btree(message_id), e fechou a pendência.

As quatro views permanecem fisicamente presentes:

| View | Estado aprovado |
|---|---|
| vw_dimensionamento_ocupacao | Consumidor ativo; preservação transitória |
| vw_demanda_capacidade | Consumidor ativo; preservação transitória |
| vw_dimensionamento_equipe | LEGADO ADICIONAL / PRESERVAÇÃO TRANSITÓRIA |
| vw_timeline_paciente | LEGADO ADICIONAL / PRESERVAÇÃO TRANSITÓRIA |

As duas últimas continuam classificadas EXTERNAL_CONSUMER_NOT_PROVABLE.
Sua presença adicional em HML não conflita com o conjunto canônico e não é
falha de equivalência. A instalação nova continua criando somente as duas views
incluídas no contrato congelado. **Decisão final: NÃO remover as views adicionais.**

### D.2 — configuração local e procedimento

Configuração canônica validada localmente por `heads`, `show m0_baseline_v1` e
ScriptDirectory: diretório correto, uma única base/head m0_baseline_v1.
Configuração histórica validada separadamente: head 8c01a0d1a004.

Procedimento aprovado: processo psql dedicado, ON_ERROR_STOP, identidade HML,
BEGIN, lock_timeout/statement_timeout, lock SHARE ROW EXCLUSIVE da tabela técnica,
exatamente uma revision 8c01a0d1a004, UPDATE condicionado com exatamente uma linha
retornada, leitura ainda na transação e COMMIT somente após todos os guards.
Erro antes do COMMIT interromperia o processo e encerraria a conexão com rollback.

### D.3 — backup/PITR e decisão humana de risco

Evidência humana do painel Recovery Render, serviço monitra-postgresql-hml:

- PITR disponível para os últimos três dias no momento do gate;
- export lógico completo concluído com indicador de sucesso em 23/09/2026,
  19:50, conforme horário exibido pelo painel, sem inferência de timezone;
- artefato .dir.tar.gz disponível para download;
- retenção informada de pelo menos sete dias;
- export anterior de 20/09/2026, 12:01, também disponível naquele momento;
- revision pré-adoção conhecida: 8c01a0d1a004.

O responsável humano aceitou essa combinação para a operação limitada à linha
técnica de versionamento. **Restore preventivo do novo export NÃO foi testado**
e foi expressamente dispensado para este gate. Não há alegação de teste de
restauração ou de verificação independente do painel pelo agente. As janelas de
retenção são evidência histórica do gate, não garantia de disponibilidade futura.

### D.4 — execução humana e validação pós-adoção

Identidade comprovada:

- database: monitra_postgresql_hml;
- user: monitra_postgresql_hml_user;
- schema: public;
- PostgreSQL: 18.4.

Adoção executada pelo operador:

`8c01a0d1a004 → UPDATE transacional controlado → m0_baseline_v1 → COMMIT`.

A leitura pós-COMMIT confirmou m0_baseline_v1, sem ERROR, FATAL, timeout ou
perda de conexão reportada. Em **nova conexão**, a consulta confirmou exatamente
uma linha em public.alembic_version com m0_baseline_v1 e as quatro views presentes.

O operador executou `alembic -c alembic-canonical.ini current` em container
descartável docker-api (Alembic 1.16.5), montando o worktree aprovado em /app e
fornecendo M0_DATABASE_URL exclusivamente ao processo. Resultado informado:

```text
m0_baseline_v1 (head)
```

Nenhum upgrade, stamp ou migration foi executado nessa validação. A adoção não
executou DDL, backfill, alteração de dados assistenciais ou remoção de views.
A única alteração HML foi o valor técnico de public.alembic_version.

### Supersessão explícita do plano pré-HML

As decisões D.1–D.4 substituem o plano preliminar deste documento:

- proposta anterior de DROP das duas views: **retirada**;
- equivalência exigindo ausência de legados adicionais: **substituída** pela
  equivalência do contrato canônico com preservação transitória dos adicionais;
- comprovação física pendente de whatsapp_mensagens: **concluída**;
- backup pendente: **aceito conforme decisão humana de risco D.3**;
- adoção pendente / WAITING_HML_RECONCILIATION_APPROVAL: **superado por M0_PASS**.

Não repetir adoção, bootstrap ou alteração de versionamento para “finalizar” M0.

## Operação Alembic após adoção

**Vigente: alembic-canonical.ini**, cadeia alembic_canonical, head m0_baseline_v1.
**Histórica: alembic.ini**, cadeia alembic/versions, preservada sem reescrita.

Próximas migrations devem nascer na cadeia canônica, inicialmente com
`down_revision = "m0_baseline_v1"`, mantendo um único head revisado:

```bash
python -m alembic -c alembic-canonical.ini revision -m "descricao"
```

Nenhuma revision nova foi criada por esta documentação. Autogenerate permanece
não habilitado sobre metadata parcial/legada; migrations são explícitas/revisadas.

Banco NOVO, public vazio, com URL explicitamente configurada:

```bash
python -m alembic -c alembic-canonical.ini upgrade head
```

**É proibido executar novamente o bootstrap sobre HML existente.** O HML já
reconhece m0_baseline_v1; evoluções futuras autorizadas executam apenas revisions
descendentes usando a configuração canônica. Não usar a configuração histórica,
comandos sem `-c` explícito, stamp ou retorno a base como atalhos no HML adotado.
A mudança de versionamento não demonstra que todos os jobs externos tenham sido
reconfigurados; a seleção correta da configuração é requisito operacional permanente.

## Riscos residuais e limites

- Consumidores externos das duas views adicionais não foram comprovados ausentes;
  views preservadas, sem remoção autorizada.
- CRUD legado capacidade_instalada continua dependente de tabela ausente; a M0
  não cria capacidade artificial nem remove seu consumidor.
- Colunas e relações legadas transitórias permanecem nos limites aprovados.
- Restore preventivo não testado, conforme aceitação humana específica.
- Evitar mistura das duas cadeias; o histórico não reconhece a revision canônica.
- Falha de conexão após COMMIT exige verificar estado antes de repetir operações.
- Reversão técnica da adoção, se futuramente autorizada e sem migrations posteriores,
  limita-se ao versionamento anterior com os mesmos guards. Não há views a restaurar.
  Com evoluções posteriores, exige novo plano; não executar downgrade do bootstrap.
- Baseline estrutural não clona dados, permissões de infraestrutura ou massa HML.

Próximo gate na sequência: G1, **não iniciado e dependente de autorização específica**.

## Validação local executada e aprovada (Checkpoints A–C)

- PostgreSQL dedicado: container `integra-wave5-m0-validation`, imagem postgres:18,
  porta local 55613. Nenhum container/banco de aplicação existente foi usado.
- Bootstrap: `python -m alembic -c alembic-canonical.ini upgrade head` com
  M0_DATABASE_URL apontando exclusivamente para localhost:55613/m0_baseline: PASS.
- Python 3.9: `compile(Path(file).read_text(), file, 'exec')` nos 23 arquivos
  Python alterados/novos: PASS, sem escrever bytecode no repositório.
- Focado: `python -m unittest discover -s tests -p test_m0_baseline.py -v`:
  10 PASS, zero skips (última execução 2.053s, após fixar version_table_schema=public).
- Completo: `python -m unittest discover -s tests -v`, Python 3.9 em container
  docker-api, código montado :ro, PostgreSQL18 real: **380 PASS, zero skips**, 45.976s.
  Executado antes do último ajuste exclusivamente de version_table_schema;
  os 10 testes M0 foram repetidos e passaram depois dele. Nenhuma mudança funcional
  da aplicação após a suíte completa.
- Ambiente completo: REMEDIATION_POSTGRES_URL, CARDIO_GATE1_POSTGRES_URL,
  CARDIO_GATE3_POSTGRES_URL, CARDIO_GATE4_POSTGRES_URL,
  WHATSAPP_TEST_POSTGRES_URL, CARE_PLAN_TEST_POSTGRES_URL e
  SESSION_TEST_POSTGRES_URL = `postgresql+psycopg2://gate1@127.0.0.1/gate1_test`;
  WAVE3_TEST_POSTGRES_URL = `postgresql+psycopg2://wave3@127.0.0.1/wave3_test`;
  WAVE5_TEST_POSTGRES_URL = `postgresql+psycopg2://wave5@127.0.0.1/wave5_test`.
  Todos localhost **dentro da rede do container M0**, não PostgreSQL do host.
  M0_TEST_POSTGRES_URL usa role m0_test e banco m0_baseline nesse mesmo container.
  DATABASE_URL=sqlite:// para imports; PYTHONDONTWRITEBYTECODE=1.
- Foram instalados httpx 0.28.1 e pypdf 6.19.0 somente no runtime temporário.
  Não houve alteração de requirements. Role sintético gate1 recebeu exclusivamente
  GRANT SET ON PARAMETER deadlock_timeout para a regressão existente.
- Primeira execução completa: 379 testes, 2 erros ambientais (pypdf ausente e
  permissão deadlock_timeout). Não foi contada como PASS; ambos corrigidos no
  ambiente isolado antes da execução de 380 acima.
- Comparação intermediária ORM/catálogo identificou índices de avaliações e
  diagnóstico ausentes do Model: declarações completadas e comparação final PASS.
- Heads por leitura: `python -m alembic heads` -> 8c01a0d1a004;
  `python -m alembic -c alembic-canonical.ini heads` -> m0_baseline_v1.
- Neuro engine, Cardio engine e providers ClinicalReading comparados byte a byte
  com HEAD: idênticos. Sem diff em app/services, app/routers, app/schemas ou
  alembic histórico. Regressões Neuro caracterizadas incluídas na suíte completa.
- Budget de consultas preservado: composição longitudinal 14/14 consultas para
  3/53 pacientes; Cockpit profissional Neuro14/Cardio16 antes/depois de +50.
- `git diff --check`: PASS. Sem staging/commit/push.
- Evidência integral fora do repo: `/private/tmp/integra-wave5-m0-final-tests.log`.

### Estado Git do checkpoint local, ainda sem commit

HEAD 7051b8b12293d18fd9b2f8692a4e86cc80985968, detached.
20 arquivos existentes modificados + 7 arquivos novos (27 no total).
Frontend limpo em 2fc1c9fe785b95599e9592a9063b9db84d374778.
Worktrees anteriores não foram editados/removidos nem suas refs alteradas;
entradas antigas prunable foram preservadas.

Arquivos existentes alterados:

- `app/models/agenda_cuidado.py`
- `app/models/atividade_terapeutica.py`
- `app/models/avaliacao_clinica.py`
- `app/models/diagnostico.py`
- `app/models/modular.py`
- `app/models/paciente.py`
- `app/models/profissional.py`
- `app/models/profissional_modulo.py`
- `app/models/pts.py`
- `app/models/registro.py`
- `app/models/responsavel.py`
- `app/models/responsavel_paciente.py`
- `app/models/sessao_assistencial.py`
- `app/models/usuario.py`
- `app/models/whatsapp_conversa.py`
- `tests/fixtures/cardio_gate1_runtime.py`
- `tests/test_cardio_channels.py`
- `tests/test_cardio_longitudinal.py`
- `tests/test_daily_record.py`
- `tests/test_whatsapp_postgres.py`

Arquivos novos:

- `alembic-canonical.ini`
- `alembic_canonical/baseline_v1.json`
- `alembic_canonical/env.py`
- `alembic_canonical/script.py.mako`
- `alembic_canonical/versions/m0_baseline_v1.py`
- `tests/test_m0_baseline.py`
- `docs/wave5-m0-baseline.md`

**STATUS FINAL: M0_PASS — aprovado após D.4.**

| Checkpoint | Resultado |
|---|---|
| A — inventário e decisões | PASS; consumidores e exceções classificados |
| B — ORM e desenho da baseline | PASS; cadeias separadas, sem G1 |
| C — bootstrap, catálogo e regressões | PASS; 10 testes M0, 380 testes completos, zero skips |
| D.1 — confronto físico final | PASS; whatsapp_mensagens comprovada, views preservadas |
| D.2 — preflight canônico | PASS; configuração e procedimento validados |
| D.3 — backup | Aceito por decisão humana; restore não testado |
| D.4 — adoção e pós-adoção | PASS; COMMIT, uma revision canônica, current=head, quatro views |

Este fechamento documental não cria branch, commit, push, deploy ou autorização G1.
