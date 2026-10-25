# D9.2-E12 — disparo manual (não publicado)

POST `/saude-mental/pessoas/{pessoa_id}/contextos/{contexto_id}/whatsapp/disparar-manual?instituicao_id={id}`

Autenticação canônica e ASSISTENCIAL_REGISTRAR contextual obrigatórias.
Header obrigatório `Idempotency-Key`: 16–128 caracteres ASCII alfanuméricos ou `._:-`.
Body estrito: `{"motivo":"ACOMPANHAMENTO_EXTRAORDINARIO"}` ou
`{"motivo":"SOLICITACAO_DA_PESSOA"}`. Não aceita telefone, template, autor nem bypass.

Resposta: solicitacao_id, conversa_id, tentativa_id, estado e aceitacao_meta.
ACEITO significa aceitação do transporte, não entrega. O diagnóstico D9.2 existente
continua sendo a fonte de callbacks sent/delivered/read/failed e consentimento.
HTTP 403: autorização contextual negada; 409: impedimento de negócio ou chave
reutilizada com conteúdo divergente; 422: body/header inválido; 503: resultado
indisponível. Nenhuma resposta autoriza retry automático.

Chave vinculada a instituição e usuário. Repetição exata retorna a solicitação
original, inclusive PREPARADO/EM_EXECUCAO/INCERTO; não retoma transporte.
Motivo/acompanhamento divergente na mesma chave gera conflito.

Lock transacional da chave, seguido do lock canônico por telefone. Preparação
manual e automática compartilham elegibilidade e exclusão por conversa vigente.
Tentativas PREPARADO/EM_EXECUCAO/INCERTO de ciclos anteriores bloqueiam ambos;
solicitação manual PREPARADO sem tentativa também bloqueia novos ciclos.
Conversa e solicitação são confirmadas juntas antes do transporte. O vínculo da
tentativa é confirmado junto com seu PREPARADO. Não há transação aberta durante
HTTP externo. Template e idioma são fotografados e conferidos no transporte.
O caminho manual não altera proximo_envio_em, mesmo nulo ou futuro. O automático
preserva seu cálculo semanal. Failed não encerra conversa nem altera consentimento.

## Bloqueio de segurança pendente

Não existe fonte canônica separada de autorização prévia de comunicação:
configure grava PENDENTE, receive(SIM) grava CONSENTIDO para um check-in.
`require_prior_authorization` falha fechado com
`PRIOR_WHATSAPP_AUTHORIZATION_UNAVAILABLE`, independentemente desses estados.
Não existe configuração, campo HTTP ou privilégio que contorne o gate.
Os testes de sucesso substituem exclusivamente esse gate em memória; não provam
opt-in em HML. Publicação operacional: NO-GO até definição e implementação da
fonte canônica de evidência. Não habilitar inferindo PENDENTE ou CONSENTIDO.

Migration aditiva `d92e12_whatsapp_manual`, pai `d92a_whatsapp_persistencia`.
Sem carga histórica e sem downgrade destrutivo. Aplicação exige schema atualizado.
Novo template UTILITY não ativado; transportador usa configuração existente.
O snapshot de template/idioma permite evolução posterior do contrato de variáveis,
mas suporte efetivo à variável BODY e ativação exigem etapa posterior.

Testes: definir DATABASE_URL e M0_TEST_POSTGRES_URL com a mesma credencial privada
para PostgreSQL descartável 127.0.0.1:55620/m0_baseline; nunca DEMO persistente.
Executar `PYTHONPATH=.:tests .venv-e12/bin/python -m pytest -q tests/test_whatsapp_manual.py`.
Fixtures criam bancos d92a_<uuid>, aplicam migrations e removem só os bancos próprios.

## Evidências locais — 25/10/2026

- 123 PASS, 0 FAIL, 0 SKIP: E12 (21), persistência (11), transporte (15),
  callbacks (12), diagnóstico (9), Saúde Mental (19), segurança (17),
  diagnósticos de transporte (9), baseline (10).
- 50 PASS, 0 FAIL, 0 SKIP: Neuro, canais Cardio e Registro Diário.
- PostgreSQL 18.6 descartável, loopback 55620; 5 bancos d92a próprios
  removidos e ausência confirmada por conexão independente.
- Sintaxe de 13 arquivos Python e git diff --check aprovados.
- Head canônico único d92e12_whatsapp_manual, pai d92a_whatsapp_persistencia.
- Warnings preexistentes: Config Pydantic obsoleto e urllib3/LibreSSL local.
- Relatórios JUnit: /private/tmp/e12-results.xml e /private/tmp/e12-legacy-results.xml.
- Sem Meta real, publicação, migration compartilhada ou alteração do checkout main.

## Inventário da entrega

- `alembic_canonical/versions/d92e12_whatsapp_manual.py`
- `app/models/__init__.py`
- `app/models/whatsapp_manual.py`
- `app/routers/whatsapp_mental.py`
- `app/schemas/whatsapp_manual.py`
- `app/services/whatsapp_convite_envio.py`
- `app/services/whatsapp_manual.py`
- `app/services/whatsapp_mental.py`
- `app/services/whatsapp_sender_service.py`
- `docs/d92-e12-disparo-manual.md`
- `tests/test_m0_baseline.py`
- `tests/test_whatsapp_convite_persistence.py`
- `tests/test_whatsapp_manual.py`
- `tests/test_whatsapp_mental.py`

## Continuidade E12C

A pendência de gate fixo descrita acima registra o resultado histórico da E12B.
A E12C substitui esse gate por autorização persistida e aplica a mesma verificação
aos caminhos automáticos e reenvios. Consulte `d92-e12c-autorizacao-comunicacao.md`.
Os testes de sucesso agora registram evidências sintéticas pelo serviço canônico,
sem substituir a autorização por mocks.
