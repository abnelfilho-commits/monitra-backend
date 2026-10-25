# D9.2-E12C — autorização prévia de comunicação (não publicada)

## Estados separados

- Acompanhamento ATIVO representa configuração operacional; não comprova opt-in.
- O histórico `whatsapp_autorizacoes_comunicacao` comprova o registro profissional
  da autorização do canal com referência à evidência. Ausência bloqueia convites.
- SIM mantém o aceite individual e o comportamento assistencial existente; não
  cria nem renova autorização de comunicação. O campo legado consentimento_status
  permanece compatível e não é usado como substituto do histórico de autorização.
- Revogação acrescenta REVOGADA ao histórico, sem apagar autorizações anteriores.
  PARAR mantém o encerramento existente e acrescenta evento vinculado à conversa
  e ao recibo autenticado de mensagem. Não atribui autoria profissional ao titular.

## API contextual

Prefixo: `/saude-mental/pessoas/{pessoa_id}/contextos/{contexto_id}/whatsapp`.
Query obrigatória `instituicao_id`. Autenticação canônica obrigatória.

- POST `/autorizacao-comunicacao`: ASSISTENCIAL_REGISTRAR contextual.
- POST `/autorizacao-comunicacao/revogar`: mesma autorização de escrita.
- GET `/autorizacao-comunicacao`: ASSISTENCIAL_LER contextual; estado e histórico.

POSTs exigem `Idempotency-Key` de 16–128 caracteres ASCII alfanuméricos ou `._:-`.
O corpo de registro exige exclusivamente:

- `origem`: PRESENCIAL, DOCUMENTO_ELETRONICO ou CANAL_EXTERNO;
- `obtida_em`: instante com fuso explícito, não futuro, normalizado em UTC;
- `referencia_evidencia`: identificador opaco do documento/protocolo, 8–200
  caracteres ASCII alfanuméricos ou `._:-`, sem URL com credencial nem conteúdo;
- `evidencia_sha256`: hash SHA-256 hexadecimal minúsculo do artefato conservado;
- `evidencia_verificada`: booleano verdadeiro, atestação explícita do profissional.

Revogação recebe somente `motivo`: SOLICITACAO_TITULAR ou ERRO_REGISTRO.
Telefone, autor, estado, template e bypass não são aceitos no body.
Identidades, instituição, paciente e contexto são resolvidos no servidor.

HTTP: 200 registro/repetição/leitura; 401/403 não autorizado; 422 payload inválido;
409 conflito/impedimento; 503 resultado indisponível (não repetir automaticamente).
Repetições retornam o mesmo evento, `repetido=true` e `estado_atual`; repetir uma
concessão antiga depois da revogação não reativa nada.

## Limite da evidência

Não existe repositório documental canônico integrado. Reutiliza-se o padrão de
referência auditável da identidade, sem reutilizar suas permissões administrativas.
O serviço valida formato, hash, tempo, autoria e integridade, mas não busca arquivos
externos nem certifica sua autenticidade. O profissional autorizado deve consultar
uma evidência real, conservada e recuperável pela instituição antes de atestar.
Um hash não prova sozinho que houve autorização. Não registrar referências fictícias
em HML; as referências TEST-ONLY dos testes existem apenas nas fixtures descartáveis.

## Integridade e concorrência

Ledger append-only, com trigger PostgreSQL recusando UPDATE/DELETE, cadeia de
antecessores, raiz única por acompanhamento e FKs compostas de contexto/instituição.
Não há backfill. Histórico anterior permanece sem autorização até registro explícito.
Chave por instituição/usuário, fingerprint de conteúdo, lock da chave e locks canônicos
por telefone/contexto/acompanhamento. Não há commits internos no registro/revogação;
a rota confirma a operação. Resultado incerto pode ser reconciliado pela mesma chave.

Somente uma autorização ativa por cadeia; nova autorização após revogação exige
nova evidência obtida depois da revogação e hash ainda não utilizado nesse acompanhamento.
PARAR/encerramento não são desfeitos por novo registro. Troca de telefone revoga a
permissão anterior; o fingerprint do destino também bloqueia transferência indevida.
Este fingerprint é dado derivado, não anonimização, e não é retornado pela API.

O gate protege seleção automática, prepare, disparo manual, /disparar e
/reenviar-convite, sendo revalidado antes do transporte. Cada tentativa nova registra
`autorizacao_comunicacao_id`; tentativas históricas permanecem com NULL.
Nenhuma transação permanece aberta durante HTTP. Revogação antes da transição
EM_EXECUCAO bloqueia a chamada; uma operação já em execução externa não pode ser
recolhida. A confirmação de PARAR e respostas reativas existentes são preservadas;
a proteção de convites não é aplicada indevidamente ao Registro Diário Neuro/Cardio.

O endpoint manual não cria autorização. Seu agendamento continua intacto. Não há
ativação de template UTILITY nem retentativa automática por falha/timeout/131049.

## Migration e implantação futura

`d92e12c_autorizacao_whatsapp` é filha de `d92e12_whatsapp_manual`. Acrescenta uma
tabela, sua função/trigger de imutabilidade e FK nullable em whatsapp_convite_envios.
Sem alterações de registros antigos, sem concessões automáticas e sem downgrade
que remova evidências. A publicação requer aplicar a cadeia aditiva antes do código,
por autorização separada; todos os acompanhamentos sem evidência ficam bloqueados.

Testes utilizam PostgreSQL 18 descartável em 127.0.0.1:55620 e Meta simulada.
DATABASE_URL e M0_TEST_POSTGRES_URL devem apontar para a mesma base de testes
m0_baseline, com credencial privada; fixtures criam e removem bancos próprios.

## Evidências executadas — E12C

- Matriz D9.2, E12B, E12C, baseline, Neuro/Cardio e Registro Diário: 203 PASS,
  0 FAIL, 0 SKIP (`/private/tmp/e12c-final.xml`).
- Compatibilidade da migration sobre E12B com tentativa ACEITO preexistente:
  1 PASS (`/private/tmp/e12c-migration.xml`); campos anteriores preservados,
  autorização NULL e ledger vazio, sem backfill.
- Total distinto: 204 PASS. PostgreSQL 18.6 descartável; transporte Meta simulado.
- Conferência independente dos sete bancos identificados nos logs de descarte
  dessas execuções: nenhum permanece em pg_database.
- git diff --check aprovado. Warnings de Config Pydantic legado e LibreSSL local;
  nenhuma falha ou skip. Nenhuma operação em HML, PROD ou DEMO persistente.

### Inventário específico E12C

Novos: migration d92e12c_autorizacao_whatsapp.py; model, schema e service
whatsapp_autorizacao.py; tests/test_whatsapp_autorizacao.py;
tests/whatsapp_authorization_fixture.py; este documento.

Incrementais: app/models/__init__.py; app/models/whatsapp_convite.py;
app/routers/whatsapp_mental.py; app/services/whatsapp_manual.py;
app/services/whatsapp_mental.py; app/services/whatsapp_convite_envio.py;
app/services/whatsapp_ingress.py; tests/test_m0_baseline.py;
tests/test_whatsapp_convite_persistence.py; tests/test_whatsapp_convite_envio.py;
tests/test_whatsapp_manual.py; tests/test_whatsapp_mental.py;
docs/d92-e12-disparo-manual.md.

Os arquivos anteriores da E12B foram preservados. O estado Git combinado das
etapas contém 11 arquivos modificados e 13 não rastreados, staging vazio,
branch homolog, HEAD b0581fa0ddf9fc04aa18c750cb408b14422a8b6a.
