# Wave 5 — G1: Fundação Institucional

Baseline: `b1b3863658f78620bf45ea1b63a395381b4de22a`, M0 aprovada.
Checkpoint A: conflito de autorização resolvido pela decisão humana complementar.
`alembic -c alembic-canonical.ini heads` confirmou `m0_baseline_v1` antes da edição.

## Fronteira aprovada

Vínculo institucional NÃO concede acesso clínico. Nenhum router público novo,
seletor institucional, backfill, sincronização ou conversão de autorização foi
introduzido. Serviços de domínio participam da transação do chamador (flush,
sem commit implícito); exposição HTTP depende do futuro gate de autorização.

## Inventário e convergência

| Estrutura | Produtores/consumidores atuais | Decisão G1 |
|---|---|---|
| clinicas | routers/clinicas.py; pacientes.py; profissionais.py; usuarios.py; responsaveis.py; cockpit_gestao_service.py | PRESERVAR_TRANSITORIAMENTE |
| clinica_id de usuário, paciente, profissional | core/acl.py; care_lines/access.py; patient_service.py; patient_line_service.py; session_service.py; cardio_longitudinal.py | PRESERVAR_TRANSITORIAMENTE; nenhuma ampliação de escopo |
| pacientes.profissional_id | routers/pacientes.py (criação/edição/serialização); cockpit_professional_composition.py; cockpit_gestao_service.py | PRESERVAR_TRANSITORIAMENTE; equipe canônica nova em paralelo, sem sincronização |
| vinculos / ProfissionalPaciente | models/vinculo.py; routers/vinculos.py; FK profissional_id aponta usuarios.id | PRESERVAR_TRANSITORIAMENTE; sem backfill por ausência de equivalência institucional/ocupacional/temporal |
| ocupacoes_profissionais | models/atividade_terapeutica.py; routers/atividades_terapeuticas.py; profissionais.py; care_plan_service.py | CONVERGE_G1 por reutilização do catálogo na FK dos novos vínculos |
| profissionais.ocupacao_id | profissionais.py; consumidores de elegibilidade/agenda | PRESERVAR_TRANSITORIAMENTE; não copiar automaticamente |
| PTS / agenda_cuidados / sessoes_assistenciais | care_plan_service.py; scheduling_service.py; session_service.py; assistential_session_service.py | FORA_DO_ESCOPO de redesenho; autorização e evidência histórica preservadas |
| módulos e paciente_modulos / profissional_modulos | care_lines/access.py; Cockpit; jornadas Neuro/Cardio | FORA_DO_ESCOPO; não limitar novos vínculos a uma Linha |
| ClinicalReading, engines, DailyRecord, WhatsApp, Report Engine | serviços institucionais existentes | FORA_DO_ESCOPO funcional; regressão obrigatória |

Nenhum legado classificado REMOVER_G1. Nenhum consumidor existente passa a ler
as relações novas como mecanismo de autorização ou como fonte clínica.

## Contrato físico

Migration `g1_institucional_v1`, parent `m0_baseline_v1`, somente na cadeia
`alembic-canonical.ini`. Cadeia histórica intacta.

- `instituicoes`: identidade serial, denominação obrigatória, nome fantasia e
  CNPJ opcionais, CNPJ único e normalizado, tipo validado, pai opcional RESTRICT,
  ativo e timestamps com timezone; CHECK contra self-parent.
- `instituicao_papeis`: FK RESTRICT, UNIQUE instituição/papel, enum por CHECK,
  ativo e criado_em. Uma instituição admite ambos os papéis.
- `paciente_instituicoes`: paciente/instituição/tipo, identificador externo
  opcional, intervalo e estado administrativo independentes.
- `profissional_instituicoes`: profissional/instituição/ocupação obrigatórios,
  permitindo ocupações e instituições simultâneas.
- `paciente_profissionais`: paciente e FK do vínculo profissional institucional;
  não duplica profissional/instituição/ocupação; não representa sessão.

As três tabelas temporais têm datas inclusivas, CHECK de ordem, FKs RESTRICT,
índices B-tree nas FKs e exclusão GiST de intervalos sobrepostos para a mesma
chave quando ativo=true. Sem duplicidade concorrente; encerramento permite novo
vínculo no dia seguinte ao fim. Inativo é administrativo e não substitui datas.
Nenhum DELETE em cascata apaga histórico.

Dependência técnica: extensão PostgreSQL `btree_gist` para igualdade dos tipos
inteiro/texto nas exclusion constraints. Migration cria se ausente; downgrade
não remove extensão compartilhável. PostgreSQL descartável é a prova estrutural;
SQLite não aplica as exclusões/regex e não constitui evidência deste gate.

CNPJ: 14 dígitos com verificadores validados no contrato de entrada do serviço;
sem herança do pai. Banco protege formato, unicidade e nullability. Ciclos
transitivos são rejeitados no serviço, serializando mutações hierárquicas por
advisory lock transacional antes da leitura em READ COMMITTED. Escritas diretas
que contornem esse serviço não são API de domínio autorizada.

## Operação e limites

- G1 não migra dados legados, nem inventa datas de início.
- A migration G1 foi aplicada em HML pela ponte operacional, com COMMIT e
  validação pós-COMMIT confirmados. Não repetir bootstrap, stamp ou migration.
  A revision aplicada é imutável; futuras evoluções exigem nova revision.
- Encerrar vínculo só atualiza data_fim; preserva pessoas e sessões.
- Vínculos de equipe não são automaticamente criados/encerrados por sessões,
  hierarquia ou outros vínculos.
- Futuro gate: Usuário × Instituição, permissões/contexto ativo, escopo e
  transição de clinica_id; explicitamente não implementado aqui.
- Nenhum commit/push/merge/deploy autorizado nesta execução.

## Validação

Resultado final: **G1_HML_EXECUTION_PASS**, conforme evidência da ponte
operacional humana. Estado HML: **g1_institucional_v1 (head)**.
Fechamento Git em preparação, ainda sem commit G1.

- Validação original: **390 PASS, zero skips**. Após a correção exclusivamente
  operacional do validador: **401 PASS, zero skips**, Python 3.9 em container
  efêmero e PostgreSQL 18 descartável; log `/private/tmp/g1-validator-full-suite.log`.
- Regressões operacionais do validador compartilhado: **11 PASS**; log
  `/private/tmp/g1-validator-focused.log`. Incluem NOT NULL ausente/trocada,
  constraint extra, CHECK removido, cada EXCLUDE removida, índice ausente,
  revision divergente, extensão ausente e views ausentes/alteradas.
- Dez regressões G1: PASS; repetidas após reforçar a comparação física de tipos,
  nullability, PK, FK, CHECK e UNIQUE com o ORM. Log
  `/private/tmp/g1-focused-final.log`.
- Cenário A: banco vazio → M0 → G1, PASS.
- Cenário B: banco M0 → G1, PASS. Catálogos finais iguais (tipos com precisão,
  defaults/nullability, PK/FK/UNIQUE/CHECK/exclusion, índices e sequences).
- Head único: `g1_institucional_v1`; parent: `m0_baseline_v1`.
- M0 permanece validada isoladamente na revision original; testes de catálogo
  congelado não confundem as cinco entidades posteriores com a baseline M0.
- Concorrência: exclusão de vínculo duplicado e prevenção de ciclo hierárquico
  comprovadas com conexões concorrentes reais.
- Segurança: usuário continua recebendo 404 para paciente de outra clínica,
  antes e depois de criar vínculos institucionais/equipe novos.
- Regressões existentes Neuro/Cardio, DailyRecord/WhatsApp, PTS/Agenda/Sessões,
  Cockpit, isolamento, consultas em lote e Report Engine/PDF: PASS.
- Diff de engines/providers/routers/ACL/Report Engine e baseline M0: vazio.
- Nenhum teste SQLite é usado como prova do gate estrutural PostgreSQL.

Ocorrências resolvidas no ambiente de teste: primeira execução recusou URLs
que não eram as fixtures locais permitidas; uma execução posterior foi
interrompida por lock mantido pela preparação do próprio teste concorrente.
Foram corrigidas a configuração descartável e a fixture, sem mascarar erros
nem modificar regras clínicas. A execução final acima terminou com sucesso.

## Histórico operacional HML — evidência humana

1. Preflight read-only confirmou PostgreSQL 18.4, database
   `monitra_postgresql_hml`, usuário `monitra_postgresql_hml_user`, schema
   `public`, revision única `m0_baseline_v1`, cinco tabelas G1 ausentes e
   dependências físicas compatíveis. `btree_gist` 1.8 disponível e trusted.
2. Backup pré-G1: export lógico de 24/09/2026 às 13:42 (horário exibido pelo
   Render), artefato `.dir.tar.gz` disponível e PITR de três dias. Restore
   preventivo não testado; risco aceito pelo responsável especificamente
   para este gate. Não se afirma validade temporal para operações futuras.
3. Primeira tentativa abortou antes do COMMIT: **VALIDATOR_DEFECT**. PostgreSQL
   18 registra NOT NULL em `pg_constraint` com `contype='n'`; o executor
   contava essas entradas, mas não as incluía no contrato esperado.
   Não foi falha da migration nem do contrato institucional.
4. Nova conexão read-only comprovou rollback integral: revision
   `m0_baseline_v1`, `btree_gist` ausente e cinco tabelas G1 ausentes.
5. Correção exclusivamente operacional: `scripts/g1_hml_validation.py`,
   compartilhado pelo executor e testes, inclui `n` e valida as colunas exatas
   em `pg_constraint` e `pg_attribute.attnotnull`. Divergências registram
   EXPECTED × ACTUAL antes do abort, sem credenciais, mantendo fail closed.
   Contagens NOT NULL: 6 / 5 / 8 / 8 / 7 nas cinco tabelas, respectivamente.
6. Foram adicionadas 11 regressões operacionais; suíte final 401 PASS,
   zero skips. Os 231 arquivos protegidos permaneceram idênticos, incluindo
   migration, ORM, schemas, serviço de domínio, M0 e regras clínicas.
7. Segunda execução: `m0_baseline_v1 → g1_institucional_v1`, validação
   pré-COMMIT PASS, COMMIT concluído e validação pós-COMMIT em nova conexão
   PASS, conforme confirmação da ponte operacional.
8. Verificação independente com Alembic canônico confirmou
   **g1_institucional_v1 (head)**. As quatro views foram preservadas pelas
   validações aprovadas. Nenhuma nova operação HML ocorre neste fechamento.

## Checkpoint Git proposto

- Parent: `b1b3863658f78620bf45ea1b63a395381b4de22a` (checkpoint M0).
- Branch proposta, ainda não criada: `codex/wave5-g1-institucional`.
- Um único commit proposto: `feat(db): establish G1 institutional foundation`.
- Escopo: dez arquivos G1 (dois modificados e oito novos), incluindo o
  validador operacional compartilhado e suas regressões.
- `/tmp/wave5_g1_hml_execute.py` e logs em `/private/tmp` são artefatos
  operacionais temporários; não integram o checkpoint.
- Promoção posterior para backend `homolog` exige autorização separada,
  fetch/ancestralidade e fast-forward quando possível; parar em divergência.
- A autorização multi-institucional continua fora deste gate. Sem G2,
  endpoints novos, backfill ou sincronização automática.

Migration aplicada, preservada sem edição:
`alembic_canonical/versions/g1_institucional_v1.py`

SHA-256: `3e0d88f99562c9e5c984f6651809523f3de35946dc2cbcd305bf47e3ef04b767`.

Nesta preparação apenas este documento foi atualizado. Evidências aprovadas
(401 testes / 11 operacionais / 10 G1) foram conferidas, sem reexecução da suíte
ou acesso HML; nenhum código mudou desde essa validação.
