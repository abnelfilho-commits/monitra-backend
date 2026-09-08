# Arquitetura da Plataforma Integra Care
Este documento apresenta a arquitetura oficial do **Integra Care Health Platform**.


Seu objetivo é registrar:


- os princípios arquiteturais da plataforma;
- sua organização conceitual;
- seus principais componentes;
- a arquitetura de software;
- a arquitetura longitudinal;
- os fluxos assistenciais;
- as camadas de inteligência;
- os ambientes;
- os princípios de integração;
- as decisões arquiteturais que orientam sua evolução.


Este documento deve funcionar como referência para:


- desenvolvimento;
- arquitetura de software;
- infraestrutura;
- segurança;
- implantação;
- integrações;
- evolução de produto;
- governança técnica.


As regras funcionais e assistenciais detalhadas são mantidas no
`09_REGRAS_NEGOCIO.md`.


---


# 2. Visão Arquitetural


O Integra Care é uma plataforma modular de gestão longitudinal de
linhas de cuidado.


Sua arquitetura foi concebida para permitir que diferentes contextos
assistenciais utilizem um **núcleo tecnológico e longitudinal
compartilhado**, preservando regras clínicas específicas de cada linha
de cuidado.


A evolução da plataforma ampliou esse conceito.


O núcleo do Integra Care não é apenas armazenamento longitudinal.


A arquitetura atual conecta:


```text
CAPTURA
   ↓
REGISTRO
   ↓
LONGITUDINALIDADE
   ↓
JORNADA ASSISTENCIAL
   ↓
INTELIGÊNCIA
   ↓
CONHECIMENTO
   ↓
APOIO À DECISÃO

O paciente permanece como eixo central da arquitetura.

3. Princípios Arquiteturais

A plataforma segue os seguintes princípios:

plataforma única;
núcleo assistencial compartilhado;
paciente como eixo longitudinal;
arquitetura multi-clínica;
arquitetura multi-módulo;
linhas de cuidado independentes;
regras clínicas desacopladas;
reutilização máxima dos componentes centrais;
separação entre experiência e regra de negócio;
separação entre planejado e realizado;
persistência estruturada da longitudinalidade;
múltiplos canais de entrada;
uma única verdade longitudinal;
inteligência como camada de apoio;
rastreabilidade;
escalabilidade;
evolução incremental;
separação entre DEV, HML e PROD.
4. Arquitetura Conceitual Atual
                         INTEGRA CARE
                              │
                 ┌────────────┴────────────┐
                 │                         │
          EXPERIÊNCIAS                INTEGRAÇÕES
                 │                         │
       ┌─────────┼─────────┐               │
       │         │         │               │
     Portal      APP    WhatsApp        Futuros
 Profissional Responsável Business      Canais
       │         │         │               │
       └─────────┴────┬────┴───────────────┘
                      │
                      ▼
              API / CAMADA DE APLICAÇÃO
                      │
                      ▼
               NÚCLEO ASSISTENCIAL
                      │
       ┌──────────────┼───────────────┐
       │              │               │
       ▼              ▼               ▼
    Neuro        Cardiometabólico   Futuras
desenvolvimento                   Linhas de Cuidado
       │              │               │
       └──────────────┼───────────────┘
                      ▼
              NÚCLEO LONGITUDINAL
                      │
       ┌──────────────┼───────────────┐
       │              │               │
       ▼              ▼               ▼
   Timeline       Clinical Engine   Report Engine
       │              │               │
       └──────────────┼───────────────┘
                      ▼
             CONHECIMENTO ASSISTENCIAL
                      │
                      ▼
                APOIO À DECISÃO
5. Camadas de Responsabilidade

A arquitetura pode ser compreendida em cinco grandes camadas:

5.1 Experiência

Responsável pela interação dos diferentes atores com a plataforma.

Exemplos:

Portal Profissional;
APP do Responsável;
WhatsApp Business;
futuras experiências específicas.
5.2 Aplicação

Responsável pelos casos de uso e fluxos operacionais.

Exemplos:

autenticação;
autorização;
pacientes;
PTS;
agenda;
sessões;
registros;
avaliações;
relatórios.
5.3 Domínio

Responsável pelas entidades, conceitos e regras centrais.

Exemplos:

paciente;
clínica;
profissional;
linha de cuidado;
PTS;
sessão assistencial;
Clinical Engine;
regras específicas de cada módulo.
5.4 Dados

Responsável pela persistência e preservação das relações e do histórico.

Inclui:

PostgreSQL;
registros relacionais;
registros longitudinais;
respostas estruturadas;
vínculos;
histórico temporal.
5.5 Infraestrutura

Responsável pela execução dos componentes da plataforma.

Inclui:

Render;
Vercel;
Docker;
ambientes;
domínios;
configurações;
deploy.

Cada camada evolui por razões diferentes. Separar responsabilidades
reduz o impacto de mudanças e aumenta a capacidade de evolução da
plataforma.

6. Arquitetura Física

A arquitetura física atual é composta por frontends desacoplados,
backend centralizado e banco relacional.

                    USUÁRIOS


            ┌──────────┼──────────┐
            │          │          │
            ▼          ▼          ▼


care.meyio.com.br   app.care...   WhatsApp
Portal Profissional APP Responsável Business
React + Vite        React + Vite      │
            │          │              │
            └──────────┼──────────────┘
                       ▼


              api.care.meyio.com.br
                   FastAPI
                       │
                       ▼
                  PostgreSQL
Componentes de Produção
Portal Profissional

https://care.meyio.com.br

Tecnologias:

React;
Vite;
Vercel.
APP do Responsável

https://app.care.meyio.com.br

Tecnologias:

React;
Vite;
Vercel.
API

https://api.care.meyio.com.br

Tecnologias:

FastAPI;
SQLAlchemy;
Alembic;
Render.
Banco
PostgreSQL 16.
Containers
Docker.
7. Frontends Desacoplados

Profissionais, gestores e responsáveis possuem necessidades diferentes.

Por isso, a plataforma utiliza experiências desacopladas sobre o mesmo
núcleo de negócio.

Portal Profissional
        │
        │
APP do Responsável
        │
        ├──────────────► API
        │                  │
WhatsApp Business          ▼
                        Domínio
                           │
                           ▼
                         Dados

As interfaces podem variar.

As regras centrais não devem ser duplicadas.

Experiências podem ser diferentes. A verdade do negócio deve
permanecer centralizada.

8. Portal Profissional

O Portal Profissional concentra a operação clínica e assistencial.

Entre suas capacidades estão:

autenticação;
Cockpit Assistencial;
gestão de pacientes;
visão 360° do paciente;
diagnósticos;
Registro Diário;
avaliações;
M-CHAT;
Denver II;
PTS;
objetivos;
Agenda de Cuidados;
Sessões Assistenciais;
Registro de Atendimento;
intervenções;
Timeline Clínica;
Evolução Clínica;
Clinical Engine;
Painel Clínico Inteligente;
Analytics;
dimensionamento;
geração de relatórios.
9. APP do Responsável

O APP do Responsável oferece uma experiência simplificada e direcionada
à participação do responsável na jornada longitudinal.

Entre suas capacidades estão:

autenticação;
identificação do paciente vinculado;
Registro Diário;
histórico;
acompanhamento.

O APP compartilha o mesmo núcleo longitudinal utilizado pelo Portal
Profissional.

10. WhatsApp Business

O WhatsApp Business constitui um canal adicional de captura longitudinal.

Seu objetivo é aproximar o Registro Diário da rotina real do responsável.

Fluxo conceitual:

RESPONSÁVEL
     ↓
WHATSAPP
     ↓
CONVERSA ESTRUTURADA
     ↓
VALIDAÇÃO
     ↓
REGISTRO DIÁRIO
     ↓
NÚCLEO LONGITUDINAL

O canal de entrada não deverá criar uma base paralela.

As respostas coletadas devem convergir para a mesma estrutura longitudinal
utilizada pelos demais canais.

Múltiplos canais. Uma única jornada.

11. Backend como Núcleo de Aplicação

O backend concentra:

APIs;
autenticação;
autorização;
casos de uso;
regras de negócio;
Clinical Engine;
Report Engine;
persistência;
integrações.

Tecnologias principais:

FastAPI;
SQLAlchemy;
Alembic;
PostgreSQL;
Docker.

Estrutura conceitual:

app/
├── routers
├── services
├── models
├── schemas
├── database
├── security
├── utils
└── core

A estrutura interna poderá evoluir conforme a plataforma cresce.

O princípio permanece:

A API é uma fronteira. A coerência acontece por trás dela.

12. Fluxo de Aplicação

Toda operação protegida segue conceitualmente:

REQUISIÇÃO
     ↓
AUTENTICAÇÃO
     ↓
AUTORIZAÇÃO
     ↓
CONTEXTO
     ↓
REGRA DE NEGÓCIO
     ↓
PERSISTÊNCIA
     ↓
RESPOSTA

A autenticação identifica o usuário.

A autorização determina se ele possui acesso ao contexto solicitado.

A regra de negócio determina o comportamento permitido.

13. Arquitetura de Dados

O PostgreSQL é o banco relacional central da plataforma.

A arquitetura de dados precisa preservar duas dimensões simultaneamente:

RELAÇÕES
   +
TEMPO

As relações organizam:

usuários;
clínicas;
pacientes;
profissionais;
responsáveis;
módulos;
formulários;
vínculos;
PTS;
agenda;
sessões;
demais entidades.

A longitudinalidade preserva:

acontecimentos;
sequência;
origem;
contexto;
evolução.
14. Núcleo Longitudinal

O Registro Longitudinal constitui uma das principais assinaturas
arquiteturais do Integra Care.

O núcleo longitudinal permite que diferentes acontecimentos clínicos
participem da mesma jornada.

Exemplos:

Registro Diário
Avaliação
Intervenção
Sessão
Atendimento
Diagnóstico
PTS
             │
             ▼
     NÚCLEO LONGITUDINAL
             │
             ▼
          Timeline
             │
             ▼
          Evolução
             │
             ▼
        Inteligência

A arquitetura vigente utiliza registros_longitudinais e
respostas_registro como estruturas centrais para os formulários
longitudinais.

15. Formulários Estruturados

A plataforma utiliza formulários configuráveis para permitir variação
de conteúdo sem reconstruir o núcleo tecnológico.

Conceitualmente:

FORMULÁRIO
    │
    ├── CAMPOS
    │
    └── RESPOSTAS
           │
           ▼
   REGISTRO LONGITUDINAL

Podem variar:

campos;
formulários;
parâmetros;
cadastros auxiliares.

Devem permanecer governados:

identidade;
origem;
acesso;
rastreabilidade;
regras;
integridade;
cálculos;
significado clínico.
16. Arquitetura Multi-Clínica

Uma mesma plataforma pode atender múltiplas instituições.

O compartilhamento da arquitetura não deve implicar mistura de contextos.

Integra Care
    │
    ├── Clínica A
    │     ├── Usuários
    │     └── Pacientes
    │
    ├── Clínica B
    │     ├── Usuários
    │     └── Pacientes
    │
    └── Clínica N

A autorização deverá considerar o contexto institucional do usuário.

17. Arquitetura Multi-Módulo

O paciente possui identidade única e poderá participar de diferentes
linhas de cuidado.

                    PACIENTE
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
        Neuro         Cardio      Futuras
                                  Linhas

As linhas compartilham:

identidade;
usuários;
infraestrutura;
segurança;
longitudinalidade;
componentes reutilizáveis.

Cada linha preserva:

formulários específicos;
regras clínicas;
engines;
indicadores;
protocolos;
interpretações.
18. Fluxo Assistencial Atual

A arquitetura assistencial evoluiu significativamente desde a versão 1.0.

O fluxo atual pode ser representado como:

DIAGNÓSTICO
     ↓
AVALIAÇÕES
     ↓
PTS
     ↓
OBJETIVOS
     ↓
PLANEJAMENTO
     ↓
AGENDA DE CUIDADOS
     ↓
SESSÕES ASSISTENCIAIS
     ↓
REGISTRO DE ATENDIMENTO
     ↓
REGISTRO DIÁRIO + INTERVENÇÕES
     ↓
TIMELINE CLÍNICA
     ↓
EVOLUÇÃO
     ↓
CLINICAL ENGINE
     ↓
REPORT ENGINE
     ↓
APOIO À DECISÃO

Esse fluxo representa a evolução do Integra Care para um:

Sistema Operacional da Jornada Assistencial.

19. Planejado × Realizado

Uma decisão arquitetural central é preservar a diferença entre:

PLANEJADO
    ↓
Agenda de Cuidados


REALIZADO
    ↓
Sessão
    ↓
Registro de Atendimento

O planejamento representa intenção assistencial.

A execução representa o que efetivamente aconteceu.

A diferença entre essas dimensões também é informação.

20. Sessões Assistenciais

Sessões Assistenciais operacionalizam o planejamento.

Fluxo:

PTS
 ↓
Objetivo
 ↓
Agenda de Cuidados
 ↓
Sessões
 ↓
Atendimento
 ↓
Registro Longitudinal

As sessões permitem relacionar:

atividade planejada;
profissional;
paciente;
periodicidade;
duração;
execução;
atendimento.
21. Timeline Clínica

A Timeline é uma camada de consolidação da jornada.

Ela não deverá se transformar em fonte paralela da verdade.

Seu papel é organizar cronologicamente acontecimentos provenientes das
fontes oficiais.

Pode reunir:

Registros Diários;
avaliações;
intervenções;
sessões;
atendimentos;
diagnósticos;
outros acontecimentos longitudinalmente relevantes.
FONTES OFICIAIS
      ↓
AGREGAÇÃO
      ↓
TIMELINE
22. Clinical Engine

O Clinical Engine constitui a camada de interpretação clínica automatizada.

Seu papel é transformar dados estruturados e longitudinais em sinais de
apoio à leitura profissional.

Arquitetura conceitual:

DADOS LONGITUDINAIS
        ↓
NORMALIZAÇÃO
        ↓
REGRAS CLÍNICAS
        ↓
SCORE
        ↓
RISCO
        ↓
TENDÊNCIA
        ↓
PRIORIDADE / PROTOCOLO
        ↓
MOMENTO CLÍNICO
        ↓
PAINEL / NARRATIVA

A inteligência clínica permanece separada da camada visual.

O backend deverá ser a fonte oficial das regras clínicas centrais.

23. Estado Atual × Recorrência × Tendência × Histórico

O Clinical Engine deverá preservar semanticamente quatro dimensões:

ESTADO ATUAL
     ≠
RECORRÊNCIA
     ≠
TENDÊNCIA
     ≠
HISTÓRICO

Essa separação é necessária para evitar interpretações incorretas.

Exemplo:

um sintoma pode ter ocorrido historicamente;
pode não existir no registro atual;
ainda assim pode fazer parte da trajetória;
sem que seja correto classificá-lo como condição presente.

A arquitetura deve preservar simultaneamente o presente e o passado.

24. Clinical Engine Neuro

A Linha de Cuidado Neurodesenvolvimento possui regras específicas.

Entre os eixos atuais estão:

sono;
irritabilidade;
crise sensorial;
saúde intestinal;
alimentação;
risco;
tendência.

A interpretação utiliza diferentes estratégias conforme a natureza do
indicador.

Exemplo conceitual:

SONO
→ padrão recente


IRRITABILIDADE
→ estado mais recente


CRISE SENSORIAL
→ estado mais recente


INTESTINAL
→ recorrência e natureza da alteração


ALIMENTAÇÃO
→ estado recente comparado ao histórico

Não existe obrigação arquitetural de todos os indicadores utilizarem a
mesma janela temporal ou método de agregação.

A estratégia deve acompanhar o significado clínico do indicador.

25. Linha Cardiometabólica

A Linha Cardiometabólica utiliza o mesmo núcleo longitudinal,
preservando seu domínio clínico próprio.

Entre os dados atualmente acompanhados estão:

glicemia;
pressão arterial;
peso;
IMC.

Sua arquitetura permite produzir:

risco;
tendência;
indicadores;
dashboards;
evolução individual;
visão populacional.

As regras Cardio permanecem desacopladas das regras Neuro.

26. Painel Clínico Inteligente

O Painel Clínico é uma camada de visualização da inteligência produzida
pelo Clinical Engine.

Fluxo:

REGISTROS
   ↓
CLINICAL ENGINE
   ↓
PAINEL CLÍNICO

O frontend não deverá reconstruir regras clínicas centrais que já são
responsabilidade do backend.

Fallbacks visuais ou compatibilidade com informações históricas deverão
ser tratados cuidadosamente para evitar duplicação da inteligência.

27. Evolução Clínica

A Evolução Clínica representa a trajetória temporal de determinados
indicadores.

Diferentemente dos cards de estado atual, os gráficos preservam o
histórico.

PASSADO ───────────────► PRESENTE

Uma melhora atual não deve apagar eventos anteriores.

Da mesma forma, eventos antigos não devem necessariamente dominar a
interpretação do estado atual.

28. Report Engine

O Report Engine constitui uma camada independente para transformação
de dados e evidências em conhecimento estruturado.

Arquitetura conceitual:

FONTES
  ↓
PROVIDERS
  ↓
REPORT CONTEXT
  ↓
INDICADORES
  ↓
EVIDÊNCIAS
  ↓
INTERPRETAÇÕES
  ↓
NARRATIVE BUILDER
  ↓
CANONICAL REPORT
  ↓
RENDERER
  ↓
PDF / FUTUROS FORMATOS

O framework foi concebido para:

reutilização;
modularidade;
expansão;
diferentes públicos;
diferentes tipos de relatório.
29. Providers

Providers são responsáveis por coletar e organizar informações necessárias
para construção do contexto do relatório.

Podem consumir dados de diferentes domínios da plataforma.

Exemplos:

paciente;
Clinical Engine;
PTS;
sessões;
acontecimentos assistenciais;
outros serviços.

A coleta deverá permanecer separada da apresentação final.

30. Canonical Report

O CanonicalReport representa uma estrutura intermediária independente
do formato final.

DADOS + INTELIGÊNCIA
        ↓
CANONICAL REPORT
        ↓
   ┌────┴─────┐
   ▼          ▼
  PDF       Futuros
           Formatos

Essa separação permite reutilizar a mesma lógica de relatório para
diferentes renderizações.

31. Renderers

Renderers transformam o relatório canônico em formatos de apresentação.

O primeiro renderer implementado é:

PDF Renderer.

A arquitetura permite futura ampliação para outros formatos sem alterar
a lógica central do relatório.

32. CLN-001 — Relatório Longitudinal Inteligente

O CLN-001 é o primeiro relatório canônico do Report Engine.

Ele integra diferentes fontes da jornada do paciente.

Entre suas dimensões estão:

identificação;
resumo executivo;
situação atual;
narrativa longitudinal;
PTS;
diagnósticos;
sessões;
acontecimentos;
inteligência clínica;
interpretação;
recomendações.

Fluxo:

JORNADA DO PACIENTE
        ↓
REPORT ENGINE
        ↓
CLN-001
        ↓
RELATÓRIO LONGITUDINAL INTELIGENTE
33. Arquitetura de Conhecimento

A evolução do Integra Care introduz uma nova sequência conceitual:

DADO
 ↓
INFORMAÇÃO
 ↓
INDICADOR
 ↓
INTERPRETAÇÃO
 ↓
NARRATIVA
 ↓
CONHECIMENTO
 ↓
APOIO À DECISÃO

Essas camadas não devem ser confundidas.

O dado original deve permanecer preservado mesmo quando novas
interpretações forem geradas.

34. Arquitetura de Integrações

Integrações externas devem entrar na plataforma por contratos controlados.

Fluxo conceitual:

SISTEMA / CANAL EXTERNO
          ↓
      INTEGRAÇÃO
          ↓
       VALIDAÇÃO
          ↓
         API
          ↓
    REGRA DE NEGÓCIO
          ↓
     PERSISTÊNCIA

O WhatsApp Business é atualmente um exemplo de integração operacional.

Novas integrações deverão seguir os mesmos princípios de segurança,
rastreabilidade e consistência.

35. Arquitetura de Autenticação e Autorização

Fluxo principal:

USUÁRIO
   ↓
CREDENCIAIS
   ↓
AUTENTICAÇÃO
   ↓
JWT
   ↓
AUTORIZAÇÃO
   ↓
PERFIL + CLÍNICA + MÓDULO + VÍNCULOS
   ↓
RECURSO AUTORIZADO

Perfis atualmente utilizados:

ADMIN;
ADMIN_CLINICA;
PROFISSIONAL;
RESPONSAVEL.

Possuir uma conta não significa possuir acesso irrestrito aos dados.

36. Segurança

A arquitetura de segurança deverá considerar:

HTTPS;
JWT;
menor privilégio;
controle por perfil;
isolamento multi-clínica;
permissões por módulo;
vínculos assistenciais;
proteção dos dados;
rastreabilidade;
separação de ambientes;
segurança das integrações;
proteção de credenciais e segredos.

Detalhes específicos são mantidos no 12_SEGURANCA.md.

37. Ambientes

O Integra Care utiliza três ambientes principais.

Ambiente	Finalidade
DEV	Desenvolvimento e testes
HML	Homologação funcional e técnica
PROD	Operação oficial

Fluxo:

DEV
 ↓
HML
 ↓
VALIDAÇÃO
 ↓
PROD
 ↓
VALIDAÇÃO PÓS-DEPLOY

Produção não deve ser utilizada como ambiente primário de desenvolvimento.

38. Branches e Promoção

O fluxo atual utiliza branches compatíveis com os ambientes de
homologação e produção.

Conceitualmente:

DESENVOLVIMENTO
      ↓
homolog
      ↓
HML
      ↓
VALIDAÇÃO
      ↓
main
      ↓
PROD

Antes da promoção deverão ser executadas verificações compatíveis com a
alteração realizada.

Podem incluir:

validação funcional;
build frontend;
verificação sintática;
testes;
git diff;
migrations;
smoke tests.
39. Deploy

Infraestrutura atual:

Camada	Tecnologia
Portal Profissional	Vercel
APP Responsável	Vercel
Backend	Render
Banco	PostgreSQL
Containers	Docker

Domínios de Produção:

https://care.meyio.com.br
https://app.care.meyio.com.br
https://api.care.meyio.com.br
40. Migrações

Alterações estruturais do banco deverão utilizar mecanismos controlados
de migração.

Tecnologia adotada:

Alembic.

As migrations devem ser tratadas como parte da evolução arquitetural da
plataforma e validadas antes da execução em Produção.

41. Escalabilidade por Linhas de Cuidado

A arquitetura permite crescimento horizontal por linhas de cuidado.

                      INTEGRA CARE
                           │
                   NÚCLEO COMPARTILHADO
                           │
      ┌─────────────┬──────┴──────┬─────────────┐
      ▼             ▼             ▼             ▼
    Neuro         Cardio       Oncologia      Futuras

Novas linhas devem reutilizar o máximo possível do núcleo existente.

Devem ser criadas novas estruturas apenas quando houver diferença real
de domínio ou comportamento.

42. Escalabilidade Organizacional

A arquitetura multi-clínica permite que novas organizações utilizem a
mesma aplicação sem duplicação integral da plataforma.

               INTEGRA CARE
                    │
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
 Organização A Organização B Organização N

O crescimento da base de clientes deverá preservar isolamento,
performance e governança de acesso.

43. Princípio de Reutilização

Antes de criar uma nova estrutura, deve-se avaliar se a necessidade pode
ser atendida por:

configuração;
extensão;
novo formulário;
nova regra;
novo adapter;
novo provider;
novo módulo;
novo componente reutilizável.

Nova necessidade não significa automaticamente nova arquitetura.

44. Roadmap Arquitetural
Curto Prazo
estabilização dos primeiros cases;
evolução contínua do Clinical Engine;
evolução do Report Engine;
expansão dos relatórios;
atualização da documentação oficial;
revisão dos manuais de usuário;
fortalecimento da observabilidade;
consolidação da metodologia de engenharia.
Médio Prazo
evolução do Dimensionamento Inteligente;
Planejamento Financeiro Assistencial;
dashboards gerenciais e populacionais;
expansão das integrações;
evolução de automações;
Linha de Cuidado Oncológica após validação funcional.
Longo Prazo
novas linhas de cuidado;
ecossistema de integrações;
APIs externas controladas;
inteligência assistencial ampliada;
automações e agentes especializados;
novas capacidades populacionais e preditivas, quando clinicamente
validadas.
45. Arquitetura Agregada dos Cockpits

A evolução dos Cockpits do Integra Care introduziu uma arquitetura
agregada para reduzir o acoplamento entre a experiência de frontend e
a quantidade de pessoas acompanhadas.

Na arquitetura anterior, determinadas experiências carregavam a
população e realizavam chamadas adicionais por paciente para obtenção
de informações como risco clínico e eventos longitudinais.

Esse padrão produzia fan-out de requisições HTTP e aumentava o custo
de carregamento conforme a população crescia.

A arquitetura atual desloca a consolidação para o backend:

~~~text
FRONTEND
   ↓
ENDPOINT AGREGADO DO COCKPIT
   ↓
SERVIÇO DE AGREGAÇÃO
   ├── população
   ├── inteligência clínica
   ├── prioridades
   ├── atividade assistencial
   └── eventos recentes
   ↓
PAYLOAD CONSOLIDADO
   ↓
FRONTEND
~~~

Os contratos agregados atualmente utilizados são:

~~~text
GET /cockpit/profissional
GET /cockpit/gestao
~~~

O Cockpit Profissional consolida a informação necessária à experiência
assistencial do profissional.

O Cockpit de Gestão consolida informações populacionais, operacionais
e gerenciais para os perfis administrativos.

Essa arquitetura tem como objetivos:

reduzir o número de requisições HTTP necessárias para abertura dos
Cockpits;
evitar fan-out por paciente no frontend;
centralizar a composição dos indicadores no backend;
preservar contratos consistentes entre backend e frontend;
preparar os Cockpits para populações progressivamente maiores;
permitir evolução dos indicadores sem replicação de lógica nas
experiências de usuário.

A agregação não cria uma nova fonte de inteligência clínica.

Quando uma informação depende de interpretação clínica, o
**Clinical Engine permanece como fonte oficial**.

Os serviços de Cockpit podem consumir, organizar e apresentar essa
inteligência, mas não devem reproduzir ou criar regras clínicas
paralelas no frontend ou na camada de agregação.

46. Arquitetura do Cockpit de Gestão

O Integra Care diferencia suas experiências de Cockpit de acordo com
o papel exercido pelo usuário na operação.

~~~text
PROFISSIONAL
      ↓
Cockpit Assistencial
      ↓
Carteira / Paciente / Jornada


ADMIN_CLINICA
      ↓
Cockpit de Gestão
      ↓
Unidade / População / Operação


ADMIN
      ↓
Cockpit de Gestão
      ↓
Organização / Unidades / População / Operação
~~~

A arquitetura segue o princípio:

**O Cockpit é definido prioritariamente pelo papel do usuário, e não
pelo segmento do cliente.**

Dessa forma, clínicas, empresas, escolas, operadoras, governos ou
outros contextos não exigem automaticamente arquiteturas distintas de
Cockpit.

O núcleo gerencial permanece compartilhado e poderá receber extensões
específicas quando necessidades reais forem validadas.

O perfil ADMIN possui visão consolidada global da operação.

O perfil ADMIN_CLINICA possui visão restrita ao escopo da clínica ou
unidade à qual está vinculado.

O perfil PROFISSIONAL possui visão assistencial orientada à sua
carteira, prioridades e jornadas dos pacientes sob acompanhamento.

A arquitetura de gestão separa dimensões que possuem significados
diferentes:

**Risco Clínico**

Representa interpretação clínica e permanece sob responsabilidade do
Clinical Engine.

**Continuidade Longitudinal**

Representa a regularidade da produção de informação longitudinal,
especialmente do Registro Diário, conforme regras funcionais vigentes.

**Atividade Assistencial**

Representa acontecimentos assistenciais realizados em determinado
período.

**Acompanhamento Ativo**

Representa a existência de evidência assistencial recente segundo as
regras de negócio vigentes.

Essas dimensões podem ser apresentadas conjuntamente no Cockpit, mas
não devem ser tratadas como equivalentes.

O Cockpit de Gestão utiliza um contrato canônico denominado
`cockpit_v2`, incorporado de forma aditiva ao endpoint
`GET /cockpit/gestao`.

A manutenção temporária de campos legados permite transição controlada
das experiências consumidoras sem exigir quebra imediata de
compatibilidade.

A visão canônica prioriza informações agregadas.

Detalhes individuais são disponibilizados quando necessários à
priorização ou ao drill-down, evitando o transporte desnecessário da
população completa no carregamento inicial.

A versão atual possui limites arquiteturais conhecidos:

o recorte específico por módulo ainda não integra o contrato final de
filtros do Cockpit de Gestão;
a análise de Continuidade Longitudinal baseada em Registro Diário
permanece atualmente alinhada ao módulo Neurodesenvolvimento;
os indicadores de atividade e acompanhamento ativo são tratados de
forma transversal às linhas de cuidado no estágio atual;
notificações automáticas decorrentes de quebra de continuidade não
fazem parte desta versão;
capacidades de Inteligência Econômica do Cuidado pertencem a evolução
específica posterior;
filtros e mecanismos adicionais de drill-down pertencem à evolução
subsequente do Cockpit de Gestão.

47. ADRs — Architectural Decision Records

As principais decisões arquiteturais incluem:

ADR-001 — Plataforma modular por linhas de cuidado.
ADR-002 — Registro longitudinal como núcleo.
ADR-003 — API central para experiências desacopladas.
ADR-004 — Núcleo assistencial compartilhado.
ADR-005 — PTS como eixo do planejamento.
ADR-006 — Planejamento Financeiro derivado da assistência.
ADR-007 — Crescimento por linhas de cuidado.
ADR-008 — Separação entre planejado e realizado.
ADR-009 — Sessão Assistencial como ocorrência da execução.
ADR-010 — Múltiplos canais convergem para um núcleo longitudinal.
ADR-011 — Clinical Engine como camada independente de inteligência.
ADR-012 — Estado atual, recorrência, tendência e histórico são
dimensões distintas.
ADR-013 — Regras clínicas específicas permanecem desacopladas por
linha de cuidado.
ADR-014 — Report Engine como framework reutilizável.
ADR-015 — Canonical Report desacopla inteligência de renderização.
ADR-016 — Timeline consolida fontes oficiais e não cria verdade
paralela.
ADR-017 — HML precede a promoção para Produção.
ADR-018 — Inteligência automatizada apoia, mas não substitui,
julgamento profissional.
ADR-019 — Cockpits utilizam arquitetura agregada e evitam fan-out por
paciente no frontend.
ADR-020 — Clinical Engine permanece como fonte oficial da inteligência
clínica; Cockpits não criam regras clínicas paralelas.
ADR-021 — A experiência dos Cockpits é definida prioritariamente pelo
papel do usuário, e não pelo segmento do cliente.
ADR-022 — Risco clínico, continuidade longitudinal e atividade
assistencial são dimensões distintas da gestão.
48. Princípios de Evolução Arquitetural

Toda evolução relevante deverá responder às seguintes perguntas:

O problema é real e validado?
A funcionalidade pertence ao núcleo ou a uma linha específica?
Já existe estrutura reutilizável?
O dado precisa ser longitudinal?
Qual é a fonte oficial da informação?
A nova regra deve ficar no backend?
Há impacto sobre outras linhas de cuidado?
Há impacto sobre segurança ou autorização?
Há necessidade de migration?
Há impacto no Clinical Engine?
Há impacto no Report Engine?
A documentação precisa ser atualizada?
49. Arquitetura e Inteligência Artificial

O Integra Care deverá tratar inteligência artificial e automação como
camadas complementares à arquitetura oficial.

A introdução de IA não deverá:

eliminar rastreabilidade;
substituir fontes estruturadas;
criar verdades clínicas paralelas;
contornar regras de autorização;
alterar silenciosamente dados originais.

A IA poderá apoiar:

interpretação;
síntese;
narrativa;
priorização;
automação;
apoio operacional;
futuras capacidades assistenciais validadas.

Toda utilização clínica deverá preservar supervisão e governança
adequadas.

50. Relação com a Documentação

A arquitetura deve ser interpretada em conjunto com:

09_REGRAS_NEGOCIO.md — regras funcionais e assistenciais;
10_API.md — contratos de comunicação;
11_BANCO_DADOS.md — persistência;
12_SEGURANCA.md — segurança;
13_RELEASES.md — evolução das versões;
CHANGELOG.md — mudanças detalhadas;
futuro Integra Care Engineering Playbook — processo de engenharia.
51. Histórico de Revisões
Versão	Data	Descrição
1.0.0	03/07/2026	Arquitetura inicial oficial
1.1.0	24/08/2026	Jornada Assistencial, Sessões, arquitetura multicanal, Clinical Engine, Report Engine, CLN-001 e evolução da arquitetura longitudinal
1.2.0   08/09/2026      Arquitetura agregada dos Cockpits, escalabilidade, Cockpit de Gestão e gestão populacional por perfil
52. Considerações Finais

A arquitetura do Integra Care foi criada para preservar algo maior do
que estruturas técnicas.

Ela precisa preservar a jornada.

Por isso, a arquitetura evoluiu de:

REGISTRAR
   ↓
ARMAZENAR
   ↓
VISUALIZAR

para:

PLANEJAR
   ↓
EXECUTAR
   ↓
REGISTRAR
   ↓
CONECTAR
   ↓
INTERPRETAR
   ↓
COMPREENDER
   ↓
DECIDIR

O núcleo tecnológico pode ser compartilhado.

As experiências podem variar.

As linhas de cuidado podem crescer.

Os canais podem se multiplicar.

Mas três elementos devem permanecer preservados:

Identidade. Longitudinalidade. Coerência.

Uma única plataforma. Um único núcleo assistencial. Múltiplas linhas de cuidado.

© Integra Care Health Platform