# CARDIO-005 — contrato de persistência Cardio

Implementação local sobre backend 60aea08abb996c3465f057a44520e753ff1c8dd0, branch homolog. Sem commit, promoção ou acesso HML. Contrato físico dos snapshots confirmado pelo responsável; não inferido das fixtures.

## Contrato final

- Glicemias, pressões, peso, altura, atividade física, sono e humor: somente respostas_registro. Nenhuma coluna nova; modulo_id continua sendo o contexto estrutural, sem projeção redundante modulo.
- score_clinico numeric, risco/protocolo varchar, leitura_clinica/observacoes text: nullable, sem defaults, preservados nas fixtures e na escrita. Os quatro derivados são snapshots da observação; observacoes é texto complementar fora do engine.
- ClinicalReading atual permanece baseada em respostas. E.1 peso/altura da mesma observação e IMC derivado não foram alterados. Engine e thresholds intactos.
- RegistroAdapter histórico inalterado: segue lendo leitura_clinica/protocolo do evento. Novo registro não substitui snapshot de evento anterior.

## Consumidores

- /cardiometabolico/mapa-risco: ClinicalReadingService.get_readings em lote; população por vínculo ativo e escopo institucional via list_patients. Requer usuário autenticado e autorização existente da Linha. Agrupa por identidade da clínica, preserva campos existentes e top 3 por score; acrescenta critico/indisponivel. Ausência não vira baixo/zero/preventivo; média considera somente scores disponíveis e retorna None quando nenhum existe. Ordenação principal de clínicas por alto preservada.
- APP GET registros-cardio: consumidor adicional registrado no Backlog antes da mudança. Mantém filtro de origem, vínculo de responsável, snapshots e formato; medições agora vêm de evolution/respostas do próprio record_id, nunca da leitura atual de outro evento. Leitura em lote, sem consulta por registro.
- app/services/cardiometabolico.py contém helper legado que ainda referencia medições físicas; nenhum chamador encontrado na aplicação. Não removido, não declarado morto. app/scripts/recalcular_scores_cardio.py reescreve snapshots; não executado nem alterado. Registrados em CARDIO-006 para auditoria de usos externos/semântica histórica.

## Fixtures

Corrigidas test_daily_record, test_cardio_longitudinal, test_cardio_channels, test_whatsapp_postgres e fixtures/cardio_gate1_runtime. Apenas as cinco extensões físicas confirmadas são criadas; não há colunas de medições ou modulo textual. Nenhuma migration nova. A adaptação preexistente de precisão numérica das respostas nos testes PostgreSQL foi preservada; não constitui comprovação nova da precisão HML.

## Validação executada

Runtime Python 3.9: /Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/neuro_mvp_backend/venv/bin/python.

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests <python> -m unittest test_daily_record test_cardio_longitudinal test_clinical_reading`: 93 descobertos, 82 PASS, 11 skips PostgreSQL (etapa intermediária).
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests <python> -m unittest test_cardio_channels test_whatsapp_security`: 22 PASS após corrigir erro introduzido na edição da fixture.
- Compilação em memória + `ast.parse(..., feature_version=(3,9))`: 9 arquivos Python modificados PASS.
- Suíte completa FINAL: `PYTHONDONTWRITEBYTECODE=1 <python> /private/tmp/cardio005_tests.py`, runner equivalente a `unittest.defaultTestLoader.discover('tests')`: **370 PASS, zero skips**, 41.278s. Log: /private/tmp/cardio005-tests18.log.
- PostgreSQL 18 descartável Docker, somente 127.0.0.1:55439, sem volumes de dados compartilhados. PGPORT=55439; CARE_PLAN_TEST_POSTGRES_URL, REMEDIATION_POSTGRES_URL, CARDIO_GATE1_POSTGRES_URL, WHATSAPP_TEST_POSTGRES_URL, SESSION_TEST_POSTGRES_URL, CARDIO_GATE3_POSTGRES_URL, CARDIO_GATE4_POSTGRES_URL = postgresql+psycopg2://gate1@127.0.0.1/gate1_test; WAVE3_TEST_POSTGRES_URL = postgresql+psycopg2://wave3@127.0.0.1/wave3_test; WAVE5_TEST_POSTGRES_URL = postgresql+psycopg2://wave5@127.0.0.1/wave5_test.
- Runner acrescenta ao final de sys.path o site-packages do runtime Codex para pypdf, preservando precedência do venv. Sem instalação/alteração de dependências.
- Tentativas intermediárias: conexão local bloqueada pelo sandbox; reexecutada com permissão. PostgreSQL 16 falhou em 11 testes que exigem versão 18 e revelou leitura física do APP (corrigida). Não tratados como PASS.
- Cobertura: criação/edição, todas as respostas, IMC, observações, snapshots históricos, leitura atual independente de snapshots adulterados, mapa/APP, rollback, Neuro, WhatsApp, clínica/Linha, vínculos inativos, reports e concorrência.
- Orçamento Cockpit: 14 consultas para 3 e 53 pacientes (SQLite/PostgreSQL); profissional Neuro/Cardio 14/16 antes e após +50 pacientes. Mapa tem teste separado de consultas constantes e limite 10.
- Alembic single head: 8c01a0d1a004. Engines Neuro/Cardio, adapter histórico, ClinicalReading e E.1 comparados byte a byte contra HEAD: inalterados.
- Frontend limpo e inalterado; build/ESLint frontend não aplicáveis. Nenhuma configuração de linter Python encontrada; compile/AST e diff check executados. Warning ambiental urllib3/LibreSSL permanece.

## Governança / limites

CARDIO-005 EM EXECUÇÃO, aguardando validação humana e operacional. CARDIO-001 permanece EM EXECUÇÃO; CARDIO-002 intocado. DATA-002 registra drift físico versus models/migrations; CARDIO-006 registra convergência histórica futura. Nenhuma correção de drift, migration nova, massa HML, deploy ou operação remota realizada. SQL dos testes restrito ao ambiente descartável sintético.
