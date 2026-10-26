# E14B.1 — Etapa 1: evidência de transporte, roteamento inalterado

Migration `e14b1_transporte`, filha de `d92e12c_autorizacao_whatsapp`.
Nenhum backfill de identidade, nenhum uso de context.id para resolver conversas,
nenhuma mudança na normalização, prioridade, questionários ou PARAR.
O índice uq_wcc_aberta_telefone permanece intacto.

## Contrato

whatsapp_mensagens_roteaveis possui unicidade por (phone_number_id, wamid),
destinatário solicitado, wa_id opcional, estado VALIDA/AUSENTE/INVALIDA,
origem META_CONVITE/META_RESPOSTA, instante de observação e exatamente uma FK
para conversa contextual ou legada. Dados de transporte são privados: não
são adicionados aos endpoints existentes ou logs.

VALIDA significa resposta Meta com um único contato, input exatamente igual ao
solicitado e wa_id numérico válido. Não significa identidade civil, consentimento,
autorização clínica ou prova de entrega. Contacts ausente/ambíguo/incompatível
não muda uma aceitação já válida; não conserva o valor inválido.

Convites continuam exigindo um único wamid inequívoco, conforme D9.2.
O transporte textual antigo sem wamid continua funcionando sem inventar evidência.
A captura não executa HTTP e não confirma transações internamente. Repetição da
mesma chave e conteúdo retorna a mesma linha; conteúdo conflitante falha fechado.

Recibos antigos permanecem com fingerprint v1 e resolução HISTORICO.
Novos recibos usam v2 (emissor, remetente, conteúdo, context.id opcional).
Contextos de encaminhamento sem id não são referências de resposta.
Context.id válido é persistido, mas deliberadamente ignorado na seleção.
CONTEXTUAL_ATUAL, LEGADO_ATUAL e LEGADO_SEM_CONVERSA descrevem apenas o caminho
atual. O hash v1 é usado ao conferir reentregas de recibos históricos, que não
podem comprovar um contexto que nunca foi conservado.

## Atomicidade e limitações

Convite: evidência é confirmada na transação de ACEITO; falha mantém o mecanismo
D9.2 de resultado incerto e não autoriza nova tentativa.
Resposta textual: a marca enviado_em é confirmada antes da persistência adicional.
Se a captura falhar depois, o webhook retorna falha, mas a reentrega não envia
novamente o texto já marcado. Pode haver uma lacuna de evidência, sem reconstrução
ou novo envio automático. O resultado externo não é transacional com PostgreSQL;
continua existindo a janela anterior de commit incerto do envio textual.

A etapa não promete roteamento multilinhas, não corrige 12/13 dígitos e não usa
as novas associações como concessão de acesso. Não reescreve dados históricos.
Migration deve preceder o novo código. Downgrade destrutivo é recusado.
Nenhuma migration ou publicação persistente é autorizada por estes testes.

## Validação local

Usar .venv-e12 e PostgreSQL 18 descartável, porta 55620, base m0_baseline.
M0_TEST_POSTGRES_URL e DATABASE_URL devem coincidir; não usar porta 55621.
As fixtures criam bancos próprios d92a_* ou equivalentes e os removem ao terminar.
Meta é simulada. Suíte nova: tests/test_whatsapp_transporte.py.
Suítes existentes: D9.2, manual, autorização, mental, segurança, template,
Neuro/Cardio. Teste da migration compara campos antigos dos recibos antes/depois.
