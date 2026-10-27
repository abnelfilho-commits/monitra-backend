# E14B.1 — fechamento WhatsApp Saúde Mental v1

Base de revisão: `homolog`, `1d862162d87f8870473dd47695e84082029554f0`.
Este documento descreve a alteração local e o procedimento futuro. Nenhum comando
operacional deste procedimento foi executado em HML/PROD.

## Bloqueadores resolvidos

- O ingresso autenticado passa exclusivamente por PARAR ou pelo executor de
  seleção explícita. Não chama o dispatcher antigo por telefone; este agora
  recusa a execução. Referência desconhecida, identidade conflitante, evidência
  obsoleta e ambiguidade não selecionam outro contexto como alternativa.
- O menu legado novo exige responsável único, telefone exato e plano completo
  de pacientes autorizados, revalidado sob locks antes de criar a sessão.
  Sessões existentes são endereçadas por ID. Selecionar linha e retornar ao menu
  após conclusão preservam os fluxos Neuro/Cardio, sem mudar questionários.
- A preparação deixa de bloquear acompanhamentos distintos que compartilham
  telefone. Mantém serialização do transporte e unicidade por acompanhamento.
- Migration `e14b_close_v1`, descendente de `e14b3b2_comunicacao`, instala pausa
  persistente e barreira de protocolo antes de retirar a unicidade telefônica,
  na mesma transação PostgreSQL. Não migra, encerra ou exclui dados clínicos.

## Contratos preservados

PARAR precede qualquer handler clínico. Mental contextual interrompe comunicação,
não cuidado nem E12C; ambiguidade bloqueia preventivamente sem escolher Pessoa.
Neuro/Cardio não recebem encerramento assistencial. SIM não remove barreiras.
Reativação continua explícita e exige evidência nova. Recibo, decisão e efeitos
são confirmados juntos; falha do handler selecionado faz rollback integral.
Timeline mantém escopo, auditoria e idempotência existentes.

A seleção recusa contextos expirados/inativos sem mutação clínica. A preparação
continua expirando somente execuções do próprio acompanhamento. Isso substitui
os antigos testes que esperavam expiração/cancelamento pelo dispatcher telefônico.
Replays v1 mantêm a resposta histórica; não reexecutam seleção ou cuidado.

O índice `uq_wcc_aberta_acompanhamento` permanece único. O índice
`uq_wcc_aberta_telefone` é substituído por `ix_wcc_aberta_telefone`, parcial e
não único, com o mesmo predicado de status aberto. Os locks canônicos e
`FOR NO KEY UPDATE` não foram alterados.

## Pausa e compatibilidade

`whatsapp_runtime` contém uma linha com protocolo `e14b_close_v1` e `active=false`
na instalação. Ingresso textual (inclusive PARAR), preparação e autorização de
saída exigem a linha ativa. Ausência de tabela/linha falha fechada. A pausa causa
503 no webhook textual, sem recibo confirmado; o operador precisa considerar a
janela de retenção/reentrega do provedor. Callbacks de status continuam podendo
ser persistidos para reconciliação. Operações administrativas de cuidado/E12C
não são uma nova autorização para envio.

Cada transação ORM do novo binário marca localmente
`integra.whatsapp_protocol=e14b_close_v1`. Triggers recusam escritores sem marca
em 11 tabelas WhatsApp, inclusive operações sem linhas afetadas e TRUNCATE.
A marca não sobrevive ao commit/rollback e não deve ser configurada globalmente
no banco, role, pool ou string de conexão. SQL administrativo direto que escreva
nessas tabelas exige análise e marca transacional explícita; não desabilitar triggers.

A marca é uma barreira de compatibilidade, não autenticação contra alguém que
possua credenciais de banco. É obrigatório parar todas as instâncias antigas e
invalidar suas credenciais antes de ativar o novo ingresso. O runtime deve usar
role não proprietária e sem poderes DDL/superuser, com SELECT e UPDATE somente da coluna `id`
na tabela de controle (necessário ao `FOR SHARE`, sem permissão de alterar
`active`/`protocol` ou de DELETE); a role operacional separada administra a pausa. Revisar
heranças de roles para não conceder indiretamente escrita ou propriedade.

O lock compartilhado da linha de controle dura só a transação de autorização.
HTTP ocorre após commit, nunca sob uma transação aberta. Uma chamada já liberada
pode terminar depois de PARAR ou da pausa. Portanto a pausa SQL isolada não é uma
prova de drenagem: parar/drainar processos e reconciliar execuções em trânsito é
parte obrigatória do procedimento. PREPARADO, EM_EXECUCAO ou INCERTO não autorizam
retry automático, inclusive após reinício.

## Procedimento de publicação HML — somente após autorização

1. Revisar o diff, a migration e as evidências de teste; consolidar somente com
   autorização. Conferir branch/SHA aprovado, backup restaurável e schema atual
   `e14b3b2_comunicacao`. Confirmar Auto-Deploy Off por leitura e nenhum deployment
   em andamento. Não reutilizar a leitura Render de uma execução anterior.
2. Reservar janela de indisponibilidade e responsável pela recuperação. Suspender
   ingresso e disparadores/schedulers; parar e drenar todas as instâncias antigas,
   inclusive workers e jobs fora do serviço web. Inventariar convites e respostas
   PREPARADO/EM_EXECUCAO/INCERTO. Não reenviar para tentar descobrir o resultado.
3. Invalidar credenciais antigas, encerrar suas conexões e comprovar ausência de
   processos antigos capazes de acesso ao banco ou de HTTP já autorizado. Se não
   for possível demonstrar isso, interromper a publicação. Preparar credenciais
   exclusivas do novo binário com privilégios mínimos; não executar este corte
   como rolling deploy misturando versões.
4. Com role de migration e destino HML conferido fora de logs, executar
   `M0_DATABASE_URL=<segredo-HML> alembic -c alembic-canonical.ini upgrade e14b_close_v1`.
   A atribuição é ilustrativa: obter o segredo pelo mecanismo seguro do ambiente,
   sem colocá-lo em histórico de shell. Usar timeout operacional de lock e manter
   a pausa se a DDL não concluir. A migration é transacional, não concorrente.
5. Conferir revision, linha de controle pausada, os 11 triggers habilitados,
   índice único por acompanhamento e índice telefônico não único. Conferir
   contagens/dados pré/pós-migration. A role de runtime recebe `GRANT SELECT, UPDATE(id) ON whatsapp_runtime`
   (UPDATE da coluna id permite o lock de leitura; CHECK impede outro id),
   sem UPDATE de active/protocol nem DELETE, e privilégios necessários nas demais tabelas/sequências, sem
   capacidade de modificar o protocolo, desabilitar triggers ou executar DDL.
6. Publicar manualmente apenas o binário revisado, com ingresso/schedulers ainda
   suspensos. Conferir SHA efetivo e credenciais novas em todas as instâncias.
   Verificar que uma conexão sem marca não consegue escrever em tabela cercada,
   usando operação sem efeitos dentro de transação descartada, e que o webhook
   pausado não confirma mensagens. Não enviar WhatsApp real nesse smoke test.
7. Após liberação operacional, a role de controle executa:

   ```sql
   BEGIN;
   SET LOCAL lock_timeout = '5s';
   UPDATE whatsapp_runtime SET active=true
   WHERE id=1 AND protocol='e14b_close_v1';
   -- Exigir exatamente uma linha alterada.
   COMMIT;
   ```

   Liberar ingresso e os disparadores autorizados. Isso ativa infraestrutura,
   não concede E12C nem reativa comunicação interrompida. Acompanhar falhas de
   seleção, 503, bloqueios de protocolo e execuções incertas sem registrar PHI.

## Recuperação segura

Pausar com a mesma transação de controle, usando `active=false`; se houver timeout,
a pausa não foi comprovada. Suspender/drainar processos e saídas novamente.
Manter schema e barreira de protocolo. Corrigir para frente usando binário
compatível; validar e só então reativar. A migration recusa downgrade porque
podem existir conversas legítimas simultâneas com o mesmo telefone. Não remover
conversas/índices de proteção nem reativar binário antigo para forçar recuperação.
Restauro integral de backup é operação excepcional separada: requer autorização,
tratamento de mensagens posteriores ao backup e reconciliação de efeitos externos;
não fornece rollback de WhatsApp já enviado.

## Critérios para liberar E2E real

- Revisão e autorização explícitas de consolidação/publicação; SHA publicado
  confirmado, sem versões antigas, credenciais antigas inutilizáveis.
- Migration, privilégios e pausa/ativação verificados em HML; recuperação e
  reconciliação de incerteza com responsáveis definidos.
- E12C válida e contextual, identidade de transporte comprovada e destinatários
  de homologação autorizados. Não usar SIM como autorização ou reativação.
- Evidências locais aprovadas: seleção/referência e recusa segura, duas conversas
  no mesmo telefone, concorrência, isolamento, PARAR/Timeline, atomicidade,
  Neuro/Cardio e HTTP fora de transação, sem retry de INCERTO.
- Autorizar separadamente o envio real. Os testes locais usam transporte simulado
  e não comprovam credenciais, template aprovado ou entrega efetiva na Meta.

## Evidências locais

Execução final em PostgreSQL **18.6**, container local
`integra-demo-e1b2-pg18` (`40d363b1f984`), porta `127.0.0.1:55620`.
Transportes Meta simulados; migrations apenas em bancos descartáveis próprios.

| Matriz final executada | PASS | FAIL | ERROR | SKIP |
| --- | ---: | ---: | ---: | ---: |
| Principal, contratos e ativação | 411 | 0 | 0 | 0 |
| Legada PostgreSQL Neuro/Cardio | 31 | 0 | 0 | 0 |
| **Total de IDs distintos** | **442** | **0** | **0** | **0** |

Reconciliação dos IDs com os logs aprovados anteriores: **416/416 presentes**,
**26 novos**, nenhuma omissão ou duplicação. Os 416 anteriores foram executados
novamente, não apenas revisados. As rodadas intermediárias com falhas não são
contabilizadas como aprovação; seus problemas foram corrigidos e reexecutados.

Passaram concorrência de preparação por acompanhamentos distintos no mesmo
telefone, replay, criação única de menu, pausa versus transação, revalidação sob
locks, isolamento de Pessoa/instituição, PARAR/Timeline/E12C, rollback integral,
HTTP fora de transação e ausência de retry de INCERTO. Os novos testes também
comprovam bloqueio de escritores sem protocolo, marca transacional sem vazamento,
privilégios mínimos da role, migration pausada com preservação de linhas,
rollback do corte diante de índice de origem ausente e recusa de downgrade.

Ambas as matrizes terminaram com `DATABASE_INVENTORY_PRESERVED True` e
`NEW_DATABASES_REMAINING []`. A role NOLOGIN criada no teste de privilégios foi
removida pelo rollback, e sua ausência foi conferida.

Evidências locais (temporárias):

- `/private/tmp/e14b-close-full-final.log`
- `/private/tmp/e14b-close-legacy-final.log`
- `/private/tmp/e14b-close-evidence.json` — IDs e hashes dos logs.
- `/private/tmp/e14b-close-git-evidence.json` — inventário e hashes Python.

Sintaxe dos **22 arquivos Python** aprovada. `git diff --check` e verificação
integral de whitespace dos arquivos novos/modificados sem erros.
`FOR NO KEY UPDATE` e os arquivos de regras/questionários clínicos não mudaram.

Estado de entrega: branch `homolog`, HEAD
`1d862162d87f8870473dd47695e84082029554f0`, staging vazio, **18 modificados e
5 novos**, sem commit/push. Nenhum deploy, migration persistente, envio real ou
alteração Render/Meta. Não houve nova consulta ao Render nesta operação; seu
estado deverá ser conferido antes da publicação.

Riscos/pendências operacionais: validar corte de credenciais e ausência de
instâncias antigas em HML; drenar HTTP já autorizado; dimensionar a janela de DDL
com o volume real; autorizar e executar E2E Meta real. O aviso preexistente
urllib3/LibreSSL 2.8.3 continua presente no ambiente local. Os testes não provam
ausência universal de deadlocks com escritores externos aos locks canônicos.
Não há autorização de publicação implícita nestes resultados.

## Inventário da alteração

Modificados (18):

- `app/database.py`
- `app/models/whatsapp_contextual.py`
- `app/services/whatsapp_comunicacao.py`
- `app/services/whatsapp_conversation_service.py`
- `app/services/whatsapp_ingress.py`
- `app/services/whatsapp_mental.py`
- `app/services/whatsapp_selected.py`
- `tests/test_m0_baseline.py`
- `tests/test_whatsapp_comunicacao.py`
- `tests/test_whatsapp_convite_persistence.py`
- `tests/test_whatsapp_mental.py`
- `tests/test_whatsapp_multilinhas.py`
- `tests/test_whatsapp_postgres.py`
- `tests/test_whatsapp_preparation_locks.py`
- `tests/test_whatsapp_referencia.py`
- `tests/test_whatsapp_selected.py`
- `tests/test_whatsapp_stop.py`
- `tests/test_whatsapp_transporte.py`

Novos (5):

- `alembic_canonical/versions/e14b_close_v1.py`
- `app/services/whatsapp_runtime.py`
- `docs/e14b-whatsapp-fechamento.md`
- `tests/test_whatsapp_activation.py`
- `tests/whatsapp_runtime_fixture.py`

Os nomes dos métodos de teste anteriores foram preservados para reconciliar os
416 IDs da baseline. Expectativas que exigiam dispatcher telefônico, resolvedor
inativo, unicidade global ou mutação clínica durante recusa foram atualizadas
para o contrato autorizado neste fechamento; não foram removidos testes.

Para reproduzir: ambiente Python da aplicação com `PYTHONPATH=tests:.`, URL
`M0_TEST_POSTGRES_URL` de um servidor PostgreSQL local exclusivo de testes
(capaz de CREATE DATABASE), e `DATABASE_URL` apontando para o mesmo ambiente
sintético. As fixtures canônicas criam e removem seus bancos `d92a_*`. A matriz
legada exige `WHATSAPP_TEST_POSTGRES_URL` apontando para um banco **descartável**
`e14b_legacy_*` com `btree_gist`; nunca usar URL de HML/PROD. Ativação da fixture
recusa nomes que não pertençam aos prefixos descartáveis conhecidos. Os runners
da execução desta revisão, em `/private/tmp/e14b-close-full.py`,
`/private/tmp/e14b-close-focus.py` e `/private/tmp/e14b3b3c-resume-legacy.py`,
verificam container, porta, versão e inventário de bancos antes/depois. Logs e
runners temporários devem ser arquivados na revisão antes de limpezas do host.

Aguardando revisão e autorização de consolidação e publicação.
