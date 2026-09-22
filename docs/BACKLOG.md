# Integra Care — Backlog Mestre

Baseline: 22/09/2026. Fonte oficial de pendências dos dois repositórios. Documento local ainda não commitado.

## Governança

“Todo achado relevante identificado durante uma Wave, Sprint ou Pacote que não pertença ao escopo corrente deve ser registrado no Backlog Mestre antes do encerramento da atividade.”

“Todo item tratado deve ter seu status atualizado no Backlog Mestre no mesmo pacote que o resolver, antes do encerramento.”

IDs são estáveis. Não renumerar por prioridade. Ao concluir, preservar item e registrar pacote, SHA completo, data e evidência de validação. Responsáveis e prazos não são presumidos. Prioridades são propostas de triagem, não autorização de execução. P0 bloqueador; P1 alta; P2 média; P3 baixa. REVISAR não afirma defeito aberto: exige confirmar situação atual. Nenhum achado crítico foi explorado ou corrigido.

O documento estratégico `integra-care-docs/roadmap/backlog.md` permanece roadmap, sem duplicar esta gestão. Ideias comerciais não são automaticamente pendências.

## Baselines e evidências

BE = monitra-backend, HEAD be377dab8f3dc1e023f3971a2b27512a96902100; FE = frontend, HEAD 13123a698f20ccd168c8503efda75ed82a5e7dd3. Caminhos/linhas referem-se a esses commits; FE pertence ao outro repositório. Inventário estático e documentação/conversa fornecida; sem testes, acesso HML ou comprovação de deployment nesta atividade. Ausência de chamador numa busca não prova código morto.

## Resumo

Total: 19 itens. Nenhum CONCLUÍDO sem registro de resolução próprio.

Status: ABERTO: 10; PLANEJADO: 1; EM EXECUÇÃO: 2; BLOQUEADO: 0; REVISAR: 6; CONCLUÍDO: 0.

Prioridade: P0: 1; P1: 1; P2: 14; P3: 3.

Área: Agenda/Sessões: 1; Cardio: 6; Cockpit Gestão: 1; Dados Demo: 2; Frontend compartilhado: 1; Neuro: 1; Performance: 1; Report Engine: 1; Segurança: 1; Tooling: 3; WhatsApp: 1.


## P0

### CARDIO-005 — Alinhar projeção do Registro Diário ao contrato físico

- **Área:** Cardio
- **Tipo:** DEFEITO
- **Status:** EM EXECUÇÃO
- **Prioridade:** P0
- **Origem:** Falha HML informada pelo usuário; auditoria estática em 22/09/2026, sem acesso HML/SQL.
- **Descrição:** Falha original: projeção física de campos estruturados causava UndefinedColumn para atividade_fisica. Correção local mantém esses campos somente em respostas_registro; snapshots e observacoes preservados conforme inventário físico fornecido pelo responsável. Fixtures deixaram de criar medições duplicadas.
- **Impacto:** POST Registro Diário Cardio retorna 500 e a transação padrão é revertida; bloqueia validação operacional E.1 e massa canônica.
- **Evidência:** app/services/daily_record/providers/cardio.py:15,48,61; app/services/daily_record/service.py:63; alembic/versions/26e0eeea73e1_base_modular_monitra.py:68; tests/test_daily_record.py:95; tests/fixtures/cardio_gate1_runtime.py:33.
- **Dependências:** Validação humana da correção e smoke HML posterior; contrato dos cinco campos físicos confirmado pelo responsável. DATA-002 acompanha drift; CARDIO-006 acompanha semântica histórica.
- **Critério de conclusão:** Criação/edição institucional funcionam no schema físico comprovado; campos clínicos e altura preservados em respostas_registro; ClinicalReading/Evolução usam a mesma observação; rollback integral comprovado; fixtures não inventam colunas para satisfazer código; Neuro preservado.
- **Pacote sugerido:** Correção delimitada do contrato de persistência Cardio.
- **Responsável:** A definir.
- **Data/prazo:** Identificado em 22/09/2026; prazo não definido.
- **Consumidor adicional confirmado:** app/routers/responsavel_cardio.py:listar_registros_cardio_responsavel consultava glicemia_jejum, pressões e peso físicos. Registrado antes da convergência para respostas da mesma observação; preservar snapshots, origem e autorização do APP.
- **Resolução:** Implementação local realizada; validação registrada em docs/cardio-005-implementation.md. EM EXECUÇÃO até aceite e validação operacional; sem commit/promoção neste pacote. Distinto de CARDIO-001 (antropometria) e CARDIO-002 (interpretações legadas).



## P1

### SEC-001 — Revisar autorização das leituras legadas

- **Área:** Segurança
- **Tipo:** SEGURANÇA
- **Status:** REVISAR
- **Prioridade:** P1
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Rotas examinadas não declaram ator no handler. Auditar dependências globais e ACL efetiva por clínica/Linha antes de concluir exposição; nenhuma sondagem remota realizada.
- **Impacto:** Potencial acesso fora do escopo institucional; explorabilidade não comprovada.
- **Evidência:** BE app/routers/timeline.py:54; BE app/routers/cardiometabolico.py:78,203; BE docs/multiline-wave-5.md:218
- **Dependências:** Revisão de segurança local; inventário de montagem das rotas
- **Critério de conclusão:** Testes anônimo/outra clínica/Linha não autorizada negados em todos os caminhos ativos; evidência de proteção ou correção.
- **Pacote sugerido:** Auditoria ACL legada
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.


## Pendências registradas — CARDIO-005

### DATA-002 — Reconciliação do schema físico HML × Alembic × Models

- **Área:** Dados Demo
- **Tipo:** DÍVIDA TÉCNICA
- **Status:** ABERTO
- **Prioridade:** P2
- **Evidência:** Inspeção HML fornecida pelo responsável: score_clinico numeric, risco/protocolo varchar, leitura_clinica/observacoes text; nullable, sem defaults. Ausentes do model/migration modular examinados.
- **Critério de conclusão:** Reconciliação explícita e validada do schema versionado com contrato físico; sem migration inferida no CARDIO-005.
- **Resolução:** Pendente; não implementado neste pacote.

### CARDIO-006 — Convergência futura do snapshot interpretativo longitudinal

- **Área:** Cardio
- **Tipo:** DÍVIDA TÉCNICA
- **Status:** ABERTO
- **Prioridade:** P2
- **Evidência:** RegistroAdapter consome leitura_clinica/protocolo do evento; app/scripts/recalcular_scores_cardio.py reescreve snapshots; app/services/cardiometabolico.py ainda referencia medições físicas (sem chamador encontrado na aplicação). Não executar o script nem considerar ausência de chamador prova de código morto.
- **Critério de conclusão:** Definir semântica histórica antes de convergir consumidores; não substituir evento passado por leitura atual. Inventariar usos externos dos helpers legados antes de remover dependências.
- **Resolução:** Pendente; snapshots preservados no CARDIO-005; distinto de CARDIO-002 (IMC e interpretações paralelas).

## P2

### CARDIO-001 — Contrato Peso kg / Altura m / IMC

- **Área:** Cardio
- **Tipo:** EVOLUÇÃO
- **Status:** EM EXECUÇÃO
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Implementar E.1: mesma observação, independência do label, captura de altura, labels explícitos e coerência cadastral. Implementação local E.1 realizada em 22/09/2026 no escopo cirúrgico autorizado: projeção kg/m, metadata ClinicalReading e captura profissional. Sem alteração cadastral ou metadados HML nesta etapa.
- **Impacto:** IMC indisponível com metadados atuais.
- **Evidência:** BE app/services/cardio_evolution.py:24; FE src/pages/cardiometabolico/RegistroDiarioCardiometabolico.jsx:331; decisão Pacote E.1
- **Dependências:** Validação humana da implementação local; confirmar fechamento do escopo cadastral/metadados do design anterior.
- **Critério de conclusão:** 80/2 → 20; 82/1.75 → 26.8; labels arbitrários não afetam cálculo; ausência/duplicidade seguras; cadastro não modifica histórico; risco e Neuro preservados.
- **Pacote sugerido:** E.1 — pacote imediato
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Evidência local em docs/cardio-001-e1-implementation.md. Sem commit; EM EXECUÇÃO até validação humana e encerramento explícito.

### CARDIO-002 — Convergir IMC e interpretações paralelas legadas

- **Área:** Cardio
- **Tipo:** DÍVIDA TÉCNICA
- **Status:** ABERTO
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Inventariar chamadas e convergir/remover cálculos paralelos de IMC; /alertas combina máximos históricos. Não promover labels clínicos legados a fonte canônica. Helper sem chamador encontrado não é prova de código morto.
- **Impacto:** Pode combinar observações distintas e divergir do contrato institucional.
- **Evidência:** BE app/routers/cardiometabolico.py:78; BE app/services/cardiometabolico.py:193; BE docs/multiline-wave-2.md:192
- **Dependências:** CARDIO-001; revisão clínica para efeitos nos alertas
- **Critério de conclusão:** Nenhum caminho ativo calcula IMC por combinação entre registros/cadastro; fonte única e regressões por consumidor; remoção somente após comprovação de uso.
- **Pacote sugerido:** Cardio — convergência legada
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### CARDIO-003 — Contrato dos booleanos do Registro Diário

- **Área:** Cardio
- **Tipo:** BUG
- **Status:** ABERTO
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Definir uso_medicacao/adesao_alimentar ponta a ponta. Schema aceita, router específico omite, provider direto rejeita; metadados HML fornecidos contêm ambos.
- **Impacto:** Entrada pode não ser persistida pelo canal específico.
- **Evidência:** BE app/schemas/cardiometabolico.py:28; BE app/routers/cardiometabolico.py:197; BE app/services/daily_record/providers/cardio.py:29
- **Dependências:** Decisão funcional dos campos
- **Critério de conclusão:** Campos têm contrato explícito de entrada/persistência/leitura e testes entre canais; sem alteração clínica implícita.
- **Pacote sugerido:** Registro Diário — booleanos
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### DATA-001 — Massa Canônica Cardio V1

- **Área:** Dados Demo
- **Tipo:** DADOS
- **Status:** PLANEJADO
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Planejar e posteriormente executar via contratos institucionais os seis casos: baixo+regular, moderado+atenção, alto+regular, crítico+regular, baixo+crítica e ID12 sem leitura. Massa congelada.
- **Impacto:** Demonstração HML ainda sem coorte canônica.
- **Evidência:** Decisão fornecida: Massa Canônica Fase 2; BE app/services/daily_record/service.py:16; BE app/routers/pacientes.py:196
- **Dependências:** CARDIO-001 validado; autorização HML; data âncora e plano de recuperação/idempotência
- **Critério de conclusão:** Coorte aprovada, autoria real, clínica2/Linha2, resultados verificados, nenhum toque Neuro/clínica1, IDs e evidências registrados; não alegar transação global das APIs.
- **Pacote sugerido:** Massa Canônica V1
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### UX-001 — Responsividade integrada do shell/sidebar

- **Área:** Frontend compartilhado
- **Tipo:** UX
- **Status:** ABERTO
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Diagnosticar shell fixo e corrigir experiência mobile integrada sem confundir com responsividade dos cards isolados.
- **Impacto:** Uso mobile prejudicado.
- **Evidência:** FE src/components/Layout.jsx:86,124; validação humana dos Pacotes A/Cardio V2
- **Dependências:** Escopo UX próprio
- **Critério de conclusão:** Jornadas integradas em 390/768/1280px sem obstrução; navegação e autorização preservadas.
- **Pacote sugerido:** UX shell mobile
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### ARCH-001 — Isolamento do Cockpit Gestão Multi-Line

- **Área:** Cockpit Gestão
- **Tipo:** ARQUITETURA
- **Status:** REVISAR
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Revisão futura explícita da Gestão; não transferir garantias do Cockpit Profissional para ADMIN/ADMIN_CLINICA.
- **Impacto:** Garantia de isolamento incompleta na evidência disponível.
- **Evidência:** BE docs/professional-cockpit-multiline.md:126
- **Dependências:** Diagnóstico do serviço/rotas Gestão
- **Critério de conclusão:** Matriz de acesso populacional por perfil/clínica/Linha comprovada; registrar se já resolvido.
- **Pacote sugerido:** Cockpit Gestão
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### REPORT-001 — Limitar aquisição histórica do Report Engine

- **Área:** Report Engine
- **Tipo:** DÍVIDA TÉCNICA
- **Status:** ABERTO
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Medir e limitar leitura das fontes antes do filtro de período, preservando semântica temporal.
- **Impacto:** Históricos grandes podem aumentar memória/latência apesar de ausência de N+1.
- **Evidência:** BE docs/cardio-v1-wave-4-checkpoint.md:182; BE app/services/report_engine/providers/timeline_provider.py:12
- **Dependências:** Benchmark sintético
- **Critério de conclusão:** Limites e plano de consultas comprovados com históricos grandes; conteúdo e período preservados.
- **Pacote sugerido:** Performance relatórios
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### WHATSAPP-001 — Comprovar prontidão operacional Meta

- **Área:** WhatsApp
- **Tipo:** DOCUMENTAÇÃO
- **Status:** REVISAR
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Gate local não comprova configuração/entrega real Meta. Verificar se validação operacional posterior já ocorreu antes de reabrir trabalho.
- **Impacto:** Liberação operacional sem evidência consolidada.
- **Evidência:** BE docs/cardio-v1-wave-2-checkpoint.md:191,194
- **Dependências:** Autorização específica para ambiente/canal
- **Critério de conclusão:** Registrar configuração sem segredos, teste operacional autorizado e evidências; ou vincular evidência já existente.
- **Pacote sugerido:** WhatsApp — gate operacional
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### AGENDA-001 — Recuperação entre atendimento e finalização

- **Área:** Agenda/Sessões
- **Tipo:** DÍVIDA TÉCNICA
- **Status:** REVISAR
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Confirmar fluxo atual de duas operações e UX de repetição da finalização após atendimento persistido; não presumir que continua sem recuperação.
- **Impacto:** Possível sucesso parcial e repetição indevida.
- **Evidência:** BE docs/multiline-wave-7.md:175; FE src/services/sessoesAssistenciais.js:36,45
- **Dependências:** Revisão da jornada atual
- **Critério de conclusão:** Falha na finalização é recuperável sem duplicar atendimento; teste integrado e evidência.
- **Pacote sugerido:** Sessões — recuperação
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### NEURO-001 — Conferir exclusão longitudinal pelo caminho legado

- **Área:** Neuro
- **Tipo:** BUG
- **Status:** REVISAR
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Documento registra exclusão Neuro apontando /registros/{id}; confirmar frontend atual e identidade do dado antes de corrigir ou marcar resolvido.
- **Impacto:** Possível incompatibilidade entre leitura e exclusão.
- **Evidência:** BE docs/multiline-wave-3.md:164
- **Dependências:** Rastrear jornada; não executar exclusão HML
- **Critério de conclusão:** Identidade/persistência corretas e teste de exclusão autorizado, ou evidência de retirada/resolução do caminho.
- **Pacote sugerido:** Neuro — integridade longitudinal
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### CARDIO-004 — Revisar narrativa clínica baseada em observação única

- **Área:** Cardio
- **Tipo:** EVOLUÇÃO
- **Status:** ABERTO
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Submeter vocabulário como hiperglicemia persistente/obesidade severa à validação clínica; não mudar thresholds nem narrativa sem aprovação.
- **Impacto:** Texto pode sugerir evidência longitudinal/diagnóstica além da entrada usada.
- **Evidência:** BE app/services/cardiometabolico_engine.py:109; BE docs/multiline-wave-4.md:107; BE docs/cardio-v1-wave-4-checkpoint.md:184
- **Dependências:** Validação clínica/produto
- **Critério de conclusão:** Semântica validada e caracterizada por testes; mudança ou aceitação documentada.
- **Pacote sugerido:** Revisão clínica Cardio
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### TECH-003 — Reavaliar latência HML Neuro

- **Área:** Performance
- **Tipo:** DÍVIDA TÉCNICA
- **Status:** REVISAR
- **Prioridade:** P2
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Recuperar relatório/medições do Pacote D e verificar resolução; sintoma reportado não prova causalidade do Cardio V2.
- **Impacto:** Carregamento Neuro relatado como prolongado.
- **Evidência:** Decisão/achado de governança: Pacote D — HML PERFORMANCE DIAGNOSIS; FE src/pages/dashboard/NeuroDashboard.jsx
- **Dependências:** Evidência HTTP autorizada; verificar gates posteriores
- **Critério de conclusão:** Waterfall e causa/mitigação comprovados ou evidência posterior de resolução; não aumentar timeout para mascarar.
- **Pacote sugerido:** Pacote D — acompanhamento
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.


## P3

### TECH-001 — Diagnosticar bundle frontend >500 kB

- **Área:** Tooling
- **Tipo:** DÍVIDA TÉCNICA
- **Status:** ABERTO
- **Prioridade:** P3
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Medir composição, transferência, carregamento e impacto; não prescrever code splitting antes do diagnóstico.
- **Impacto:** Aviso recorrente; impacto de performance não comprovado.
- **Evidência:** BE docs/cardio-v1-wave-4-checkpoint.md:126; BE docs/professional-cockpit-multiline.md:88; achado de governança
- **Dependências:** Baseline de build/medição
- **Critério de conclusão:** Causa e impacto medidos; solução ou aceitação fundamentada com evidência de build.
- **Pacote sugerido:** Performance frontend
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### TECH-002 — Depreciações Pydantic existentes

- **Área:** Tooling
- **Tipo:** DÍVIDA TÉCNICA
- **Status:** ABERTO
- **Prioridade:** P3
- **Origem:** Decisão/achado de governança do projeto; recuperação de código/documentação conforme evidência abaixo.
- **Descrição:** Tratar usos depreciados conforme versão suportada, sem atualização indiscriminada de dependências.
- **Impacto:** Warnings e risco de compatibilidade futura.
- **Evidência:** BE app/routers/pacientes.py:127; BE docs/cardio-v1-wave-4-checkpoint.md:185
- **Dependências:** Confirmar matriz Python/Pydantic
- **Critério de conclusão:** Warnings-alvo eliminados e schemas/serialização cobertos sem regressão.
- **Pacote sugerido:** Compatibilidade backend
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente; ao concluir registrar pacote, commit, data e validação.

### TECH-004 — Lint preexistente no formulário diário Cardio

- **Área:** Tooling
- **Tipo:** DÍVIDA TÉCNICA
- **Status:** ABERTO
- **Prioridade:** P3
- **Origem:** Inspeção CARDIO-001 / E.1 em 22/09/2026.
- **Descrição:** ESLint identifica react-hooks/immutability e exhaustive-deps em carregarPaciente/useEffect; mesmas ocorrências confirmadas no HEAD frontend 13123a6 por lint via stdin. Não corrigidas no pacote cirúrgico.
- **Impacto:** Lint do arquivo permanece com 1 erro e 1 warning preexistentes.
- **Evidência:** FE src/pages/cardiometabolico/RegistroDiarioCardiometabolico.jsx:43 no HEAD; docs/cardio-001-e1-implementation.md.
- **Dependências:** Revisão isolada de lifecycle do formulário.
- **Critério de conclusão:** Ocorrências eliminadas sem requests duplicados, perda de contexto ou regressão de submissão.
- **Pacote sugerido:** Higiene de hooks do formulário Cardio.
- **Responsável:** A definir.
- **Data/prazo:** Não definido; inventariado em 22/09/2026.
- **Resolução:** Pendente.

## Reconciliação: não reabrir automaticamente

- CARDIO-DR-OBS-001: não duplicado como aberto. Provider preserva observacoes e responsável chama serviço institucional (app/services/daily_record/providers/cardio.py:43; app/routers/responsavel_cardio.py:94); docs/cardio-v1-wave-2-checkpoint.md documenta convergência.
- Webhook sem assinatura, teste público e logs sensíveis: dívida histórica superada pelo gate de segurança Wave 2; separar da confirmação operacional WHATSAPP-001.
- Ausência de autoria física Cardio: schema alignment foi resolvido; ausência é explicitamente indisponível por decisão de produto, não autorização para criar coluna. Evidência: docs/cardio-physical-schema-alignment.md e app/services/timeline/sources.py:110.
- Report Engine Cardio ausente e Cockpit Profissional sem Multi-Line: documentação antiga superada pelos checkpoints Wave 4 e professional-cockpit-multiline; não reabrir.
- Concorrência Daily Record: docs/daily-record-concurrency.md:153 registra validação posterior; não reabrir a falha histórica da remediation como defeito atual.
- Skips PostgreSQL condicionais são proteção de ambiente, não testes defeituosos; gates posteriores registram zero skips. Nenhum item de correção criado apenas pela presença de skipUnless.
- bcrypt deprecated="auto" é configuração de biblioteca, não TODO. Busca por TODO encontrou também literal de filtro TODOS; descartado.
- Sem as-of, sem autoria histórica inventada e sem trend Cardio são limites aprovados, não roadmap automático.
- Lint preexistente mencionado na conversa: sem nova execução/comparação de ocorrências nesta atividade; não perpetuar contagem histórica como diagnóstico atual.
- Roadmap estratégico contém produção, BI/IA/financeiro/APIs públicas sem contrato de pendência validado; não importado.

## Consolidação e próximos passos

E.1 (CARDIO-001) precede Massa Canônica (DATA-001) e convergência IMC legado (CARDIO-002). Warnings de bundle repetidos em várias Waves estão somente em TECH-001; Pydantic em TECH-002; achados de ACL em SEC-001. Não confundir esses itens com a correção clínica.

Inventário não é auditoria exaustiva de segurança nem certificação operacional. Itens REVISAR devem recuperar evidência antes de virar implementação. Nenhuma pendência foi resolvida nesta atividade.
