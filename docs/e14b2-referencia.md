# E14B.1 — Etapa 2: referência explícita

Migration `e14b2_referencia`, filha de `e14b1_transporte`: adiciona motivo de
resolução aos recibos, amplia a constraint de decisões e adiciona impressão
de identidade/estado legado às novas evidências de transporte. Não altera evidências
ou recibos históricos. Migration deve preceder o código; downgrade destrutivo
continua bloqueado. Nenhuma aplicação em ambiente persistente nesta etapa.

## Decisão

- Com `context.id`: chave exata `(Phone Number ID, wamid)` no ledger de transporte.
- Sem referência: dispatch anterior, inclusive prioridades e PARAR, inalterado.
- `VALIDA`: remetente deve ser exatamente o wa_id retornado pela Meta.
- `AUSENTE`: somente igualdade exata com destinatário solicitado.
- `INVALIDA`: recusa. Nunca aplicar heurística de nono dígito neste caminho.
- Resposta enviada ao wa_id pode usar a ponte previamente registrada pela Meta,
  mas apenas para a mesma conversa e emissor. Não há associação global de pessoas.
- Desconhecida/incompatível/indisponível: resposta neutra única, decisão
  REFERENCIA_RECUSADA e motivo interno, sem FK selecionada e sem fallback.
- Válida: REFERENCIA_CONTEXTUAL ou REFERENCIA_LEGADA, FK específica no recibo.
  Não há escolha por maior ID, data ou linha de cuidado.

## Validação assistencial

Saúde Mental reutiliza locks canônicos e valida destino do acompanhamento,
identidade contextual, paciente, Pessoa, linha, estado e expires_at antes de
chamar receive. SIM, respostas e PARAR continuam nas funções existentes.
Referência vencida é recusada para respostas assistenciais. PARAR mantém a
regra canônica: uma conversa ainda aberta pode revogar o acompanhamento mesmo
após vencimento temporal, desde que a referência e identidade sejam válidas.
Conversa encerrada não é reaberta; nunca se redireciona para outro acompanhamento.
Sem referência, nenhuma mudança no tratamento anterior de PARAR.

Neuro/Cardio usa o responsável da conversa selecionada, sem buscar outro por
heurística. Revalida responsável ativo, telefone cadastrado normalizado por
formatação, vínculo, paciente ativo, clínica e linhas autorizadas pelo serviço
canônico. O handler recebe a conversa selecionada e não busca/cria outra.

O legado não tem expires_at nem identificador imutável de episódio: reutiliza
linhas. Por segurança, o recibo registra na transação clínica SHA-256 de ID, responsável, paciente, telefone,
linha, etapa, data de referência e updated_at. O resolvedor exige igualdade
integral; timestamp isolado não prova o episódio sob concorrência. Evidências
legadas antigas sem essa impressão são recusadas, sem backfill presumido.
A captura da resposta copia a impressão do recibo; não lê o estado posterior
à chamada HTTP, evitando associar a mensagem enviada a uma transição concorrente. INICIO não
é episódio assistencial aberto; datas de registro fora de hoje/ontem são
recusadas conforme contrato existente. Não se inventa janela universal de 24h.
Essa restrição pode recusar resposta a mensagem antiga após avanço legítimo;
responder à mensagem atual permite continuar. Evidências faltantes da Etapa 1
não são reconstruídas automaticamente.

## Concorrência e idempotência

Locks telefônicos em ordem determinística para remetente e destino conhecido;
locks clínicos/responsável/paciente e conversa antes de mutação. Recibo e
transição são confirmados na mesma transação. Replay retorna resposta original
sem reaplicar a transição. Fingerprint v2 vincula também context.id; v1 mantém
compatibilidade histórica. Recusa também é durável e idempotente. Nenhum
payload bruto, telefone ou conteúdo clínico adicional é exposto na resposta.

Índice uq_wcc_aberta_telefone preservado; normalização, cadastros, consentimentos,
questionários e seleção multilinhas de texto livre fora do escopo.

## Validação executada

PostgreSQL 18.6 local, porta 55620. Bancos novos com nomes UUID criados e
removidos pelos testes; Meta simulada, sem uso do PostgreSQL persistente DEMO,
HML ou PROD. Matriz final: 203 PASS; legado: 31 PASS; M0: 10 PASS.
Três testes M0 se repetem na matriz: 241 testes distintos, zero FAIL/ERROR/SKIP.
Uma rodada intermediária teve quatro falhas de snapshot por fixture carregada
antes da adição de coluna; a execução integral foi repetida com arquivos estáveis.
Sintaxe e git diff --check aprovados. Head único e14b2_referencia.

Logs locais finais:
- /private/tmp/e14b2-validated.log
- /private/tmp/e14b2-legacy-validated.log
- /private/tmp/e14b2-baseline-validated.log

## Inventário do diff da Etapa 2

Novos:
- alembic_canonical/versions/e14b2_referencia.py
- app/services/whatsapp_referencia.py
- tests/test_whatsapp_referencia.py
- docs/e14b2-referencia.md

Modificados:
- app/models/whatsapp_mensagem.py
- app/models/whatsapp_transporte.py
- app/services/whatsapp_conversation_service.py
- app/services/whatsapp_ingress.py
- app/services/whatsapp_transporte.py
- tests/test_m0_baseline.py
- tests/test_whatsapp_convite_persistence.py
- tests/test_whatsapp_mental.py
- tests/test_whatsapp_postgres.py
- tests/test_whatsapp_transporte.py

Nenhum commit, push, deploy ou aplicação de migration persistente nesta etapa.
