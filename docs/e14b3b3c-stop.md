# 3B.3C — PARAR no ingresso autenticado

## Gate e limites

Consulta Render somente leitura em 26/10/2026: `monitra-backend-hml`,
Auto-Deploy Off, último deployment Live `dep-dbfknf5g1s2s7386h13g`,
commit `9b4cee10ff9ac6170b14adc6919582525f76bd5b`. Lista atualizada sem
build/deploy em andamento. Baseline local homolog
`4afac48382759b6f46641a89a96914abcee49f61` limpa antes da implementação.

Sem deploy, envio real, alteração de configuração, migração persistente ou
ativação do resolvedor clínico geral. Nenhuma migration necessária; head
`e14b3b2_comunicacao`, índices de telefone e acompanhamento preservados.

## Contrato

O parser/HMAC/emissor permanece inalterado. `process_message` reconhece texto
`PARAR` (trim/case) antes de interpretar respostas clínicas ou menus. Somente
esse comando utiliza `whatsapp_stop`; demais mensagens mantêm os handlers
anteriores, com verificação da barreira antes de avançar respostas.

- Referência explícita Mental: chave exata emissor + wamid, prova do remetente,
  todas as evidências da conversa e vínculo institucional/assistencial atuais.
  Convite expirado/cancelado/concluído pode identificar um acompanhamento ainda
  ativo. Não se exige SIM ou E12C vigente para interromper comunicações.
- Sem referência: candidatos Mental e legado reunidos sem criar sessão, expirar
  conversa ou produzir efeito clínico. Só um acompanhamento Mental inequívoco
  recebe evento individual. Convites históricos do mesmo acompanhamento não são
  destinos diferentes; o recibo sem referência não atribui uma conversa arbitrária.
- Ambiguidade, ausência de vínculo, identidade conflitante, referência desconhecida
  ou Neuro/Cardio: barreira preventiva somente para emissor/remetente autenticado.
  Nenhum evento de Pessoa é fabricado. Não há fallback clínico.
- Evidência Meta é restrita ao emissor/conversa; não há heurística de identidade
  baseada no nono dígito. A chave conservadora existente serve apenas aos locks.

Acompanhamento clínico, autorização prévia E12C, consentimento individual,
respostas, expiração e PTS não são alterados pelo comando. Receptores clínicos
diretos recusam PARAR sem ingresso autenticado, em vez de executar revogação
legada. Mensagens explicativas não dizem mais que PARAR encerra acompanhamento.

## Persistência, auditoria e leitura

Reutiliza `whatsapp_comunicacao_eventos` (fonte da Timeline contextual),
`whatsapp_mensagens` e `whatsapp_resolucoes`. Uma transação grava recibo v2,
decisão sem telefone/texto/dado clínico e evento durável. Identificador da mensagem
é a chave idempotente; fingerprint divergente retorna conflito. Replay retorna o
resultado original, inclusive após reativação; recibos v1 continuam replayáveis.

Evento contextual: `COMUNICACAO_WHATSAPP_INTERROMPIDA`, origem WhatsApp,
autoria Pessoa pelo vínculo validado e referência auditável. Estado
`WHATSAPP_INTERROMPIDO` é consultável independentemente da Timeline. Contratos
existentes de leitura exigem capacidade contextual; Gestor/RH não recebe eventos
individuais. Não há Registro Diário/check-in, pontuação ou indicador artificial.

O retorno interno confirma a interrupção, mas não autoriza mensagem de resposta
externa depois da barreira. A reativação explícita registra o evento existente
`COMUNICACAO_WHATSAPP_REATIVADA`, exige evidência nova e não remove barreira
preventiva independente. SIM não reativa, não concede E12C nem avança check-in
bloqueado.

## Concorrência e limites

Plano completo antes de escrita: operação `ingress:<message_id>`, emissor e
conjunto de transporte, serializadores telefônicos compatíveis, identidade
institucional/Pessoa/contexto/paciente, acompanhamento/conversas ordenadas,
recibo/ledger/auditoria. Proposta reconstruída sob locks; se mudou, não há
atribuição clínica. Locks do Registro Diário (`FOR NO KEY UPDATE`) não mudam.

Preparação, interrupção, reativação e autorização de IO compartilham coordenação.
Interrupção confirmada bloqueia autorização posterior; uma chamada externa já
liberada pode terminar. Nenhuma transação permanece aberta por este comando
para HTTP; ele não executa HTTP. EM_EXECUCAO/INCERTO continuam sem retry automático.

Garantias são do conjunto de escritores canônicos. Escritas SQL externas e
alterações de evidência fora desses caminhos não são legitimadas por esta etapa.
Os testes concorrentes não constituem prova de ausência absoluta de deadlocks.
O índice global ainda limita conversas abertas simultâneas. Seleção clínica
multilinhas geral, navegação nova do resolvedor e remoção do índice aguardam
etapas posteriores.

## Validação

Meta simulada; PostgreSQL 18 descartável em bancos exclusivos criados pelos
runners de teste. Revisão canônica aplicada somente nesses bancos. Regressões
376 anteriores, com expectativas PARAR atualizadas para o novo contrato, mais
cenários de ingresso/interrupção. Resultados finais e contagens são registrados
no relatório da execução; logs intermediários com falha não são evidência PASS.


## Retomada E14B.1 — validação de 27/10/2026

Checkout recuperado: `monitra-backend-homolog-e12`, branch `homolog`, HEAD
`4afac48382759b6f46641a89a96914abcee49f61`. A pasta inicial
`neuro_mvp_backend` estava em `main`, com alterações de outro trabalho; foi
preservada. Status e diff foram inspecionados antes de qualquer edição.

Logs recuperados: primeira rodada focada com 141 PASS, 6 FAIL e 1 ERROR;
rodada posterior com 380 PASS, 0 FAIL e 3 ERROR em 383 testes.
As três correções posteriores já estavam salvas no checkout:

- Revogação sintética pelo comando público `register(..., revoke=True)`,
  com chave e auditoria exigidas por `ck_wac_comando_humano`.
- Retry após PARAR espera `WHATSAPP_INTERROMPIDO` e verifica ausência de HTTP;
  a tentativa anterior permanece `INCERTO`.
- Segundo acompanhamento Mental usa o contexto de outra instituição
  (`contexts[1]`), sem violar `ex_contexto_vigencia`.

Os três testes passaram na retomada. Não foi necessária nova alteração de
código ou testes; esta retomada apenas registrou a validação neste documento.
A implementação existente foi preservada, inclusive as expectativas atualizadas
para PARAR não encerrar acompanhamento, não revogar E12C e gerar bloqueio
preventivo quando não houver alvo inequívoco.

### Resultado por IDs distintos

| Matriz | PASS | FAIL | ERROR | SKIP |
| --- | ---: | ---: | ---: | ---: |
| Principal, com PARAR | 385 | 0 | 0 | 0 |
| PostgreSQL legado | 31 | 0 | 0 | 0 |
| Total distinto | 416 | 0 | 0 | 0 |

Comparação dos IDs com as três matrizes finais da 3B.3B: todos os **376**
IDs anteriores presentes, **40** novos, nenhum ausente ou contado duas vezes.
Logs e evidência de reconciliação:

- `/private/tmp/e14b3b3c-resume-full.log`
- `/private/tmp/e14b3b3c-resume-legacy.log`
- `/private/tmp/e14b3b3c-resume-evidence.json`
- `/private/tmp/e14b3b3c-baseline-ids.json`

### Evidência PostgreSQL e verificações

PostgreSQL **18.6**, container `integra-demo-e1b2-pg18` (`40d363b1f984`),
porta local `127.0.0.1:55620`. Migrações de teste executadas exclusivamente
em bancos descartáveis de propriedade dos runners. Ambas as rodadas terminaram
com `DATABASE_INVENTORY_PRESERVED True` e `NEW_DATABASES_REMAINING []`.

Passaram concorrência de replay/idempotência, PARAR versus preparação/envio/
reativação, revalidação sob locks, rollback, isolamento de Pessoa/instituição,
Timeline invisível antes do commit, HTTP fora de transação e não repetição de
resultado INCERTO. Meta simulada, sem envio real.

`test_indexes_preserved_and_head` confirmou `e14b3b2_comunicacao` e os índices
`uq_wcc_aberta_telefone` e `uq_wcc_aberta_acompanhamento`.
Nenhuma migration criada ou modificada; modelos sem alterações nesta etapa.
Sintaxe dos 12 arquivos Python modificados/novos aprovada e `git diff --check`
sem erros. Resolvedor multilinhas geral permanece inativo.

### Inventário final da 3B.3C

Modificados (10):

- `app/services/whatsapp_comunicacao.py`
- `app/services/whatsapp_conversation_service.py`
- `app/services/whatsapp_ingress.py`
- `app/services/whatsapp_mental.py`
- `app/services/whatsapp_referencia.py`
- `app/services/whatsapp_resposta.py`
- `tests/test_whatsapp_autorizacao.py`
- `tests/test_whatsapp_comunicacao.py`
- `tests/test_whatsapp_mental.py`
- `tests/test_whatsapp_referencia.py`

Novos, ainda não rastreados (3):

- `app/services/whatsapp_stop.py`
- `tests/test_whatsapp_stop.py`
- `docs/e14b3b3c-stop.md`

### Limites e estado de entrega

Permanece o aviso preexistente urllib3/LibreSSL 2.8.3. Uma chamada externa já
liberada antes de PARAR pode terminar; novas autorizações são bloqueadas.
Os testes não provam ausência universal de deadlocks contra escritores externos
que não compartilham os locks canônicos. Logs em `/private/tmp` são temporários.
O gate Render acima é a evidência anterior fornecida para a retomada, não uma
nova consulta ao ambiente remoto.

HEAD e branch preservados, alterações não staged. Nenhum commit, push, deploy,
migration persistente ou envio real. Etapa 3B.3D não iniciada.
Aguardando validação e autorização de consolidação.
