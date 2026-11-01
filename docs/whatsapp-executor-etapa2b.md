# Etapa 2B — executor semanal Mental

Implementação local sobre c1f02b65e0347b3fafd3a7bbfb46717ad445b446. Não publicada nem ativada.

## Ativação e autoridade

Duas condições independentes: `WHATSAPP_WEEKLY_EXECUTOR_ENABLED=true` no processo e último evento institucional habilitado. A variável é falsa por omissão; a migration não cria habilitações. O runtime E14B continua obrigatório para envio.

`whatsapp_executor_habilitacoes` é um ledger imutável. A ausência de evento ou último evento revogado desabilita a instituição. Cada evento identifica instituição, `EXECUTOR_SEMANAL_MENTAL`, decisão, autor humano da concessão/revogação, motivo e data. A autoria humana da concessão não é usada como credencial do executor.

`set_executor_grant()` é um comando interno explícito, sem endpoint público. Exige ADMIN ativo e instituição ativa, sob o serializador institucional existente. Reutiliza `AutorizacaoInstitucionalService.authorize()`, que reconhece ADMIN global sem exigir vínculo institucional redundante. Não habilita instituições automaticamente. Grants iguais são idempotentes; revogação e nova concessão produzem novos IDs, invalidando capacidades anteriores.

A identidade de execução é um objeto interno tipado com ocorrência, instituição, versão e ID da habilitação. Não aceita JWT humano, `actor=None` como autorização ou flag genérica. Cada preparação e ambas as revalidações do transporte verificam a evidência persistida; E12C, PARAR, runtime e elegibilidade mantêm seus controles. As APIs humanas continuam usando a autorização contextual existente. Conversas semanais não podem ser reenviadas pelo caminho humano de retry.

## Ciclo e concorrência

O lifespan FastAPI inicia o ciclo somente quando a chave global estiver ativa. A cada minuto, sem sobrepor ciclos no mesmo processo, seleciona até 20 candidatos e até 20 recuperações. Cada operação possui sessão própria; timeouts locais de locks (3s) e statements (15s) são reaplicados a cada transação. Em shutdown, deixa de assumir ocorrências e aguarda a operação atual. Uma finalização forçada continua segura pela persistência anterior ao HTTP.

Instâncias sobrepostas em deploy disputam os locks existentes de transporte, instituição/contexto e acompanhamento. O acompanhamento serializa configuração, claim e outras execuções; a ocorrência é travada após os locks de conversa, respeitando a ordem E14B. Claim e conversa são commitados juntos antes do transporte. Nenhum lock é mantido durante HTTP.

A seleção prioriza AGENDADO, programação ativa, versão vigente e atraso de 0 a 2 horas (inclusive). Ocorrências mais antigas são apenas classificadas PERDIDO, nunca enviadas. Não há reposição de semanas perdidas. Próximo envio deriva da próxima ocorrência AGENDADO da versão atual; não é deslocado por atraso do processamento.

## Estados e recuperação

- AGENDADO → PROCESSANDO: claim com conversa vinculada e início persistidos.
- AGENDADO → BLOQUEADO: inelegibilidade/revalidação negada; sem chamada Meta.
- AGENDADO → PERDIDO: atraso superior a duas horas; sem conversa criada.
- PROCESSANDO → EXECUTADO: tentativa ACEITO; significa aceitação Meta, nunca entrega ou conclusão clínica.
- PROCESSANDO → BLOQUEADO: tentativa REJEITADO comprovada.
- PROCESSANDO com motivo OUTCOME_UNCERTAIN: sem evidência conclusiva, inclusive interrupção após claim/preparação. Nunca reenviar automaticamente.

A recuperação somente lê tentativas existentes e registra resultados. Não chama prepare/deliver. Aceitação persistida antes de uma falha de atualização da agenda é reconciliada em ciclo posterior, mesmo após revogação institucional. Estados incertos permanecem bloqueados para reexecução; resolução operacional fica para avaliação explícita. Reconciliações repetidas não duplicam auditoria. A auditoria usa origem técnica e FK da ocorrência, com referência à habilitação no claim.

Há uma janela inevitável entre o último commit de autorização e o HTTP externo, já existente no transporte. Revogações persistidas antes da última verificação impedem envio; não é possível desfazer uma chamada já iniciada. Aceitação posterior à revogação é registrada honestamente sem reabrir estados clínicos.

## Migration e implantação futura (não executadas em HML)

`mh_executor_v1`, filha de `mh_agenda_v1`: uma tabela de habilitações, índice institucional, triggers E14B/imutabilidade e índice de seleção na agenda. Sem conversão, concessão, atualização clínica ou geração de ocorrências. Downgrade destrutivo é recusado.

A identidade runtime precisará somente de SELECT na nova tabela para executar. Escrita de concessões é administrativa e explícita; não conceder INSERT/UPDATE/DELETE ao executor. Validar ACLs separadamente antes de qualquer implantação, sem ampliar automaticamente permissões pela migration.

Nenhum novo serviço, fila, cron externo ou recurso pago. GETs passam a informar a habilitação global/institucional e o runtime ativo em `execucao_automatica_ativa`; programação pausada continua explicitamente indicada pelos campos de programação. O contrato extraordinário e sua idempotência permanecem separados da agenda.

## Validação

Testes usam PostgreSQL 18 descartável já existente, com bases sintéticas próprias e descarte ao final. HTTP real é proibido nos testes do executor; apenas a chamada Meta é simulada. Incluem migration/rollback, grants imutáveis, concorrência, tolerância, pausa/reprogramação, E12C/PARAR, revogação entre transações, aceitação/rejeição/incerteza, reinício e shutdown. Regressões cobrem agenda, manual, transporte e E2E Mental.

## Resultado local — 01/11/2026

- Regressão ampliada: 298 casos, inicialmente 297 aprovados e uma falha no teste histórico de downgrade, que ainda não reconhecia a nova revisão. Atualizado para verificar a recusa explícita e a preservação do schema.
- Verificação final: 26/26 aprovados, zero skips, incluindo executor, lifespan, migration, contratos e reexecução do teste de downgrade corrigido. Inclui indicador operacional adicional e timeouts finais por transação.
- Regressões de manual, E12C, comunicação, PARAR, agenda, preparação, transporte e persistência/E2E Mental aprovadas.
- Migration testada em PostgreSQL 18.6 descartável: aplicação, preservação de dados e rollback integral antes do commit.
- Sintaxe Python e `git diff --check`: PASS. Inventário dos bancos locais preservado, sem bancos de teste remanescentes.
- Nenhum acesso de escrita a HML/PROD, deploy, publicação, concessão institucional real ou chamada Meta real.
- HEAD permanece c1f02b65e0347b3fafd3a7bbfb46717ad445b446, branch homolog; alterações locais sem commit/push.

Arquivos alterados: `app/main.py`, `app/models/__init__.py`, `app/models/whatsapp_agenda.py`, `app/routers/whatsapp_mental.py`, `app/services/whatsapp_agenda.py`, `app/services/whatsapp_mental.py`, `app/services/whatsapp_convite_envio.py`, `alembic_canonical/versions/mh_executor_v1.py`, `tests/test_whatsapp_executor.py`, `tests/test_m0_baseline.py`, `tests/test_whatsapp_mental.py` e este relatório.

Antes de homologar: revisão/autorização explícita para publicar, aplicar migration, validar SELECT do runtime na tabela nova e, em etapa separada, habilitar instituição e chave global. Nenhum desses passos foi executado. Incertezas de envio continuam exigindo tratamento operacional explícito, sem retry automático.
