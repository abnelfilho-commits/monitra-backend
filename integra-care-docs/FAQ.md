# Perguntas Frequentes --- Integra Care

> **Versão:** 1.0.0\
> **Empresa:** Meyio DDS Digital\
> **Documento:** FAQ.md\
> **Status:** Oficial

------------------------------------------------------------------------

# 1. Objetivo

Centralizar as dúvidas mais frequentes sobre o Integra Care, facilitando
o uso da plataforma, apoiando treinamentos e reduzindo a necessidade de
suporte para questões recorrentes.

# 2. Sobre a Plataforma

## O que é o Integra Care?

O Integra Care é uma **Plataforma Modular de Gestão Longitudinal de
Linhas de Cuidado**.

Ele apoia organizações de saúde no planejamento, execução,
acompanhamento e análise da assistência aos pacientes.

## O Integra Care é um prontuário eletrônico?

O Integra Care possui recursos de acompanhamento clínico e registro
longitudinal, mas sua proposta vai além do registro documental.

A plataforma integra planejamento assistencial, PTS, agenda de cuidados,
avaliações, intervenções, Timeline, indicadores, analytics e dashboards.

## Quais linhas de cuidado estão disponíveis?

Atualmente:

-   Neurodesenvolvimento
-   Cardiometabólico

A Linha de Cuidado Oncológica está em planejamento.

## É possível adicionar novas linhas de cuidado?

Sim. A arquitetura do Integra Care foi concebida para permitir a
expansão para novas linhas de cuidado sobre um núcleo tecnológico
compartilhado.

## O que é Registro Longitudinal?

É o acompanhamento estruturado da evolução do paciente ao longo do
tempo, reunindo eventos relevantes da sua jornada assistencial.

## O que diferencia o Integra Care de sistemas tradicionais?

A combinação de:

-   arquitetura modular;
-   acompanhamento longitudinal;
-   planejamento assistencial;
-   PTS;
-   Agenda de Cuidados;
-   analytics;
-   indicadores;
-   expansão por linhas de cuidado.

# 3. Acesso e Perfis

## Quais perfis existem?

Os principais perfis são:

-   `ADMIN`
-   `ADMIN_CLINICA`
-   `PROFISSIONAL`
-   `RESPONSAVEL`

## Qual a diferença entre ADMIN e ADMIN_CLINICA?

O `ADMIN` possui visão global da plataforma.

O `ADMIN_CLINICA` atua dentro do escopo da instituição à qual está
vinculado.

## O que o PROFISSIONAL pode acessar?

O profissional acessa os pacientes e as linhas de cuidado para as quais
possui permissão.

## O responsável acessa o Portal Profissional?

Não. O perfil `RESPONSAVEL` utiliza o APP do Responsável.

## Um profissional pode acessar mais de uma linha de cuidado?

Sim, desde que esteja devidamente habilitado e vinculado aos módulos
correspondentes.

## O que fazer em caso de problema de acesso?

O usuário deve procurar o administrador responsável pela instituição ou
o canal de suporte definido no processo de implantação.

# 4. Pacientes e Responsáveis

## Um paciente pode participar de mais de uma linha de cuidado?

Sim. A arquitetura multi-módulo permite que um mesmo paciente seja
acompanhado em diferentes linhas de cuidado.

## Um responsável pode acompanhar mais de um paciente?

Sim, desde que os vínculos tenham sido corretamente cadastrados.

## Como funciona o vínculo entre paciente e responsável?

O administrador ou profissional autorizado realiza o vínculo conforme as
regras operacionais da instituição.

## A desativação de um usuário apaga o histórico?

Não. A desativação de acesso não deve eliminar o histórico assistencial
já registrado.

# 5. Registro Longitudinal e Timeline

## O que compõe o histórico longitudinal?

Podem compor o histórico:

-   Registros Diários
-   Avaliações
-   Intervenções
-   Protocolos
-   PTS
-   Evoluções clínicas
-   Outros eventos relevantes da jornada assistencial

## Qual a diferença entre Registro Diário, Avaliação e Intervenção?

O **Registro Diário** acompanha informações recorrentes da rotina do
paciente.

A **Avaliação** aplica instrumentos, protocolos ou análises
estruturadas.

A **Intervenção** registra uma ação assistencial realizada.

## Eventos anteriores podem ser alterados ou excluídos?

O histórico longitudinal deve preservar rastreabilidade e integridade.
As regras de edição e exclusão devem respeitar a governança definida
para cada tipo de registro.

## Como a Timeline é organizada?

A Timeline apresenta os eventos relevantes em ordem cronológica,
consolidando a jornada assistencial do paciente.

## Os registros do APP aparecem no Portal?

Sim. Os registros realizados pelo responsável integram o acompanhamento
longitudinal do paciente conforme a linha de cuidado correspondente.

# 6. PTS e Agenda de Cuidados

## O que é o PTS?

O Plano Terapêutico Singular organiza o planejamento assistencial
individualizado do paciente.

## Quantos PTS ativos um paciente pode ter?

A regra oficial prevê apenas um PTS ativo por paciente e por linha de
cuidado.

## O que são objetivos terapêuticos?

São os resultados assistenciais que orientam o planejamento e as
atividades do cuidado.

## Como as atividades são planejadas?

As atividades são vinculadas aos objetivos do PTS e podem possuir
frequência, duração, período e ocupação profissional.

## O que acontece quando um PTS é encerrado?

O PTS deixa de estar ativo, mas seu histórico permanece disponível para
consulta.

## É possível reabrir um PTS?

Sim, conforme as regras de negócio da plataforma.

# 7. APP do Responsável

## Quem pode utilizar?

Responsáveis e cuidadores devidamente cadastrados e vinculados a
pacientes.

## Como selecionar um paciente?

Após o login, o usuário visualiza os pacientes aos quais possui vínculo.

## Como escolher a linha de cuidado?

Quando o paciente participa de mais de uma linha de cuidado, o APP
apresenta as opções disponíveis.

## Quantos registros podem ser realizados?

A frequência e as regras de registro dependem da linha de cuidado e do
formulário correspondente.

## Como consultar o histórico?

O APP disponibiliza o histórico dos registros realizados conforme o
paciente e a linha de cuidado selecionados.

## O APP substitui a avaliação profissional?

Não.

> **O APP é um instrumento de acompanhamento e coleta longitudinal e não
> substitui avaliação, diagnóstico ou conduta de profissional
> habilitado.**

# 8. Indicadores e Dashboards

## Como os indicadores são gerados?

Os indicadores são derivados dos dados assistenciais registrados na
plataforma.

## Os indicadores são inseridos manualmente?

Sempre que tecnicamente possível, os indicadores devem ser calculados
automaticamente a partir dos dados existentes.

## O que são score, risco e tendência?

São recursos analíticos utilizados para apoiar a leitura da evolução do
paciente conforme as regras de cada linha de cuidado.

## Dashboards substituem a decisão clínica?

Não.

> **Indicadores e analytics apoiam a tomada de decisão, mas não
> substituem o julgamento clínico profissional.**

# 9. Segurança e Privacidade

## Como o acesso é protegido?

A plataforma utiliza autenticação, controle de perfis, permissões e
comunicação segura.

## A plataforma utiliza HTTPS?

Sim. Os domínios oficiais de Produção utilizam HTTPS.

## Como funcionam os perfis e permissões?

Cada usuário acessa apenas as funcionalidades e os dados compatíveis com
seu perfil e seus vínculos.

## Uma clínica visualiza dados de outra?

A arquitetura multi-clínica foi concebida para isolar o acesso conforme
o vínculo institucional e as permissões do usuário.

## O que fazer ao suspeitar de acesso indevido?

O usuário deve interromper o uso da conta comprometida e comunicar
imediatamente o administrador responsável ou o canal oficial de suporte
da instituição.

# 10. Ambientes e Atualizações

## Qual a diferença entre DEV, HML e Produção?

-   **DEV:** desenvolvimento e testes locais.
-   **HML:** homologação e validação.
-   **Produção:** ambiente oficial de operação.

## Como uma atualização chega à Produção?

O fluxo oficial é:

**DEV → HML → Validação → Produção**

## O sistema é atualizado diretamente em Produção?

Não. A regra oficial prevê validação prévia em Homologação.

## Como as versões são registradas?

As versões são registradas no `13_RELEASES.md` e as alterações
detalhadas no `CHANGELOG.md`.

# 11. Suporte

O usuário deve procurar suporte em situações como:

-   problema de login;
-   erro de cadastro;
-   comportamento inesperado;
-   solicitação de melhoria;
-   suspeita de incidente de segurança.

O canal oficial de suporte será definido no processo de implantação de
cada instituição.

# 12. Glossário Rápido

## Linha de Cuidado

Organização estruturada da assistência para determinado contexto clínico
ou população.

## Registro Longitudinal

Histórico estruturado da evolução do paciente ao longo do tempo.

## Timeline

Visualização cronológica dos eventos assistenciais relevantes.

## PTS

Plano Terapêutico Singular.

## Agenda de Cuidados

Planejamento operacional das atividades assistenciais.

## Intervenção

Registro de uma ação assistencial realizada.

## Avaliação

Aplicação de instrumento, protocolo ou análise estruturada.

## Analytics

Processamento e interpretação de dados para apoio à tomada de decisão.

## HML

Ambiente de Homologação.

## Release

Versão oficial publicada da plataforma.

# 13. Governança do FAQ

Novas dúvidas recorrentes identificadas em:

-   treinamentos;
-   implantações;
-   Case Mirassol;
-   suporte;
-   validações com clientes;

deverão ser incorporadas a este documento.

O FAQ deverá evoluir junto com a plataforma e com a experiência real dos
usuários.

------------------------------------------------------------------------

**© Meyio DDS Digital**

**Integra Care --- Plataforma Modular de Gestão Longitudinal de Linhas
de Cuidado**
