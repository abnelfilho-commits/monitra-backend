# Wave 5 — G2.B.1 — Vínculos institucionais canônicos

**STATUS FINAL: G2B1_HML_PASS**

Validação local previamente aprovada: `G2B1_LOCAL_PASS`.

## Escopo e decisões

Baseline Git: `c4f35d36a03501ef390d59caf6fbac87b53712ed`. Pessoa, papel humano, vínculo institucional, conta digital e autorização continuam separados. Instituição é explícita e não é inferida de clínica, CNPJ, nome ou coincidência de IDs. `clinica_id` e consumidores assistenciais permanecem legados e intactos. Responsável não recebe vínculo institucional; ADMIN global não precisa de vínculo humano.

`instituicao_papeis` descreve funções da organização. `paciente_instituicoes` descreve o vínculo temporal do Paciente; `profissional_instituicoes` descreve atuação temporal por ocupação; `paciente_profissionais` descreve a relação entre os dois contextos. Ocupação contextual não sincroniza `profissionais.ocupacao_id`. Taxonomia existente e política de identificador externo não mudam.

D1: `paciente_profissionais.paciente_instituicao_id` é nullable fisicamente, sem default e sem backfill, com FK RESTRICT e índice B-tree não único. É obrigatório para CREATE canônico. `paciente_id` permanece preservado e deve coincidir com o paciente do vínculo explicitamente informado.

D2: diante de relação legada com contexto NULL, CLOSE/INVALIDATE do vínculo do paciente rejeita com `LEGACY_CONTEXT_UNRESOLVED` somente se coincidem paciente, instituição da atuação profissional, relação não invalidada e interseção com o período afetado. Não escolhe candidato, mesmo único. Para CLOSE o período afetado é posterior ao novo fim inclusivo; para INVALIDATE é toda a vigência original. Relações explícitas usam exclusivamente a nova FK. No lado profissional sempre se usa a FK profissional existente.

## Contrato físico incremental

Única revision nova: `g2b1_institucional_v1`, parent `g2a3_identidade_v1`. Migrations anteriores permanecem byte a byte intactas.

Além da coluna/FK/índice D1, cria `institucional_operacoes`, separada de `identidade_operacoes`:

- PK `id`;
- ator administrativo (`usuarios.id`) e instituição, obrigatórios;
- operação, tipo de alvo, resultado e motivo obrigatório não vazio;
- exatamente um dos três alvos FK: vínculo paciente, atuação profissional ou relação assistencial;
- estado anterior/final JSONB com chaves e estado do vínculo, sem copiar atributos pessoais de Pessoa ou credenciais;
- timestamp com timezone e default now(); índice de instituição;
- cinco FKs RESTRICT e CHECKs de alvo, operação/resultado e motivo.

Não há UPDATE/DELETE de legado, backfill, associação, Pessoa ou permissão criada pela migration. O preflight exige READ COMMITTED e rejeita objetos novos preexistentes. A FK nova nasce sobre coluna inteiramente NULL; nenhuma constraint nova é imposta aos valores das colunas históricas. EXCLUDEs G1 são preservadas.

Downgrade exige READ COMMITTED, locks exclusivos e ausência tanto de proveniência quanto de referência canônica não-NULL. Havendo qualquer informação canônica, aborta antes de remover objetos. Sem informação canônica, remove somente os objetos G2.B.1 e preserva linhas históricas. Não foi executado em HML.

## Serviço interno

`InstitucionalService` oferece CREATE, GET/LIST, CLOSE e INVALIDATE para os três vínculos. Nenhum router novo foi criado. Mutações exigem ator Usuario ADMIN ativo existente e motivo explícito, seguindo a fronteira administrativa atual; não criam conta ou autorização. GET/LIST também exigem ADMIN; LIST exige instituição explícita.

CREATE rejeita campos extras e `ativo=false`. Relação assistencial exige os dois vínculos existentes, ativos administrativamente, paciente correspondente, mesma instituição e vigência integralmente contida em ambos. Fim NULL é aberto. Não é exigido que a vigência inclua hoje: períodos futuros/históricos continuam representáveis. Não se introduz política adicional por função institucional ou atividade do cadastro global do papel.

As chaves de conflito permanecem exatamente as dos EXCLUDEs G1:

- paciente + instituição + tipo de vínculo;
- profissional + instituição + ocupação;
- paciente + atuação profissional institucional.

CREATE idêntico retorna a mesma linha sem sobrescrita nem nova mutação/auditoria. Mesmo período com payload diferente conflita. Diferentes contextos de paciente não contornam a EXCLUDE G1 de relação assistencial. Linhas invalidadas continuam fora da EXCLUDE: CREATE explícito pode produzir nova linha válida, nunca reativar a anterior silenciosamente.

CLOSE registra fim explícito, mantém `ativo=true` e não reabre vínculos. Repetir o mesmo fim é idempotente; tentar trocar um fim já registrado retorna `CLOSE_CONFLICT`. Não há comando genérico de edição de período/chaves. Retorno usa CREATE de novo período. Com datas inclusivas, o retorno da mesma chave deve começar depois do último dia anterior.

INVALIDATE exige motivo e muda somente `ativo=false`. Repetição sobre linha já invalidada é idempotente. Dependentes válidos impedem invalidação; dependentes fora do novo fim impedem CLOSE. Nenhuma cascata. INVALIDATE não equivale a desligamento normal.

Estados apresentados pelo serviço, com data de referência explícita: VIGENTE, FUTURO, ENCERRADO e INVALIDADO. Encerrado mantém atividade administrativa; invalidado ignora a vigência.

## Transações e concorrência

Chamador mantém a transação externa e decide COMMIT/ROLLBACK. O serviço nunca faz commit. Session não pode conter alterações ORM pendentes ao iniciar operação. Cada mutação e sua auditoria usam o mesmo SAVEPOINT: inclusive falha após flush da auditoria reverte integralmente o comando.

Todas as mutações canônicas de vínculos adquirem o mesmo advisory lock transacional `572001` em READ COMMITTED. É uma serialização deliberadamente conservadora do domínio, incluindo CREATE de filho versus CLOSE/INVALIDATE do pai, com releitura de instâncias após lock. Reduz concorrência entre instituições, mas evita ordens divergentes de locks e snapshots obsoletos nesta fundação. Não há retry automático.

EXCLUDEs físicas continuam sendo proteção adicional. Somente SQLSTATE 23P01 com nome de uma das três EXCLUDEs G1 é traduzido para `PERIOD_CONFLICT`; falhas desconhecidas não são interpretadas como idempotência. FK/CHECK e outros erros físicos continuam falhando sem retorno de sucesso.

Invariantes de mesma instituição/paciente, contenção temporal, D2, auditoria e dependências são garantias do serviço canônico. Não são triggers universais para SQL/ORM arbitrário. Escritores externos que não utilizem o serviço não recebem essas garantias; consumidores clínicos não foram redirecionados para este domínio.

## Compatibilidade e regressões

As fixtures G1 que exercitam histórico continuam criando relações NULL diretamente pelo ORM para testar o contrato físico congelado. Seus testes de EXCLUDE não foram substituídos por SELECT-before-INSERT. Testes de encerramento usam ator/motivo e o serviço auditado; expectativa de head passa a G2.B.1. M0 distingue a nova tabela do catálogo histórico, validada nos testes específicos da nova migration.

Nenhuma alteração em ACL, authorized_line, autenticação, módulos, vínculos legados, responsável-paciente, identidade G2.A, CPF, WhatsApp, PTS, agenda, sessões, cockpit, timeline ou relatórios. Nenhum vínculo de ADMIN ou Responsável foi criado pelo domínio.

## Validação local

Ambiente: PostgreSQL 18 descartável `integra-g2b1-disposable`, sem rede externa. Runtime de testes compartilha apenas a rede desse container, com código montado read-only. Bases e dados exclusivamente sintéticos.

Os testes específicos cobrem catálogo, upgrade incremental e rollback, downgrade conservador, contextos explícitos, D2 positivo/negativo, vigências inclusivas/abertas, retorno, ocupações simultâneas, identidade compartilhada por papéis, auditabilidade, atomicidade e concorrência em transações distintas.

Resultado: **29 testes específicos PASS** (5,195 s) e **469 testes na suíte completa PASS, zero skips** (39,366 s). A primeira execução completa apontou somente a expectativa antiga de head em `test_pessoa.py`; foi atualizada para a nova revision sem alterar o contrato funcional de Pessoa, e a suíte integral foi repetida com sucesso. Cinco testes concorrentes incluem seis disputas reais: CREATE idêntico/conflitante, CLOSE idêntico/conflitante e CREATE de filho contra CLOSE/INVALIDATE de pai.

A migration tem SHA-256 `306a1aeba851527a3f2b5f9d470b0d291ca860f1a5acc5e2dc3de9da6c77f88f`. Bootstrap vazio até o novo head e caminho incremental foram confrontados pelos testes G1 de catálogos; os testes próprios também validaram legado NULL preservado, DDL rollback e downgrade bloqueado por informação canônica.

Inventário final: sete arquivos modificados e quatro novos:

- `app/models/__init__.py`
- `app/models/institucional.py`
- `app/models/institucional_operacao.py` (novo)
- `app/schemas/institucional.py`
- `app/services/institucional.py`
- `alembic_canonical/versions/g2b1_institucional_v1.py` (novo)
- `tests/test_institucional.py`
- `tests/test_m0_baseline.py`
- `tests/test_pessoa.py` (somente head/parent canônicos)
- `tests/test_vinculos_institucionais.py` (novo)
- `docs/wave5-g2b1-institucional.md` (novo)

Logs `/tmp/g2b1-test_vinculos_institucionais.py.log` e `/tmp/g2b1-full-suite.log`, runner e manifesto de integridade ficam fora do repositório. Migrations anteriores e demais arquivos protegidos conferidos contra o snapshot inicial. Na etapa local não houve acesso HML/PROD, commit, push, merge ou deploy. A implantação HML posteriormente autorizada e comprovada pela ponte humana está registrada abaixo; não autoriza avanço para G2.B.2/G2.C.

## Evidência operacional final HML

**G2B1_HML_PASS**, conforme evidência final fornecida pela ponte operacional humana. Preflight HML: **PASS**. A migration `g2a3_identidade_v1 → g2b1_institucional_v1` foi persistida em HML; resultado da execução humana: `exit_code=0`.

Hashes congelados dos artefatos utilizados. Executor e preflight permanecem fora do repositório; a migration integra o checkpoint:

- Executor utilizado: `wave5_g2b1_hml_execute.py`; SHA-256 `05ee5d0819d5af335b84821c4a68f2163def3ef9385314a8a904bb121d8ae02d`.
- Migration: `g2b1_institucional_v1.py`; SHA-256 `306a1aeba851527a3f2b5f9d470b0d291ca860f1a5acc5e2dc3de9da6c77f88f`.
- Preflight: SHA-256 `7cd05dd687a352b9649fdecfbf191c2878a48b84c79ce3b5ee51205d41f69749`.

Sequência operacional comprovada:

```text
TRANSACTIONAL_PREFLIGHT_PASS
→ PRECOMMIT_PASS
→ COMMIT_CONFIRMED
→ POST-COMMIT em nova conexão READ ONLY
→ POSTCHECK_ROLLBACK_CONFIRMED
→ G2B1_HML_EXECUTION_PASS
```

Resultado final: revision `g2b1_institucional_v1`, `provenance_columns=13`, `backfill=0`, `protected_structures=UNCHANGED`. O pós-COMMIT repetiu com sucesso os gates `POST_EXACT_ADDITIONS`, `PROTECTED_CATALOGUE_UNCHANGED` e `G2B1_VALIDATED`.

Nenhum backfill foi realizado; estruturas protegidas foram preservadas. O pós-check ocorreu em nova conexão read-only e o rollback dessa transação de inspeção foi confirmado. Não houve retry, downgrade, acesso PROD ou deploy de aplicação nesta etapa.

O fechamento documental preserva integralmente a implementação aprovada. Os resultados **469 PASS / zero skips / PostgreSQL 18 PASS** correspondem à validação local já aprovada e não foram repetidos neste checkpoint, cuja única alteração adicional foi documental. A serialização conservadora das mutações institucionais permanece como observação não bloqueante, sem otimização ou alteração contratual.
