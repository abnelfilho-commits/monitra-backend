# E14B.1 — Etapa 3A: resolução multilinhas inativa

Baseline homolog: e4c69224772dce41c208f99245c5d6496bd3a5af.

## Interfaces privadas

`whatsapp_multilinhas.resolve(db, emitter, sender, content)` produz uma proposta
imutável: resultado, candidatos considerados, razões, IDs de evidências e seleção
única opcional. Não chama handlers, não envia respostas, não cria/expira conversas,
não confirma transações e não adquire locks. Recusa sessão ORM com alterações
pendentes; coleta sob no_autoflush. O chamador precisa de leitura consistente e
revalidação sob os locks da futura Etapa 3B antes de qualquer execução.

Resultados: UNICA, AMBIGUA, IDENTIDADE_RECUSADA, INDISPONIVEL, FALLBACK_SEGURO,
PARAR_REQUER_BLOQUEIO_3B. Ordenação por tipo/ID apenas estabiliza a auditoria;
nunca desempata candidatas. Resultado UNICA não é autorização de escrita.

`record_proposal` exige recibo v2 sem context.id, confere emissor e fingerprint,
serializa pelo recibo e registra a proposta em whatsapp_resolucoes. Não altera o
recibo original. Replay devolve a proposta anterior, mesmo após mudança de
estado. O chamador controla commit/rollback. Decisão antiga não dispensa
revalidação clínica; não pode ser executada automaticamente após mudança de
estado. Não há chamada a essas interfaces no ingresso atual nem flag de ativação.

## Identidade e elegibilidade

Evidência Meta é restrita ao mesmo emissor e conversa. wa_id precisa corresponder
exatamente ao remetente e input ao telefone da conversa. Respostas enviadas ao
wa_id são descobertas, mas não substituem a ponte original comprovada. Não há
heurística de nono dígito, normalização nova nem equivalência transitiva global.
Sem evidência, somente telefone exato. Evidência inválida/contraditória impede
seleção; não escolher a mais recente. Evidência histórica não reabre conversa.

Mental: estado e expiração, acompanhamento/contexto/paciente, instituição e
vínculo institucional vigentes, Pessoa ativa, linha e autorização prévia.
Neuro/Cardio: reutiliza os predicados canônicos de vínculo/linha extraídos para
eligible_lines, sem os locks do escritor. authorized_lines mantém seus locks e
comportamento. Exige responsável ativo, paciente ativo e vínculo, clínica
compatível, etapa reconhecida e data hoje/ontem quando preenchida. Evidência de
alias legado deve ter fingerprint do estado atual; linhas legadas são reutilizadas.

Duas candidatas elegíveis geram ambiguidade sem nomes, clínica, paciente ou
instituição na mensagem. SIM sem candidata não inicia conversa. Fallback é
somente uma proposta para responsável exato, único e vinculado, sem conversa
considerada, evidência relacionada ou acompanhamento conflitante. Não chama o
fallback antigo com heurísticas. Sessões legadas sem paciente selecionado e
históricos inconclusivos são recusados conservadoramente nesta subetapa.

PARAR sem referência retorna PARAR_REQUER_BLOQUEIO_3B sem executar qualquer
transição nem alegar que o bloqueio já ocorreu. A interrupção preventiva e o
PARAR contextual aprovado dependem da Etapa 3B. SIM não reativa autorização.

## Migration e preservação

Head novo e14b3a_multilinhas, filho de e14b2_referencia. Adiciona somente a tabela
whatsapp_resolucoes, vinculada por FK ao recibo, versão, JSON de IDs/razões e
horário. Trigger impede UPDATE/DELETE; downgrade destrutivo bloqueado. Não copia
telefone, texto recebido ou conteúdo clínico. Não altera recibos históricos.

uq_wcc_aberta_telefone e uq_wcc_aberta_acompanhamento permanecem intactos.
Ingresso, referência explícita, questionários, transporte e PARAR ativos não
foram alterados. Nenhuma migration persistente, mensagem, commit, push ou deploy.

## Dependências de 3B

- Harmonizar locks de entrada/preparação/envio/autorização antes da ativação.
- Revalidar candidatura e evidências após locks; não executar proposta obsoleta.
- Rever bloqueios globais de preparação e índice telefônico conjuntamente.
- Implementar interrupção preventiva sem contexto e interrupção contextual,
  sem encerramento clínico; verificar a barreira em todos os caminhos de envio.
- Integrar recibo, proposta e transição em uma transação; preservar replay v1/v2.
- Fallback futuro deve usar o responsável já validado, não repetir busca heurística.
- Definir continuidade segura de sessões de seleção de paciente sem antecipar
  autorização clínica. Não ativar o módulo enquanto essas dependências persistirem.

## Evidência de validação local

PostgreSQL 18.6 em 127.0.0.1:55620, recurso descartável identificado
integra-demo-e1b2-pg18. Fixtures criaram bancos UUID próprios; migrations até
head aplicadas somente nesses bancos. Remoção confirmada, inventário preservado.

- Matriz principal: 238 PASS, 0 FAIL, 0 ERROR, 0 SKIP.
- Neuro/Cardio PostgreSQL: 31 PASS, 0 FAIL, 0 ERROR, 0 SKIP.
- Baseline/M0: 10 PASS, 0 FAIL, 0 ERROR, 0 SKIP.
- Três contratos M0 são comuns às matrizes: 276 testes distintos, 35 novos.
- AST e git diff --check: PASS. Ingresso/referência/PARAR/índices preservados.

Logs locais: /private/tmp/e14b3a-validation-final.log,
/private/tmp/e14b3a-legacy.log e /private/tmp/e14b3a-baseline-final.log.
Rodadas intermediárias detectaram fixtures com identidade compartilhada,
catálogo/papel legado incompleto e expectativa de downgrade ainda sem o novo
head; corrigidas e revalidadas. A verificação inicial de inventário M0 coincidiu
com outros testes; foi repetida isoladamente com inventário preservado.
Warning existente urllib3/LibreSSL no Python local; sem chamadas HTTP externas.

Inventário: cinco novos arquivos (resolvedor, modelo de auditoria, migration,
testes e este documento); cinco modificados (registro de modelos,
whatsapp_daily_record e testes M0/persistência/Mental). Baseline Git preservada,
staging vazio; nenhuma consolidação Git autorizada nesta etapa.
