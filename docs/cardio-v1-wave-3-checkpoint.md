# WAVE 3 — EXECUTION REPORT

STATUS: PASS — Gate técnico local, em ambiente descartável.

## 1. Objetivo executado

Inteligência Longitudinal Cardio: 360°, Timeline, Evolução, ClinicalReading,
Continuity, Priority operacional e Cockpit. Não foi iniciada a Wave 4.

## 2. AS-IS confirmado

O router/360 consumia interpretações persistidas, reconstruía IMC com altura
cadastral e calculava tendência; a Timeline especializada também modificava risco.
O Cockpit derivava sua população de registros e o React possuía scoring/fallbacks.
Esses caminhos da jornada agora consomem os contratos institucionais. Os helpers
locais do router que ficaram sem chamadas foram removidos após busca de referências.

## 3. Arquivos alterados

Backend (worktree `/private/tmp/integra-wave1`):

- `app/routers/cardiometabolico.py`
- `app/services/cardio_longitudinal.py` (novo)
- `app/services/cardio_evolution.py` (novo)
- `app/services/cardio_priority.py` (novo)
- `app/services/continuity_service.py` (novo)
- `app/services/care_lines/registry.py`
- `app/services/clinical_reading/service.py`
- `app/services/clinical_reading/providers/__init__.py`
- `app/services/clinical_reading/providers/cardio.py`
- `app/services/cockpit_gestao_service.py`
- `app/services/timeline/sources.py`
- `app/services/timeline_service.py`
- `tests/test_cardio_longitudinal.py` (novo)
- `tests/test_clinical_reading.py`
- `tests/test_timeline.py`
- `tests/fixtures/cardio_gate3_http.py` (novo)
- este relatório.

Frontend (worktree `/private/tmp/integra-wave7-front`):

- `src/pages/cardiometabolico/DashboardCardiometabolico.jsx`
- `src/pages/cardiometabolico/PacienteCardiometabolico.jsx`
- `src/pages/cardiometabolico/PacientesCardiometabolico.jsx`
- `src/pages/cardiometabolico/GraficosCardiometabolico.jsx`
- `src/pages/cardiometabolico/TimelineCardiometabolico.jsx`
- `src/services/cardiometabolico.js`
- `tests/cardio-longitudinal-integration.cjs` (novo)
- `tests/gate1-integration.cjs` (seleção da massa-base continua verificando os mesmos
  quatro pacientes, permitindo pacientes sintéticos adicionais da Wave 3).

## 4. Migrations / dados

Nenhuma migration nesta Wave. Nenhum banco compartilhado alterado.
Somente schemas UUID de testes e novas entidades sintéticas no banco descartável
`integra-cardio-gate2-pg` foram utilizados. A fixture HTTP alinha exclusivamente a
sequência de pacientes desse banco, cujos primeiros IDs foram inseridos manualmente.
A fixture histórica cria formulário INATIVO com unidades explícitas; não modifica
formulários ativos nem adiciona captura de altura aos canais.

## 5. Decisões técnicas / semântica

- ClinicalReading continua sendo a fonte institucional de risco, resumo, score e
  protocolo; as duas últimas propriedades permanecem especializadas em metadata.
- A leitura individual e a leitura em lote compartilham a mesma tradução Cardio e
  o mesmo engine. Nenhum threshold, protocolo ou regra clínica foi alterado.
- Cardio trend permanece `None`. Observação inexistente/vazia não vira baixo risco.
- População nasce de paciente ativo + vínculo ativo, com autorização de clínica e
  linha do profissional; existência de eventos não determina pertencimento.
- Timeline reutiliza as fontes institucionais de registros, diagnósticos e
  intervenções. Não calcula risco/tendência. Preserva data clínica, timestamp de
  criação, autoria, origem e observações complementares como fatos distintos.
- Evolução lê respostas da mesma observação/formulário Cardio. Não mistura máximos
  históricos, últimas medições de datas diferentes ou altura cadastral.
- IMC exige respostas únicas de peso/altura, valores positivos finitos e unidades
  explícitas: labels `Peso (kg)` e `Altura (m)` ou `Altura (cm)`, com comparação sem
  distinção de caixa e espaços externos. Sem essa evidência: `imc=None` e motivo de
  indisponibilidade. Não se infere unidade pela magnitude/nome interno do campo.
  A conversão cm→m é dimensional; não é regra clínica. Não há carry-forward.
- O resumo do paciente só apresenta IMC quando record_id coincide com a observação
  utilizada pela ClinicalReading; uma alteração concorrente não mistura registros.
- Continuidade mantém exatamente os limites existentes: None→NAO_INICIADA,
  0–3→REGULAR, 4–6→ATENCAO, 7+→CRITICA. A implementação antiga delega à mesma função.
- Priority aplica exclusivamente a decisão aprovada: risco crítico > risco alto >
  continuidade crítica > risco moderado > continuidade em atenção. Consolida todos
  os sinais por paciente, sem score, com motivo principal e desempate nome/id.
- Cockpit expõe Welcome, Summary, Quick Actions, Priority, Recent Activity e síntese
  de acompanhamento. Capability `cockpit` Cardio passou a ACTIVE; `report` continua
  PLANNED. Não há ações PTS/Planejamento/Agenda/Sessões.

## 6. Testes adicionados / alterados

28 novos casos executáveis: 8 de política/semântica e 10 de jornada executados tanto
em SQLite quanto em PostgreSQL. Incluem as 20 combinações risco×continuidade,
precedência, deduplicação, empate, IMC válido/ausente/ambíguo, alteração cadastral,
paridade leitura individual/lote, contexto inativo/planejado, observação atual
vazia, três origens, diagnóstico/intervenção, Multi-Line, ACL, paginação e consultas.
As expectativas anteriores foram atualizadas para Cockpit ACTIVE e observações
fatuais opcionais na Timeline, sem alteração de expectativa clínica Neuro.

## 7. Comandos executados

Backend, a partir de `/private/tmp/integra-wave1`:

```sh
docker run --rm --network container:integra-cardio-gate2-pg -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONDONTWRITEBYTECODE=1 -e CARDIO_GATE1_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test -e CARE_PLAN_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test -e SESSION_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test -e WAVE5_TEST_POSTGRES_URL=postgresql+psycopg2://wave5@127.0.0.1/wave5_test -e WHATSAPP_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test -e CARDIO_GATE3_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test docker-api python -m unittest discover -s tests

docker run --rm --network container:integra-cardio-gate2-pg -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONDONTWRITEBYTECODE=1 -e WAVE3_TEST_POSTGRES_URL=postgresql+psycopg2://wave3@127.0.0.1/wave3_test docker-api python -m unittest discover -s tests -p test_daily_record.py

docker run --rm -v /private/tmp/integra-wave1:/work:ro -w /work docker-api python -c 'import ast,pathlib; paths=list(pathlib.Path("app").rglob("*.py"))+list(pathlib.Path("tests").rglob("*.py")); [compile(ast.parse(p.read_text(),filename=str(p),feature_version=(3,9)),str(p),"exec") for p in paths]; print("Python 3.9 compile PASS",len(paths))'

docker exec -e PYTHONPATH=/work integra-cardio-gate2-api python tests/fixtures/cardio_gate3_http.py
git diff --check
git diff --quiet HEAD -- app/services/neuro_engine.py app/services/cardiometabolico_engine.py
```

Frontend, a partir de `/private/tmp/integra-wave7-front`:

```sh
npm run build
npx eslint src/pages/cardiometabolico/DashboardCardiometabolico.jsx src/pages/cardiometabolico/PacienteCardiometabolico.jsx src/pages/cardiometabolico/PacientesCardiometabolico.jsx src/pages/cardiometabolico/GraficosCardiometabolico.jsx src/pages/cardiometabolico/TimelineCardiometabolico.jsx src/services/cardiometabolico.js
PLAYWRIGHT_MODULE=/Users/Abnel/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright node tests/cardio-longitudinal-integration.cjs
PLAYWRIGHT_MODULE=/Users/Abnel/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright node tests/gate1-integration.cjs
git diff --check
```

## 8. Resultados observados

- Suíte completa final: **303 testes, 0 falhas, 0 pulos**, 14,869 segundos.
  Os 33 anteriormente pulados efetivamente executaram com PostgreSQL.
- Daily Record complementar no PostgreSQL: **33 testes, 0 falhas, 0 pulos**.
  É uma execução adicional com sobreposição de casos; não significa 336 casos únicos.
- Compilação Python 3.9: **246 arquivos**, PASS.
- Build frontend: **865 módulos**, PASS; lint de todos os arquivos JS/JSX de produto
  alterados, PASS; diff check em ambos os repositórios, PASS.
- Jornada HTTP real: PASS, quatro contextos WhatsApp (Neuro, Cardio e paciente
  Multi-Line nas duas linhas), mais Portal/APP, replay, datas, autoria/origem,
  diagnósticos/intervenções, histórico de IMC, ausência de dados e ACL.
- Jornada navegador: PASS, Cockpit/360/Timeline/Evolução, indisponibilidade,
  escrita real Portal com confirmação de observações na Timeline, regressão Neuro,
  sem erro de execução JS ou resposta 5xx.
- Regressão navegador Wave 1: **4 jornadas**, PASS; cadastro contextual de diagnóstico,
  consulta/detalhe, isolamento de intervenções e cancelamento contextual.
- Cockpit: **14 consultas com 3 pacientes e 14 com 53**, em SQLite e PostgreSQL.
  Priority pagina após consolidação/ordenação global (20 padrão, máximo 100 pela
  API). Atividade recente limita cada fonte no SQL e carrega respostas apenas dos
  registros selecionados; resultado global limitado a 10. Teste confirma mesma
  ordem do histórico institucional completo. Não foi feito teste de carga produtiva.

Falhas intermediárias foram corrigidas e reexecutadas: sintaxe JSX (`??`/`||`),
regras de hooks/lint, whitespace, expectativa antiga da capability PLANNED,
inicialização ainda não pronta da API descartável, sequência de fixture e HTTP
201 de diagnóstico. Uma leitura transitória incompleta do script pelo mount Docker
foi reexecutada após confirmar o arquivo completo. Tentativa de py_compile nativo
não concluiu por cache fora do sandbox; a compilação em memória e no container
Python 3.9 acima concluiu. Nenhuma execução falha foi contada como PASS.

## 9. Isolamento Multi-Line

Somente registros/formulários Cardio entram na Evolução; associação explícita da
fonte determina a Timeline. Multi-Line mantém um paciente e duas jornadas. O teste
HTTP criou diagnósticos nas duas linhas, registros dos três canais e intervenção
Cardio, e verificou as leituras correspondentes. Paciente de outra clínica e
paciente sem vínculo Cardio foram negados. Paciente Cardio sem registros permaneceu
na população e exibiu indisponibilidade.

## 10. Regressão Neuro

`neuro_engine.py` e `cardiometabolico_engine.py` permaneceram sem diff. A suíte
completa inclui caracterização Neuro, Wave 1/2, WhatsApp, autoria e proteção da rota
longitudinal. As quatro jornadas de diagnóstico/360 foram reexecutadas, incluindo
Neuro exclusivo e o mesmo paciente Multi-Line. O perfil legado de Timeline Neuro
e a fronteira de compatibilidade do Report Engine não foram reescritos.

## 11. Dívidas técnicas delimitadas

- O serviço legado `app/services/cardiometabolico.py` deixou de ser consumidor
  destes endpoints; não houve limpeza ampla de código legado.
- `/cardiometabolico/alertas` e `/cardiometabolico/mapa-risco` legados não foram
  integrados ao Cockpit desta Wave e não constituem a fonte institucional aqui.
  Sua lógica/autorização preexistentes permanecem fora desta entrega; não se declara
  convergência global de todo endpoint Cardio.
- A lista antiga de pacientes mantém seu contrato de lista e paginação visual.
  O cálculo de contadores/Priority lê a população autorizada em lote; custo de CPU
  cresce com essa população, apesar do número constante de consultas.

## 12. Riscos / limites

Ausência de unidade explícita ou altura da própria observação limita corretamente
IMC; não foi ampliada captura de altura. A disponibilidade não depende da altura
cadastral. Labels de unidades são evidência do formulário referenciado; não foi
introduzido versionamento novo de metadados nesta Wave.

O build mantém aviso de bundle >500 kB; Pydantic mantém aviso de `dict()` antigo.
Nenhum desses avisos correspondeu a falha dos gates. Não se declarou lint global
de arquivos não alterados nem desempenho em escala de produção.

Meta real, segredos reais, configuração HML/PROD e banco compartilhado não foram
utilizados. Permanecem os requisitos externos de liberação operacional documentados
na Wave 2; não há nova configuração externa necessária para comprovar este Gate 3.

## 13. Gate 3

- [x] Timeline contém somente eventos Cardio.
- [x] Diagnóstico Cardio integra Timeline.
- [x] Daily Records de Portal, APP e WhatsApp integram jornada.
- [x] Intervenção Cardio integra Timeline.
- [x] Evolução utiliza somente observações Cardio e respeita política temporal IMC.
- [x] Clinical Engine mantém regras existentes; trend indisponível.
- [x] Continuity permanece independente do risco clínico.
- [x] Priority consolida sinais sem duplicação e aplica precedência aprovada.
- [x] Cockpit respeita capabilities.
- [x] Nenhuma ação PTS/Planejamento/Agenda/Sessões no Cockpit Cardio.
- [x] Neuro continua funcional nas regressões executadas.

## 14. Git

Worktrees isolados na branch `codex/cardio-v1-stabilization`.
Baselines: backend `6f60b9916a028d8d4ff186b476c233521735c88d`;
frontend `bbd3f84d2176aa1981f63c0582cf75a02e7b3ff3`.
Entrega em commits locais coerentes por repositório, identificados no relatório
final. Nenhum push, merge ou deploy. Checkouts originais preservados.

## 15. Próxima Wave

**Parar antes da Wave 4 (Report Engine).** Gate 3 entregue para validação humana.
Não foi iniciada implementação da próxima Wave.
