# WAVE 2 — EXECUTION REPORT / GATE 2

2026-09-17.

**Gate técnico no ambiente isolado: PASS.**
**Integração operacional Meta/HML/PROD: NÃO VALIDADA; liberação pendente.**
Nenhuma Wave 3 iniciada. Nenhum teste falhando na suíte automatizada final.
Lint adicional de Paciente.jsx mantém dívida anterior idêntica ao HEAD (abaixo).

## 1. Objetivo executado e AS-IS

Portal e APP Cardio passaram a utilizar a mesma representação canônica de
observações gerais e o mesmo provider institucional. WhatsApp passou de entrada
não autenticada, identificada apenas por telefone e especializada em persistência
Neuro, para uma entrada autenticada e transacional compartilhada pelas Linhas.
A rota longitudinal genérica também exigia proteção: era uma entrada paralela do
Portal sem autenticação. Agora autentica, autoriza clínica/paciente/Linha e propaga
usuário real, preservando o bloqueio de edição de atendimentos canônicos.

## 2. Decisões implementadas

- CARDIO-DR-OBS-001: `registros_longitudinais.observacoes` permanece o único campo
  canônico para o texto complementar. Sem metadado de formulário ou alias novo.
  Texto exato preservado. Omissão em edição preserva texto; null explícito limpa.
  Observação não entra em score, risco, tendência, narrativa do motor ou indicadores.
- Portal: autorização contextual, autor autenticado e normalização de números
  opcionais vazios no frontend. APP: provider comum, formulário/campos da Linha,
  manutenção de hoje/ontem e bloqueio de duplicidade por responsável Cardio.
- `/whatsapp/teste` removido, em todos os ambientes; nenhuma alternativa pública.
- POST autentica HMAC-SHA256 dos bytes originais com comparação segura. Secret ou
  destinatário não configurado: 503. Assinatura ausente/inválida: 403. Nenhum acesso
  clínico/persistência nesses casos. Payload autenticado inválido: 400; destinatário
  divergente: 403. Todo o envelope é validado antes de processar mensagens.
- GET exige verify token configurado e não vazio, token recebido correto e challenge.
- Deduplicação durável por ID de mensagem; fingerprint impede reaproveitamento do
  mesmo ID com conteúdo/remetente diferente. Advisory lock transacional serializa
  remetente; lock de responsável serializa equivalências de telefone.
- Recibo, conversa e eventual registro/respostas/projeção são confirmados juntos.
  O fluxo conversacional usa flush; DailyRecordService aceita `commit=False` para
  participação explícita na transação do canal. Demais chamadas mantêm commit padrão.
- Resposta de saída é enviada após commit clínico. Lock do recibo e `enviado_em`
  evitam repetir envio confirmado. Falha de transporte permite retry sem repetir
  gravação clínica. Timeout após aceitação remota continua sendo entrega incerta;
  não se promete exatamente uma entrega de rede.
- Telefone com zero/múltiplas correspondências não libera contexto clínico. Mantidas
  equivalências já existentes de DDI/nono dígito somente quando a identidade é única.
- Responsável ativo, paciente ativo, vínculo, clínica e Linha são revalidados antes
  de gravar. Paciente Multi-Line exige seleção explícita da Linha pelo responsável.
- Neuro mantém perguntas/opções/mapeamentos clínicos. A persistência passa ao serviço
  institucional, sem IDs fixos de campos/formulário no escritor WhatsApp.
- Captura Cardio no WhatsApp apresenta as quatro medidas existentes e observações
  aprovadas; não acrescenta campo clínico nem altera questionário Portal/APP.
  `pular` representa ausência, sem fabricar risco. Trend Cardio segue indisponível.
- APP grava `RESPONSAVEL_APP`; WhatsApp grava `RESPONSAVEL_WHATSAPP`; ambos gravam
  `criado_por_responsavel_id`. Portal grava `PROFISSIONAL` e usuário autenticado.
  Leituras/duplicidade mantêm compatibilidade com registros anteriores `RESPONSAVEL`.
- Frontend continua identificando as duas origens novas como dados da família.
- Removidos logs de telefone, mensagem, resposta e texto de erro externo. Filtro do
  access log Uvicorn retira query de verificação. Proxy externo deve ter proteção
  equivalente; sua configuração não foi inspecionada nem alterada.
- Cardio `whatsapp` declarado ACTIVE após implementação e validação isolada.

## 3. Arquivos alterados

Backend funcional:
- app/routers/{whatsapp,registros_longitudinais,responsavel_registros,responsavel_cardio,cardiometabolico}.py
- app/services/whatsapp_{ingress,conversation_service,daily_record,cardio,sender_service}.py
- app/services/daily_record/{service,adapters}.py
- app/services/daily_record/providers/cardio.py
- app/services/responsavel_registro_service.py (compatibilidade de origem em helper anterior)
- app/services/care_lines/registry.py
- app/models/{__init__,whatsapp_conversa,whatsapp_mensagem}.py
- alembic/versions/8c01a0d1a004_whatsapp_ingress.py

Testes/documentação:
- tests/test_whatsapp_{security,postgres}.py
- tests/test_cardio_channels.py
- tests/test_daily_record.py; tests/test_daily_record_routes.py
- tests/test_intervention_migration.py; tests/test_sessions_attendance.py
- tests/fixtures/{cardio_gate1_runtime,cardio_gate2_runtime,whatsapp_gate2_runtime,whatsapp_gate2_http}.py
- docs/cardio-v1-wave-2-plan.md; este relatório

Frontend:
- src/services/cardiometabolico.js
- src/pages/Paciente.jsx (reconhecimento das origens da família, sem redesign)
- tests/cardio-observations-integration.cjs

## 4. Migration e dados

Revisão aditiva `8c01a0d1a004`, sucessora única de `8c01a0d1a003`:
- `whatsapp_mensagens`: message_id PK, phone_number_id, fingerprint, resposta,
  criado_em, enviado_em opcional;
- `whatsapp_conversas.care_line` opcional para o estado anterior à seleção;
- conversas já existentes recebem NEURO porque o escritor anterior era
  exclusivamente Neuro, por proveniência do fluxo, nunca por inferência de vínculo.

Upgrade/downgrade da revisão final testados em schemas UUID do PostgreSQL descartável.
Recibos podem conter resposta assistencial: são armazenamento interno, sem endpoint
público de consulta; não devem ser exportados para logs. Downgrade remove histórico
operacional de recibos, portanto não é procedimento de recuperação de produção.

Runtime HTTP também usou somente PostgreSQL descartável, com reconstrução explícita
do schema anterior na fixture e evolução sintética para o schema final. Isso não
substitui nem inventa histórico de migrations de HML/PROD. Nenhuma execução neles.
Nenhuma migration para observacoes, nenhuma alteração de metadados clínicos.

## 5. Testes e resultados finais

| Validação | Resultado observado |
|---|---|
| Suíte completa com PostgreSQL habilitado | **275 testes, OK, zero skips** |
| Subconjunto WhatsApp/segurança/rota longitudinal | **35 testes, OK** (incluídos nos 275) |
| Registro Diário executado separadamente em PostgreSQL | **33 testes, OK** (sobreposição, não somar como únicos) |
| Regressão de sessões após autenticação da rota | **24 testes, OK** (incluídos na suíte) |
| Compilação/AST Python 3.9 | **241 arquivos PASS**, sem bytecode no repositório |
| HTTP real assinado local | Neuro, Cardio, Multi-Line em ambas as Linhas, datas e replay final PASS |
| Navegador real Portal + API real APP | Observações, número opcional vazio, autoria/canal e ACL PASS |
| Navegador regressão Gate 1 | Quatro jornadas 360/diagnóstico + intervenção/Timeline/ACL PASS |
| Build frontend | PASS, 861 módulos, aviso preexistente de bundle grande |
| ESLint do serviço frontend alterado | PASS |
| ESLint adicional Paciente.jsx | 19 erros/1 aviso; saída **idêntica ao HEAD**, nenhum novo |
| Revisão de diff e git diff --check nos dois worktrees | PASS |

Os 15 testes anteriormente dependentes de PostgreSQL foram executados, sem skips.
A suíte inclui caracterizações Neuro e regressões das foundations anteriores.
Scoring, thresholds, Clinical Engines e questionário clínico Neuro não foram alterados.

Cobertura específica: assinatura válida/inválida/ausente, adulteração, configuração
vazia, GET, ausência de rota de teste mesmo com flags, destinatário, JSON inválido,
envelope misto, eventos ignorados, identidade desconhecida/ambígua/inativa, clínica,
vínculo revogado, Linha inativa, replay, concorrência, conflito de ID, rollback antes
e durante projeção, retry de entrega, Neuro/Cardio/Multi-Line, canais, leitura de
origens anteriores, ausência de dados e ausência de texto sensível nos logs.
Rota longitudinal: autenticação, clínica/Linha, autoria, origem responsável forjada,
e preservação de HTTP 409 para alterações de atendimentos canônicos.

### Comandos executados

Backend `/private/tmp/integra-wave1` (montado read-only nos containers):

```sh
docker run --rm --network container:integra-cardio-gate2-pg -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONDONTWRITEBYTECODE=1 -e CARDIO_GATE1_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test -e CARE_PLAN_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test -e SESSION_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test -e WAVE5_TEST_POSTGRES_URL=postgresql+psycopg2://wave5@127.0.0.1/wave5_test -e WHATSAPP_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test docker-api python -m unittest discover -s tests

docker run --rm --network container:integra-cardio-gate2-pg -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONDONTWRITEBYTECODE=1 -e WHATSAPP_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test docker-api python -m unittest discover -s tests -p 'test_whatsapp*.py'

docker run --rm --network container:integra-cardio-gate2-pg -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONDONTWRITEBYTECODE=1 -e WAVE3_TEST_POSTGRES_URL=postgresql+psycopg2://wave3@127.0.0.1/wave3_test docker-api python -m unittest discover -s tests -p test_daily_record.py

docker run --rm -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONDONTWRITEBYTECODE=1 docker-api python -m unittest discover -s tests -p test_sessions_attendance.py

docker run --rm -v /private/tmp/integra-wave1:/work:ro -w /work docker-api python -c 'import ast,pathlib; paths=list(pathlib.Path("app").rglob("*.py"))+list(pathlib.Path("tests").rglob("*.py"))+[pathlib.Path("alembic/versions/8c01a0d1a004_whatsapp_ingress.py")]; [compile(ast.parse(p.read_text(),filename=str(p),feature_version=(3,9)),str(p),"exec") for p in paths]; print("Python 3.9 compile PASS",len(paths))'

docker exec -e PYTHONPATH=/work integra-cardio-gate2-api python tests/fixtures/whatsapp_gate2_http.py
docker exec -e PYTHONPATH=/work -e WHATSAPP_GATE_DAY_OFFSET=1 integra-cardio-gate2-api python tests/fixtures/whatsapp_gate2_http.py
```

O segundo HTTP run verifica ontem, após o primeiro preencher hoje, nos mesmos
pacientes sintéticos. Não se enviou mensagem a destinatários reais. Assinaturas
foram geradas com segredo sintético; o container não recebeu access token Meta.

Frontend `/private/tmp/integra-wave7-front`:

```sh
npm run build
npx eslint src/services/cardiometabolico.js
npx eslint src/pages/Paciente.jsx
git show HEAD:src/pages/Paciente.jsx | npx eslint --stdin --stdin-filename src/pages/Paciente.jsx
PLAYWRIGHT_MODULE=/Users/Abnel/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright node tests/cardio-observations-integration.cjs
PLAYWRIGHT_MODULE=/Users/Abnel/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright node tests/gate1-integration.cjs
git diff --check
```

Lint da página foi comparação adicional: ambas as versões falham identicamente.
Não se afirma que o lint global frontend esteja limpo. A integração APP foi feita
pela API autenticada; não se afirma teste de navegador do aplicativo de responsável.
Falhas intermediárias foram corrigidas/reexecutadas: dependência httpx ausente
(substituída pelo helper ASGI sem nova dependência), nome de método no teste,
expectativa de head Alembic, asserção de privacidade e chamadas diretas sem usuário.
Comando recusado anteriormente não foi considerado executado; nenhum controle
foi contornado. Os resultados acima vêm de execuções permitidas observadas.

## 6. Critérios do Gate e limites

- [x] Portal/APP/WhatsApp convergem na persistência institucional por Linha.
- [x] Observações Cardio canônicas, sem efeito clínico automático.
- [x] Origem/autor rastreáveis; APP e WhatsApp distintos.
- [x] Autenticidade da entrada e destinatário verificados antes de acesso clínico.
- [x] Deduplicação durável e transação clínica atômica, incluindo concorrência.
- [x] Neuro preservado e paciente Multi-Line isolado sem duplicação de identidade.
- [x] Intervenções independentes de PTS e isolamento do 360 preservados.
- [x] Suíte final, PostgreSQL, compilação, build e regressões integradas passaram.
- [ ] Configuração e entrega real Meta: fora do ambiente autorizado, não comprovadas.
- [ ] Liberação HML/PROD: não realizada nem presumida.

## 7. Configuração externa necessária antes de liberação operacional

1. Identificar aplicação Meta/remetente de eventos efetivos e provisionar
   `WHATSAPP_APP_SECRET` correspondente, por ambiente, sem exposição em código/log.
2. Manter `WHATSAPP_VERIFY_TOKEN` não vazio e alinhar `WHATSAPP_PHONE_NUMBER_ID`.
   `WHATSAPP_ACCESS_TOKEN` é somente para envio; não substitui o App Secret.
3. Aplicar a migration por procedimento autorizado no ambiente alvo; nesta entrega
   apenas o PostgreSQL descartável foi alterado.
4. Confirmar HTTPS, preservação do header X-Hub-Signature-256 e corpo original no
   proxy, e redigir/omitir query/token e conteúdo assistencial dos logs externos.
5. Validar handshake, evento real assinado e resposta real em ambiente expressamente
   autorizado. Integrações manuais sem assinatura deixarão de funcionar por projeto.

Sem esses itens, não se declara o WhatsApp de HML/PROD operacional. A proteção falha
fechada sem configuração. Não há outra decisão clínica pendente identificada.

## 8. Dívidas e observações delimitadas

- Lint preexistente da página Neuro: 19 erros/1 aviso, inclusive regras de hooks;
  nenhuma alteração desses trechos nesta Wave, sem ocorrência nova no diff.
- Avisos preexistentes de bundle frontend e Pydantic `dict()`.
- APP ainda lê a projeção para resposta após commit; falha dessa leitura pode
  comunicar erro após gravação concluída. Não ocorreu nas validações.
- Correspondência de telefones ainda percorre responsáveis ativos; duplicidade
  falha fechada. Cadastro Único/normalização persistida não foi implementado.
- Exatamente uma gravação clínica por message_id não implica exatamente uma entrega
  de rede após timeout remoto. Retenção/acesso operacional aos recibos precisa
  acompanhar as políticas de dados assistenciais antes de uso real.

## 9. Git e próximo passo

Dois worktrees isolados na branch `codex/cardio-v1-stabilization`.
Baseline backend `91fb278`; frontend `dcedac7`. Entrega em commits locais por
repositório, identificados no relatório final da tarefa. Sem push, merge ou deploy.
Os checkouts originais e banco compartilhado foram preservados.

**Parar antes da Wave 3.** Apresentar este Gate técnico e a configuração externa
pendente para validação, sem presumir integração real Meta.
