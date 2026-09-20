# WAVE 4 — EXECUTION REPORT

Data: 2026-09-18. Gate 4: **PASS**. Execução encerrada antes da Wave 5.

## Baseline e preservação

- Backend Gate 3: `8c4a794081ea1fd8fa9b0c27a9d5e963f3eadbb3`.
- Frontend Gate 3: `854d839f9437e9571b4152fd1ec468cb675d3a8c`.
- Branch dos dois repositórios: `codex/cardio-v1-stabilization`.
- Backend utilizado: `/private/tmp/integra-wave4-backend`; frontend: `/private/tmp/integra-wave7-front`.
- O antigo diretório backend `/private/tmp/integra-wave1` estava incompleto, sem `.git` e com 239 arquivos rastreados ausentes. Seus arquivos foram preservados. O worktree recuperado foi preparado no commit aprovado, sem utilizar nem sobrescrever alterações do checkout original em `main`.
- A retomada final preservou todas as alterações da execução interrompida e os containers descartáveis existentes. Não recriou worktrees nem reiniciou a Wave.

## Arquitetura final

Um `ReportService`, um `ReportComposer`, um `CanonicalReport` e um `PDFRenderer`.

`ReportDefinition` declara Care Line, providers, engines, knowledge engines e sections. A mera presença no registro global de Knowledge Engines não executa nada. `ReportRegistry.for_care_line` seleciona a definição da Linha resolvida; não existe seleção implícita de Neuro para paciente Multi-Line.

- **CLN-001 / NEURO:** composição explícita dos nove Knowledge Engines existentes, PTS, sessões, avaliações e diagnóstico. `NeuroClinicalEngineProvider` adapta a forma do `ClinicalReading` institucional para os campos que os Knowledge Engines já consomem; não executa outro cálculo nem altera resultados do Neuro.
- **CLN-CARDIO-001 / CARDIO:** paciente, diagnósticos contextualizados, fontes da Timeline Cardio já institucionais, Evolução Cardio institucional e `ClinicalReading`. Sections Cardio apresentam fatos e a interpretação da Linha. Não são executados providers/Knowledge Engines de PTS, planejamento, sessões, M-CHAT ou Denver.
- `CareLineResolver` valida vínculo ativo, módulo e capability `report`; `ClinicalReadingService` mantém sua validação de `clinical_reading`. Cardio `report` passa de PLANNED para ACTIVE após implementação e testes. Nenhuma outra capability mudou.
- O endpoint verifica identidade autenticada, papel e clínica antes de resolver contexto do paciente; depois aplica a autorização institucional profissional/Linha. Erro interno não devolve SQL ou conteúdo da exceção.
- Frontend compartilha `ReportDownload`, propagando a Linha fixa do 360° e o período, sem seletor arbitrário de Linha.

## Política temporal implementada

- Período inclusivo. Timeline/Registro Diário/intervenções/avaliações usam data clínica quando disponível; fontes sem data clínica usam criação apenas como **data técnica explicitamente identificada**.
- `ClinicalReading` é sempre atual; `reference_date` identifica a última observação utilizada, mesmo posterior ao período. Não há reconstrução as-of.
- Diagnósticos: eventos dentro do período e diagnósticos atualmente ativos anteriores ao início; estes são identificados separadamente. Diagnóstico sem `modulo_id` não entra em nenhuma Linha.
- PTS/planejamento: seleção por sobreposição de datas; status e objetivos são contexto atual, sem reconstrução histórica. Sessões: data de realização, ou data agendada se não há realização; status é o atual persistido. Política explicitada no PDF.
- Evolução/IMC consomem o serviço da Wave 3. Altura cadastral não reconstrói IMC; sem peso/altura e unidades na mesma observação, IMC fica indisponível.
- Cardio não ganha tendência, estado clínico, recomendações, thresholds ou score novos. Score/protocolo apresentados vêm do metadata da leitura canônica.
- Ausência de interpretação não é baixo risco/normalidade/estabilidade. Neuro conserva `sem_dados`.
- O resumo executivo Neuro deixou de afirmar continuidade incondicionalmente; apresenta fatos disponíveis e identifica estado atual. Nenhuma regra clínica Neuro foi alterada.
- Quando datas não são enviadas, mantém-se o intervalo padrão da rota: criação cadastral até hoje. Trata-se do padrão do filtro, não de data clínica nem de `reference_date`. Datas explícitas permitem incluir observações anteriores ao cadastro.

## Gate 4 — 13 critérios

| # | Critério | Evidência | Resultado |
|---|---|---|---|
| 1 | Mesmo engine gera Neuro | `test_same_framework_explicit_composition`; download real pacientes 1 e 3 | PASS |
| 2 | Mesmo engine gera Cardio | Mesma classe e renderer; download real pacientes 2 e 3 | PASS |
| 3 | Neuro mantém PTS/avaliações/sessões | `test_neuro_keeps_pts_assessments_sessions_in_period`: PTS Neuro, objetivo, planejamento, sessão no período, M-CHAT e Denver; PDF inspecionado | PASS |
| 4 | Cardio não executa/renderiza Neuro | Spies que falham se qualquer um dos nove Knowledge Engines Neuro ou providers PTS/sessão/avaliação executar; ausência nos sections/PDF | PASS |
| 5 | Somente dados Cardio | Registros/diagnósticos das duas Linhas na mesma identidade; conteúdo do PDF isolado | PASS |
| 6 | Linha chega às fontes | Resolver, filtros de diagnóstico/PTS/sessão e TimelineQuery CARE_LINE; leitura/evolução Cardio institucionais | PASS |
| 7 | Período consistente | Observação posterior afeta apenas leitura atual; eventos/evolução ficam no período; diagnóstico ativo anterior separado; timestamp técnico identificado | PASS |
| 8 | ClinicalReading Cardio institucional | Igualdade com `ClinicalReadingService.get_reading`; risco crítico e referência atual preservados; tendência None | PASS |
| 9 | PDF Cardio | Renderer compartilhado; duas páginas úteis, extração e inspeção visual | PASS |
| 10 | PDF Neuro | Renderer compartilhado; quatro páginas úteis com PTS/sessões/avaliações, extração e inspeção visual | PASS |
| 11 | Multi-Line não mistura dados | Testes SQL e quatro downloads no navegador, incluindo paciente 3 nas duas Linhas | PASS |
| 12 | Diagnóstico legado sem Linha seguro | PostgreSQL sintético deliberadamente degradado permite inserir NULL; nenhum relatório incorpora o diagnóstico. Schema real do repositório continua NOT NULL | PASS |
| 13 | Sem regressão Neuro conhecida | Suíte completa, caracterização raw Neuro, comparação do adaptador campo a campo e jornada de download Neuro | PASS |

## Validações executadas

Todos os comandos Docker usaram somente bancos/fixtures sintéticos. Os containers compartilhados `sentinela_api` e `sentinela_postgres` não foram alterados.

### Backend — suíte completa final

Executado no worktree backend:

```sh
docker run --rm --network container:integra-cardio-gate2-pg \
  -v /private/tmp/integra-wave4-backend:/work:ro -w /work \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e CARDIO_GATE1_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e CARE_PLAN_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e SESSION_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e WHATSAPP_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e CARDIO_GATE3_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e CARDIO_GATE4_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e WAVE5_TEST_POSTGRES_URL=postgresql+psycopg2://wave5@127.0.0.1/wave5_test \
  docker-api python -m unittest discover -s tests
```

Resultado: **327 tests, OK, zero skips** (23.444s). Inclui 24 testes Report Multi-Line: 12 SQLite com compatibilidade de tipos/BOOL_OR restrita à fixture e 12 PostgreSQL real, sem mock do engine clínico neste último.

O nome histórico `WAVE5_TEST_POSTGRES_URL` pertence à suíte anterior de intervenções e não representa início de uma nova Wave.

### Report Engine/PDF após correção final de paginação

```sh
docker run --rm --network container:integra-cardio-gate2-pg \
  -v /private/tmp/integra-wave4-backend:/work:ro \
  -v /private/tmp/integra-gate4-evidence:/evidence -w /work \
  -e PYTHONDONTWRITEBYTECODE=1 -e GATE4_PDF_DIR=/evidence \
  -e CARDIO_GATE4_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  docker-api python -m unittest discover -s tests -p test_report_multiline.py
```

Resultado: **24 tests, OK, zero skips** (5.020s). Depois da suíte completa, o único ajuste de execução foi remover espaçador final do renderer que podia produzir página vazia; esta matriz foi repetida para validar o ajuste.

### Daily Record — PostgreSQL específico

```sh
docker run --rm --network container:integra-cardio-gate2-pg \
  -v /private/tmp/integra-wave4-backend:/work:ro -w /work \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e WAVE3_TEST_POSTGRES_URL=postgresql+psycopg2://wave3@127.0.0.1/wave3_test \
  docker-api python -m unittest discover -s tests -p test_daily_record.py
```

Resultado: **33 tests, OK, zero skips** (2.593s). Há sobreposição com a suíte completa; não são 33 casos novos a somar como testes distintos.

### Python 3.9

```sh
docker run --rm -v /private/tmp/integra-wave4-backend:/work:ro -w /work \
  docker-api python -c 'from pathlib import Path; files=list(Path("app").rglob("*.py"))+list(Path("tests").rglob("*.py")); [compile(p.read_bytes(),str(p),"exec") for p in files]; print("Python 3.9 compile:",len(files),"files PASS")'
```

Resultado: **251 arquivos PASS**, sem bytecode gravado.

### Frontend

No worktree frontend:

```sh
npm run build
npx eslint src/components/ReportDownload.jsx src/services/pacientes.js src/pages/cardiometabolico/PacienteCardiometabolico.jsx
PLAYWRIGHT_MODULE=/Users/Abnel/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright node tests/report-multiline-integration.cjs
```

- Build: **PASS, 866 módulos**. Warning de bundle >500 kB; não é falha de build.
- ESLint dos arquivos indicados: **PASS**; não se afirma lint global do frontend.
- Chrome real + frontend `127.0.0.1:5173` + API `127.0.0.1:8020`: **4 jornadas de download PASS**, Neuro/Cardio e paciente Multi-Line; query params Linha/período, status 200, bytes PDF e filename corretos. Sem pageerror/HTTP 5xx.
- 401 sem autenticação, 404 outra clínica, 409 sem Linha em Multi-Line, 422 período inválido; validação local do período também PASS.
- A tentativa anterior ao limite de uso foi recusada antes da execução. Não foi contada como teste e não houve contorno; a execução normal posterior foi aprovada e concluída.

### PDFs

Evidências sintéticas fora do repositório:

- `/private/tmp/integra-gate4-evidence/neuro.pdf`: quatro páginas.
- `/private/tmp/integra-gate4-evidence/cardio.pdf`: duas páginas.
- PNGs de todas as páginas: `neuro-reviewed-*.png` e `cardio-reviewed-*.png` na mesma pasta.

Extração com `pypdf` do runtime disponível e assertions em `check_pdf.py`: **PASS**, seis páginas não vazias, isolamento, atualidade, indisponibilidade de tendência, IMC factual, autoria, capacidades Neuro e caracteres literais `<`, `>` e `&` no texto Cardio.

```sh
/Users/Abnel/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 /private/tmp/integra-gate4-evidence/check_pdf.py
FONTCONFIG_FILE=/private/tmp/integra-gate4-evidence/fonts.conf pdftoppm -scale-to 1200 -png /private/tmp/integra-gate4-evidence/cardio.pdf /private/tmp/integra-gate4-evidence/cardio-reviewed
FONTCONFIG_FILE=/private/tmp/integra-gate4-evidence/fonts.conf pdftoppm -scale-to 1200 -png /private/tmp/integra-gate4-evidence/neuro.pdf /private/tmp/integra-gate4-evidence/neuro-reviewed
```

As seis imagens finais foram inspecionadas: sem cortes, sobreposição, título isolado no fim de página ou página final vazia. A narrativa/recomendação Neuro e seus componentes visuais existentes foram preservados.

### Performance e Git

- Teste Report Cardio: número de consultas invariável com 1 e 21 registros; sem consulta por observação.
- Regressão populacional Gate 3: **14 consultas com 3 e 53 pacientes**, SQLite e PostgreSQL.
- `git diff --check`: PASS nos dois worktrees; diff revisado, incluindo novos arquivos.

## Arquivos backend

- `app/routers/pacientes.py`
- `app/services/assistential_session_service.py`
- `app/services/pts_service.py`
- `app/services/care_lines/registry.py`
- `app/services/report_engine/{context.py,registry.py,report_service.py}`
- `app/services/report_engine/knowledge/executive_summary_engine.py`
- `app/services/report_engine/providers/{assessment_provider.py,clinical_engine_provider.py,diagnosis_provider.py,pts_provider.py,session_provider.py,timeline_provider.py,cardio_evolution_provider.py}`
- `app/services/report_engine/reports/{__init__.py,cln_001.py,cardio_v1.py}`
- `app/services/report_engine/sections/{identification.py,temporal_scope.py,cardio.py}`
- `app/services/report_engine/renderers/pdf_renderer.py`
- `tests/{test_clinical_reading.py,test_timeline.py,test_report_multiline.py}`
- Este documento.

## Arquivos frontend

- `src/components/ReportDownload.jsx`
- `src/services/pacientes.js`
- `src/pages/Paciente.jsx`
- `src/pages/cardiometabolico/PacienteCardiometabolico.jsx`
- `tests/report-multiline-integration.cjs`

## Limitações e dívida remanescente

- Sem suporte as-of: status atuais, interpretação atual e referência atual permanecem explicitamente distintos dos eventos do período.
- Fontes institucionais da Timeline ainda materializam o histórico do paciente antes do filtro do relatório. O teste exclui N+1 por registro, não comprova memória/latência ilimitadas para históricos arbitrariamente grandes.
- PTS Neuro conserva leitura por planejamento já existente; não houve refactoring geral de performance Neuro.
- A narrativa clínica Cardio (inclusive seu vocabulário) é a do engine existente, sem revalidação ou alteração de regras nesta Wave.
- Aviso preexistente Pydantic `.dict()` e warning de bundle frontend permanecem; não impediram validações.
- Fixture reproduz colunas legadas já consumidas pelos serviços institucionais; não substitui histórico real de migrations nem comprova schema de HML/PROD.
- Evidências PDF são locais e temporárias, exclusivamente sintéticas.
- Nenhuma dependência de runtime, migration ou mudança de banco compartilhado foi introduzida. Não houve push, merge ou deploy.

## Fechamento

Commits locais nos dois repositórios sobre os respectivos baselines Gate 3; hashes finais e status dos worktrees são apresentados no relatório de entrega. O diretório backend antigo incompleto e alterações não relacionadas no checkout original permanecem preservados.

Gate 4 pronto para validação humana. Não iniciar Wave 5 automaticamente.
