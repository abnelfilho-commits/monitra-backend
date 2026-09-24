# Wave 5 — G2.A.3 — Identidade canônica e proveniência

**STATUS: G2A3_HML_PASS**

Estado final consolidado conforme evidência operacional aprovada pela ponte humana.

## Fronteira aprovada

Pessoa é a identidade humana canônica. Paciente, Profissional e Responsável são papéis humanos. Usuario é conta/identidade digital, não um papel humano. Nenhuma dessas associações concede acesso, clínica, módulo ou vínculo institucional.

O bypass clínico de ADMIN continua sendo legado conhecido, sem ampliação. A invariante de destino “ADMIN não é superusuário clínico” será realizada em G2.C e não é critério comportamental deste gate. Contexto institucional permanece em G2.B; autorização/provisionamento permanece em G2.C.

## Contrato e migration

`g2a3_identidade_v1` descende exclusivamente de `g2a2_pessoas_v1`. M0, G1 e G2.A.2 permanecem imutáveis.

As quatro tabelas `pacientes`, `profissionais`, `responsaveis` e `usuarios` recebem UNIQUE(pessoa_id), mantendo nullable, índices e FKs anteriores. Múltiplos NULL permanecem permitidos. O preflight da migration exige READ COMMITTED, bloqueia as quatro tabelas em ordem fixa e interrompe antes da DDL se houver duplicidade não-NULL. Não há merge automático ou backfill.

`identidade_operacoes` registra chave UUID idempotente, ator Usuario, tipo de operação, Pessoa, alvo de papel/conta, associação anterior, resultado, motivo, evidência explícita para regularização, requisição normalizada e data. Possui sete FKs RESTRICT e checks de tipo, resultado, alvo, conta, motivo e evidência. A requisição contém dados cadastrais, não credenciais: exige tratamento como dado pessoal e acesso administrativo. Não há rota para editar ou remover a trilha; isso não constitui proteção contra administrador direto do banco.

Downgrade exige READ COMMITTED e ausência de proveniência; não apaga trilha existente. Nenhum downgrade foi executado em HML. A migration foi aplicada com sucesso conforme a trilha operacional abaixo.

## Comandos administrativos

Prefixo `/admin/identidades`, usando a dependência ADMIN existente:

- POST `/localizar`: CPF validado no corpo, retorna somente cadastro canônico.
- POST `/pessoas`: localizar/criar Pessoa com CPF obrigatório, válido e normalizado.
- POST `/papeis`: criar/reutilizar papel humano.
- POST `/associacoes/papeis-legados`: associação explícita de registro legado.
- POST `/associacoes/contas-legadas`: associação explícita de Usuario existente.
- GET `/operacoes/{chave}`: recuperar resultado operacional.

Não há criação de Usuario. Novos Paciente/Profissional nascem inativos e sem clínica, módulos ou vínculos. Responsável existente pode ser reutilizado/associado; novo Responsável retorna `ROLE_CREATION_UNAVAILABLE_THIS_PHASE` porque seu legado acopla credenciais. Nenhuma senha, hash ou e-mail artificial é fabricado pela implementação.

A associação de conta preserva id, login, hash, perfil, estado, clínica, profissional_id e demais relações. A associação de papel preserva seus campos legados e altera somente pessoa_id. Contexto explicitamente informado incompatível causa `INSTITUTIONAL_CONTEXT_PENDING`; criar papel com contexto institucional também é indisponível neste gate. Nenhum contexto é inferido.

## Conflitos, idempotência e concorrência

CPF identifica a busca explícita comandada pelo administrador, nunca reconciliação automática de legado. Nome, nascimento, contatos e coincidências numéricas não produzem associação. Nova Pessoa exige CPF; CPF físico continua nullable para preservar legado. Não existe rota genérica de atualização cadastral; alteração de CPF pelo serviço Pessoa também é rejeitada neste gate.

Reutilização compara atributos explicitamente fornecidos, sem sobrescrever divergências. Regularização exige registro explícito, motivo, evidência e reconhecimento exato das diferenças de nome/nascimento existentes. Campos operacionais de autenticação/WhatsApp não são sincronizados. Reatribuição a outra Pessoa e duplicação de papel são rejeitadas.

Chave idempotente é serializada por advisory lock transacional. Mesmo ator/comando retorna o resultado original; payload ou ator diferente é conflito. CPF UNIQUE é proteção final: somente SQLSTATE 23505 com constraint `uq_pessoas_cpf` permite reler a Pessoa vencedora após savepoint. Outros IntegrityError não são interpretados como identidade existente. Locks de Pessoa e alvo legado protegem associação/reutilização; UNIQUE dos quatro domínios protege cardinalidade. Session atualiza instâncias após adquirir lock para evitar estado previamente carregado obsoleto.

Pessoa, papel, associação e proveniência compartilham transação READ COMMITTED. O router faz COMMIT único ou ROLLBACK integral. Chamadores diretos do serviço devem fornecer Session limpa e assumir a mesma unidade transacional; o serviço não efetua commit.

## Compatibilidade

Endpoints legados, auth/tokens, ACL por clínica/Linha, responsavel_paciente, autoria histórica, Registro Diário, WhatsApp, PTS, Agenda, Sessões, Intervenções, Diagnósticos, Avaliações, ClinicalReading, Cockpit e Report Engine não migraram para pessoa_id. Nenhum vínculo de acesso é criado. As adaptações dos testes de M0/G1 distinguem contrato histórico congelado do novo head; não modificam migrations anteriores.

## Validação local

PostgreSQL 18 descartável, rede isolada, bases sintéticas exclusivas. Cobertura de bootstrap canônico, upgrade incremental, preflight com duplicidades e rollback, catálogo, CPF nullable físico, quatro UNIQUEs, sete FKs, ausência de backfill, evidência, conflitos, preservação de conta/papel e atomicidade. Concorrência real usa Sessions/transações distintas: mesmo CPF/papel, mesma chave e disputa por mesmo registro legado.

Resultado: **440 testes PASS, zero skips** (34,886 s), incluindo **20 testes específicos de identidade** (4 contratos unitários e 16 integração/PostgreSQL). As três regressões de concorrência real passaram. `git diff --check` e whitespace dos oito arquivos novos: PASS. Snapshot dos 400 arquivos versionados confirmou alterações somente nos 11 arquivos previamente autorizados; migrations anteriores e consumidores protegidos intactos.

As primeiras tentativas da suíte identificaram preparação incompleta do runtime descartável (`btree_gist` para fixtures legadas e dependência `pypdf`). Somente esse ambiente local foi completado; nenhuma correção clínica/de dependências versionadas foi necessária. A execução final passou integralmente. Log: `/tmp/g2a3-full-suite-final.log`, fora do commit. Nenhum acesso HML/PROD nesta etapa.

## Implantação e validação HML aprovadas

A evidência humana confirmou `exit_code=0`, `TRANSACTIONAL_PREFLIGHT_PASS`, quatro gates `*_INDEX` em `phase=PRE` e quatro em `phase=POST` aprovados. O evento `G2A3_VALIDATED` confirmou:

- revision `g2a3_identidade_v1`;
- proveniência com 16 colunas e sete FKs;
- quatro UNIQUEs de domínio;
- `people=0` e `associations=0`.

A sequência final foi `PRECOMMIT_PASS` → `COMMIT_CONFIRMED` → nova conexão `readonly=true` → validação pós-COMMIT completa → `POSTCHECK_ROLLBACK_CONFIRMED` → **`G2A3_HML_EXECUTION_PASS`**. O rollback final pertence à inspeção read-only; não desfaz a migration persistida.

Nenhum backfill, Pessoa artificial, associação automática ou credencial artificial foi criado. Paciente e Profissional podem existir sem conta digital. Proveniência, idempotência, concorrência e atomicidade mantêm o contrato local aprovado.

### Trilha operacional

1. A primeira tentativa abortou localmente, sem conexão ao banco, por bind mount incorreto dos metadados Git. A correção delimitou a variável com `${G2A3_GIT_COMMON}` no comando zsh; nenhuma implementação foi alterada.
2. Uma tentativa posterior executou a migration dentro da transação, mas o validador histórico rejeitou `pacientes_INDEX` antes do COMMIT. O rollback foi confirmado; não houve COMMIT nessa tentativa.
3. A causa foi **VALIDATOR_DEFECT**: o gate histórico exigia apenas o índice não único G2.A.2. A UNIQUE G2.A.3 cria legitimamente um segundo índice, único, preservando o anterior.
4. O executor v2 separou os contratos PRE/POST e conferiu propriedades e vínculo constraint–índice. A migration permaneceu byte a byte intacta.
5. As regressões operacionais em PostgreSQL 18 descartável passaram, incluindo rejeições de catálogo incorreto, validação pré-COMMIT completa e inspeção em nova conexão read-only. O executor v2 foi então executado em HML pela ponte humana, com o sucesso completo descrito acima.

Hashes preservados:

- Migration: `a1110869f39350a63a5b159266a35d5c1cbae9f3cb5966de0871f958f9075f8e`.
- Executor histórico: `a4c7edc97b8ddac14f2e83c25b5d69b1dc9efe5fcaf1a3ea3d7cc0d268323e4b`.
- Executor v2: `4723cc609329db33e4a2d5e05c6f7bc12d174dbb3ee55be9704c02333d3c5b6e`.

Executores, preflight, regressões operacionais temporárias e logs em `/tmp` são evidências operacionais e não integram o checkpoint do produto. Os 440 testes/zero skips e PostgreSQL 18 PASS são evidências previamente aprovadas; não foram repetidos nesta consolidação exclusivamente documental.

## Limites após o checkpoint

Não repetir a migration ou executar downgrade. A consolidação Git não autoriza push, merge, deploy, associação de legado ou concessão de acesso. G2.B/G2.C continuam sujeitos a decisão humana separada; nenhum próximo gate foi iniciado.
