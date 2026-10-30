# Agenda de check-ins — Etapa 2A / Bloco A

## Limites

Persistência e gestão humana da agenda, sem executor, cron, worker, chamada Meta,
reconciliação ou classificação de ocorrências perdidas. Uma ocorrência AGENDADO
não autoriza envio. `eligible_ids()` continua excluindo programações configuradas;
`prepare(manual=False)` continua retornando `WEEKLY_EXECUTION_NOT_ENABLED`.
`/disparar-manual` não consome nem modifica agenda.

## Contrato

Base: `/saude-mental/pessoas/{pessoa_id}/contextos/{contexto_id}/whatsapp`, sempre
com `instituicao_id`. Autenticação e autorização contextual humana existentes.

GET existente acrescenta `programacao_data_fim` (data civil ou null),
`programacao_versao` (inteiro >= 0), `execucao_automatica_ativa` (sempre false).

PUT `/programacao`:

```json
{
  "dia_semana": 4,
  "horario_local": "19:00",
  "programacao_ativa": true,
  "programacao_data_fim": "2027-10-30",
  "versao_esperada": 0
}
```

- Segunda=0, domingo=6; horário civil sem offset/segundos.
- Adesão explícita: data-fim não nula e versão atual obrigatórias.
- Até 12 meses-calendário a partir de hoje em America/Cuiaba; 29/02 é limitado a
  28/02 no ano seguinte. Data-fim inclusiva pela data local, persistência UTC.
- Somente instantes estritamente futuros. Nenhuma recuperação de semanas passadas.
- Ativação sem ocorrência futura: 409 `AGENDA_NO_FUTURE_OCCURRENCES`.
- Data fora da vigência: 409 `AGENDA_END_OUT_OF_RANGE`; entrada malformada: 422.
- Versão ausente/divergente na agenda: 409 `SCHEDULE_VERSION_CONFLICT`, sem efeitos.
  O cliente deve consultar o estado antes de decidir reenviar, sem sobrescrever.
- Payload idêntico com versão atual: no-op, sem versão/evento/data novos.
  Repetir a versão anterior retorna 409, inclusive após resposta perdida.
- Mudança material incrementa versão uma vez, sob lock do acompanhamento.
- Data-fim omitida após adesão conserva o valor; null explícito retorna 409
  `AGENDA_END_REQUIRED`. Não há desadesão silenciosa para o modo legado.
- Payload antigo, sem data-fim, em acompanhamento ainda sem agenda mantém o
  comportamento anterior e não cria ocorrências. Após adesão, edição exige versão.
- Pausa conserva dia/horário/data-fim, não pausa o acompanhamento assistencial.
  É permitida mesmo após o término da vigência. Retomada exige ocorrência futura.

GET `/agenda?instituicao_id=2&limite=50&offset=0`:

- `limite`: 1–100; `offset`: 0–100000. Ordenação por previsto_em/id.
- Retorna acompanhamento_id, programacao_versao, execucao_automatica_ativa=false,
  impedimentos atuais, itens, limite, offset e proximo_offset (null no fim).
- Itens expõem identidade, instante, estado persistido, versão, conversa opcional,
  timestamps e código de motivo. Sem telefone, conteúdo clínico ou credenciais.
- Leitura não altera estado. Ocorrências vencidas permanecem com estado histórico;
  AGENDADO não significa elegível. Impedimentos atuais são informação separada.
- Paginação não representa snapshot entre requisições: uma edição concorrente pode
  mudar a versão; clientes devem reiniciar a paginação se a versão mudar.
- Não existe `/agenda/reconciliar`.

## Estados, segurança e transações

| Evento | Efeito em ocorrências futuras não assumidas |
|---|---|
| Configuração ativa sem impedimento conhecido | AGENDADO |
| Pausa da programação / acompanhamento | BLOQUEADO |
| Comunicação interrompida no acompanhamento | BLOQUEADO |
| Revogação E12C, encerramento, troca de telefone | CANCELADO |
| Reprogramação | CANCELADO fora da nova grade; cria/reutiliza a nova grade |
| Retomada explícita, após remoção dos impedimentos | AGENDADO nos instantes válidos |

BLOQUEADO/CANCELADO futuro pode ser reutilizado apenas sem conversa ou timestamps
de processamento. Unicidade `(acompanhamento_id, previsto_em)` atravessa versões.
Passado, ocorrências assumidas/processadas e referências clínicas não são alterados.
PROCESSANDO, EXECUTADO e PERDIDO são reservados: nenhum comando desta etapa os produz.

PARAR preventivo no transporte conserva a semântica multi-line: não atribui a
interrupção a outras pessoas/instituições, não altera suas agendas e aparece como
impedimento efetivo na leitura. PARAR contextual invalida a agenda na transação do
ledger. Retomar a programação não remove bloqueio nem concede E12C. Reativar
comunicação/acompanhamento também não ressuscita automaticamente ocorrências;
pausa/retomada explícita da programação reavalia impedimentos. Consentimento
PENDENTE não impede planejar um convite autorizado por E12C.

Ordem preservada: transporte → identidade assistencial → acompanhamento → agenda
por id. Hooks são chamados com locks já adquiridos, sem novo lock de transporte.
Configuração, ocorrências, auditoria e ponteiro são atômicos. O ponteiro
`proximo_envio_em` recebe o menor AGENDADO futuro durante uma edição; pausa ou
invalidação o limpa. GET não atualiza ponteiro vencido. Eventos de segurança não
alteram a versão das preferências; qualquer edição reavalia o ledger atual.

## Persistência e publicação futura

Migration `mh_agenda_v1`, filha de `mh_weekly_config_v1`, exclusivamente aditiva:
- data-fim nullable, versão default 0, constraints no acompanhamento;
- tabelas de ocorrências/auditoria com FKs RESTRICT e índices;
- FK composta impede vincular conversa de outro acompanhamento;
- auditoria append-only protegida contra UPDATE/DELETE/TRUNCATE;
- mesmo writer fence E14B nas duas tabelas novas.

Não converte programações antigas, não cria ocorrências e não ativa execução.
Downgrade destrutivo recusado; recuperação futura requer procedimento aprovado.
A implantação exigirá migration antes do binário novo e revisão das permissões
DML/sequence da identidade HML, sem ampliar permissões nesta etapa. Não manter
escritores antigos em paralelo após a adesão de acompanhamentos à agenda.

## Arquivos da entrega

- `alembic_canonical/versions/mh_agenda_v1.py`
- `app/models/__init__.py`
- `app/models/whatsapp_agenda.py`
- `app/models/whatsapp_contextual.py`
- `app/routers/whatsapp_mental.py`
- `app/schemas/whatsapp_mental.py`
- `app/services/whatsapp_agenda.py`
- `app/services/whatsapp_autorizacao.py`
- `app/services/whatsapp_comunicacao.py`
- `app/services/whatsapp_mental.py`
- `app/services/whatsapp_programacao.py`
- `docs/whatsapp-agenda-etapa2a.md`
- `tests/test_m0_baseline.py`
- `tests/test_whatsapp_activation.py`
- `tests/test_whatsapp_agenda.py`
- `tests/test_whatsapp_comunicacao.py`
- `tests/test_whatsapp_convite_persistence.py`
- `tests/test_whatsapp_mental.py`

## Validação local — 30/10/2026

Base: `9a6e2c854ca67a388f0550045f145d0cf957dc27`, branch `homolog`, cópia isolada.

- 277 testes aprovados, 0 falhas, 0 erros, 0 ignorados, em PostgreSQL 18.6
  descartável local (284,697 s na execução final).
- 16 testes novos da agenda, cobrindo calendário, UTC/data-fim inclusiva, vigência,
  idempotência, versão/concorrência, reprogramação, pausa/retomada, preservação do
  passado e de ocorrências assumidas, autorização/isolamento, PARAR contextual e
  preventivo, revogação/troca de destino, fluxo manual, migration e integridade.
- Regressão de programação anterior, WhatsApp Mental, disparo manual, persistência
  de tentativas, check-in clínico, autorização, comunicação, ativação e locks.
- Upgrade real de `mh_weekly_config_v1` para `mh_agenda_v1` em banco descartável:
  configuração ativa anterior preservada, data-fim null/versão 0, nenhuma conversão.
- Chamadas HTTP externas bloqueadas nos fixtures; entregas dos testes de regressão
  usam mocks. Nenhum envio real e nenhuma operação em HML/PROD.
- Comparação AST comprovou `authorized`, `eligible_ids`, `prepare`,
  `deliver_invitation` e `receive` inalterados. Arquivos de disparo manual, entrega,
  PARAR e resolução multi-line também permaneceram idênticos à base.
- Sintaxe dos arquivos Python e `git diff --check` aprovados.
- Inventário de bancos locais preservado; nenhum banco criado pela suíte permaneceu.

A primeira rodada ampla encontrou apenas uma asserção de head desatualizada em
um teste de comunicação. Ela foi ajustada à revisão da fixture; a rodada final
completa passou. Nenhuma regra funcional foi relaxada para fazer o teste passar.
