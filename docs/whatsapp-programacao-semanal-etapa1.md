# Programação semanal Mental — Etapa 1

Contrato de configuração apenas. Não existe executor nem identidade técnica nesta entrega.
`programacao_ativa=true` representa a preferência do profissional, não automação operacional.

## API

`PUT /saude-mental/pessoas/{pessoa_id}/contextos/{contexto_id}/whatsapp/programacao?instituicao_id={id}`

Corpo completo, sem campos adicionais:

```json
{"dia_semana":4,"horario_local":"19:00","programacao_ativa":true}
```

- Dia: inteiro 0 (segunda) a 6 (domingo).
- Hora civil, precisão de minuto, sem offset, sempre `America/Cuiaba`.
- Configuração/alteração/retomada ativa calcula a próxima ocorrência estritamente futura em UTC.
- Repetição idêntica preserva a ocorrência, inclusive vencida, e a autoria anterior.
- Pausa: enviar a preferência com `programacao_ativa=false`; mantém dia/hora e limpa `proximo_envio_em`. Não pausa o acompanhamento e não cancela conversas.
- Retomada: reenviar com `true`; não recupera semanas anteriores.
- Autoria das alterações: usuário autenticado, nunca recebido do cliente.
- PUT e GET existente retornam os quatro campos novos, além dos campos anteriores.
- 422: contrato inválido; 403: escopo/permissão indisponível; 409: acompanhamento ausente, fechado/revogado ou destino alterado concorrentemente.
- Configuração não concede consentimento nem E12C e não remove bloqueios. A autorização humana contextual existente é revalidada sob locks canônicos.

## Separação dos caminhos de envio

O campo `dia_semana` identifica configuração nova, ativa ou pausada. Esses acompanhamentos não são selecionados por `eligible_ids()`. `prepare(manual=False)` recusa explicitamente com `WEEKLY_EXECUTION_NOT_ENABLED`; portanto `/disparar` responde 409 para eles. Isso é uma restrição deliberada e documentada até a aprovação do executor, não uma ativação da automação.

Acompanhamentos ainda não configurados mantêm o comportamento legado. `/disparar-manual` permanece independente: não altera preferências nem próxima ocorrência. O reenvio de uma conversa já preparada mantém suas regras existentes e não consome a programação.

`due_in_window()` verifica **somente elegibilidade temporal**: ocorrência vencida até duas horas inclusive, programação ativa. Não autoriza envio. `next_occurrence(..., allow_late=True)` conserva uma ocorrência dentro da tolerância e salta semanas perdidas fora dela; a forma padrão calcula a próxima ocorrência futura, ancorada no horário civil. Não há consumo de ocorrências nem registro de perdas nesta etapa; isso pertence ao executor futuro.

## Migration e operação

`mh_weekly_config_v1`, após `e14b_close_v1`: quatro colunas, FK de autoria e constraints de coerência/dia. Linhas existentes recebem apenas o default `programacao_ativa=false`; dia, horário e autoria ficam nulos. Datas anteriores e demais dados permanecem iguais. Não há backfill nem ativação automática.

Não há downgrade destrutivo: remover o marcador de configuração reabilitaria caminhos legados em programações pausadas e perderia preferências. Recuperação deve ser progressiva.

Antes da futura disponibilização da API, aplicar a migration e atualizar todas as instâncias do backend; não operar com binários antigos, que desconhecem a exclusão de programações novas. Deploy e migration em HML exigem autorização posterior. Nenhuma alteração de `authorized()`, `AutorizacaoContextualService` ou das verificações de `deliver()` foi necessária.

## Arquivos da entrega

- `app/models/whatsapp_contextual.py`: quatro campos e constraints.
- `alembic_canonical/versions/mh_weekly_config_v1.py`: migration aditiva.
- `app/schemas/whatsapp_mental.py`: contrato de configuração e GET expandido.
- `app/services/whatsapp_programacao.py`: cálculo temporal e configuração autorizada.
- `app/services/whatsapp_mental.py`: exclusão explícita da execução legada para programações novas.
- `app/routers/whatsapp_mental.py`: PUT de programação.
- `tests/test_whatsapp_programacao.py`: cálculo, contrato, modelo, configuração e isolamento.
- `tests/test_whatsapp_manual.py`: preservação da programação no envio extraordinário simulado e replay.
- `tests/test_whatsapp_convite_persistence.py`: seed com colunas históricas, preservação dos dados antigos e defaults novos.
- `tests/test_m0_baseline.py`, `tests/test_whatsapp_mental.py`, `tests/test_whatsapp_activation.py`: atualização da revisão esperada e proteção contra downgrade.
- Este documento: contrato e limitações operacionais.

## Validação local

- Suíte ampliada: 143 testes aprovados, zero falhas/erros/ignorados.
- Após o ajuste final de salvamento com data ausente: 35 testes direcionados aprovados, incluindo programação e regressão extraordinária.
- PostgreSQL 18 descartável em loopback; bancos criados pelos testes removidos e inventário preservado.
- Compilação Python dos arquivos alterados e `git diff --check`: aprovados.
- Nenhuma chamada real à Meta, migration em HML, deploy, commit ou push.
- Base remota homolog confirmada: `670550fd8b093b690a12c7119e42167fd740cfc7`.

Uma troca de destino pelo fluxo existente pode limpar `proximo_envio_em`. Nesse caso, um salvamento explícito da configuração ativa restaura a próxima ocorrência futura; uma ocorrência existente, mesmo vencida, continua preservada em uma repetição idêntica.
