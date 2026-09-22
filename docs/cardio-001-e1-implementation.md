# CARDIO-001 — E.1 — implementação local

Data: 22/09/2026. Sem commit/push/HML. Backend base 64aa559cdc4a0f8758c917f93e8195d5b7429f00; frontend base 13123a698f20ccd168c8503efda75ed82a5e7dd3.

## Contrato e escopo

Peso em kg, altura em metros, mesma observação, valores únicos/positivos/finitos, IMC arredondado a uma casa. Labels não definem unidade. Sem conversão de centímetros, altura cadastral, carry-forward ou altura futura. A função project_observation existente permanece o único cálculo. ClinicalReading Cardio reutiliza essa função e expõe metadata.imc/imc_availability/imc_units; altura não entra nos inputs de risco. Ausência permanece None. Não foi adicionado campo universal ao contrato, campo manual ou coluna IMC.

O formulário profissional captura altura opcional com step 0.01; mostra Peso (kg)/Altura (m), preserva normalização existente de vazio para null e navegação. Provider, engines clínicos, Report Engine, Cockpit e Timeline não foram alterados. Não foi criada migration nem alterado metadado HML/cadastro de paciente; esses itens do design anterior não são necessários para o cálculo do escopo cirúrgico e dependem de fechamento explícito de escopo.

## Validação executada

Python: /Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/neuro_mvp_backend/venv/bin/python (3.9).

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests <python> -m unittest test_clinical_reading test_daily_record test_cardio_longitudinal`: 90 descobertos, 80 PASS, 10 PostgreSQL skipped. Repetido após ampliar temporalidade; mesmo resultado.
- `PYTHONDONTWRITEBYTECODE=1 <python> -m unittest discover -s tests`: primeira execução 365 descobertos, 278 PASS, 86 skipped, 1 erro de ambiente (pypdf ausente).
- Reexecução via `unittest.defaultTestLoader.discover('tests')` / `TextTestRunner`, acrescentando ao FINAL de sys.path `/Users/Abnel/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages` para pypdf disponível: 365 descobertos, 279 PASS, 86 skipped, zero erros. Dependências do venv mantiveram precedência. Compile em memória + ast Python 3.9: 5 arquivos PASS.
- Os 86 skips PostgreSQL NÃO foram executados/validados. Fixtures locais de persistência usaram SQLite em memória; nenhuma conexão HML ou SQL operacional foi executada.
- `PLAYWRIGHT_MODULE=/Users/Abnel/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright node tests/cardio-anthropometry.cjs`: 4 casos PASS, decimal/vazio, sem altura cadastral, sem campo manual IMC, retorno contextual preservado. HTTP inteiramente interceptado com dados sintéticos.
- Mesmo prefixo com `node tests/professional-cockpit.cjs`: 59 cenários PASS, incluindo Neuro/Multi-Line.
- Mesmo prefixo com `node tests/cardio-cockpit-v2.cjs`: 55 cenários PASS; limite mobile do shell já conhecido permanece UX-001.
- `npm run build`: PASS, 876 módulos; warning de bundle >500kB permanece TECH-001.
- `./node_modules/.bin/eslint src/pages/cardiometabolico/RegistroDiarioCardiometabolico.jsx tests/cardio-anthropometry.cjs`: 1 erro + 1 warning no lifecycle preexistente. Comparação por `git show HEAD:<arquivo> | eslint --stdin --stdin-filename <arquivo> -f json` confirmou ambas as ocorrências anteriores. Sem correção de lint fora do escopo; TECH-004 registrado.
- `git diff --check`: PASS nos dois repositórios.

## Evidência dos cenários

82/1.75 -> 26.8; 80/2 -> 20.0; 80/1.8 -> 24.7; 100/1.7 -> 34.6. Peso sozinho, altura sozinha, ambos ausentes, duplicidade, zero/negativo/não finito -> IMC indisponível. Registros anteriores/posteriores não combinam medições; mudança de cadastro e label não modifica resultados históricos. Persistência pelo DailyRecordService seguida de read_cardio produz metadata.imc=26.8 e score=0/risco baixo. Altura sozinha não fabrica risco baixo. Lote preserva orçamento existente: 14 consultas para 3 e 53 pacientes em SQLite.

## Gate e pendências

Implementação e regressões locais disponíveis PASS, com limitações explícitas: PostgreSQL não executado, lint preexistente não passa globalmente e HML/metadados não alterados. Não declarar liberação HML nem validação PostgreSQL. CARDIO-001 permanece EM EXECUÇÃO aguardando validação humana/fechamento; sem SHA de resolução pois commit proibido. CARDIO-002 e booleanos permanecem separados e intocados. Massa congelada.
