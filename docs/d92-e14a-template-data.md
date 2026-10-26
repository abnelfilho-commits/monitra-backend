# E14A — Template de acompanhamento com data

Preparação local; não ativa configuração nem autoriza envio.

Após testes e autorização de publicação, configurar exclusivamente no ambiente
pretendido:

- `WHATSAPP_MENTAL_TEMPLATE_NAME=integra_care_checkin_acompanhamento_v1`
- `WHATSAPP_MENTAL_TEMPLATE_LANGUAGE=pt_BR`

O template anterior `integra_care_checkin_bem_estar` continua suportado sem BODY
parameters. Nomes desconhecidos ou idiomas diferentes de pt_BR são recusados.
Não existe fallback silencioso entre templates.

A variável é `whatsapp_conversas_contextuais.data_referencia`, lida sob o lock da
conversa antes do envio. É uma data civil: não converter para UTC ou Cuiabá.
A preparação existente atribui essa data a partir do relógio UTC do banco; esta
etapa não muda essa regra nem recalcula datas históricas. Portanto, perto da
virada UTC ela pode diferir da data local de Cuiabá. Alterar essa semântica seria
uma decisão separada. O transporte rejeita datetime e data ausente para o novo
modelo, em vez de usar a data corrente ou um exemplo fixo.

O único componente do novo template é BODY com um parâmetro text DD/MM/AAAA.
A identidade nome/idioma é revalidada no transportador nos caminhos manual e
automático. SIM, PARAR, autorização, calendário e estados D9.2 não mudam.

Validação local (sem credenciais reais, Meta simulada):

    PYTHONPATH=tests .venv-e12/bin/python -m unittest test_whatsapp_template_date test_whatsapp_invitation_diagnostics test_whatsapp_security test_whatsapp_mental

O teste PostgreSQL `DeliveryTests.test_dated_template_uses_persisted_conversation_reference`
exige as URLs iguais explicitamente aprovadas pelos testes para o PostgreSQL
descartável em 127.0.0.1:55620/m0_baseline. Não usar HML ou DEMO persistente.
