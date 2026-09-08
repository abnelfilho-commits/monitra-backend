# Releases do Integra Care

> **Versão do documento:** 1.1.0
> **Produto:** Integra Care Health Platform
> **Documento:** 13_RELEASES.md
> **Status:** Oficial

---

# 1. Objetivo

Registrar oficialmente as versões do **Integra Care Health Platform**,
seus marcos, significado, escopo funcional e evolução arquitetural,
assistencial e estratégica.

Este documento representa a história evolutiva da plataforma.

Seu objetivo não é relacionar individualmente todas as alterações
realizadas no software, mas registrar os grandes ciclos de evolução
que caracterizam cada release.

O detalhamento funcional, técnico e corretivo de cada ciclo é mantido
no `CHANGELOG.md`.

---

# 2. Política de Versionamento

O Integra Care adota **Versionamento Semântico**:

```text
MAJOR.MINOR.PATCH

1.0.0
│ │ │
│ │ └── Correções e refinamentos compatíveis
│ └──── Novas funcionalidades e evoluções compatíveis
└────── Grandes evoluções ou mudanças estruturais incompatíveis
```

## MAJOR

Utilizado quando houver mudança estrutural relevante que represente
uma nova geração da plataforma ou introduza incompatibilidades
significativas.

Exemplo:

```text
1.x.x → 2.0.0
```

## MINOR

Utilizado quando novas capacidades relevantes forem incorporadas
mantendo compatibilidade com a geração atual da plataforma.

Exemplo:

```text
1.0.0 → 1.1.0
```

## PATCH

Utilizado para correções, estabilizações e refinamentos que não
representem nova capacidade funcional significativa.

Exemplo:

```text
1.1.0 → 1.1.1
```

---

# 3. Estado Atual da Plataforma

A release oficial consolidada permanece:

> **Integra Care v1.0.0 — Fundação**

Entretanto, desde sua publicação em 03/07/2026, a plataforma passou
por um novo ciclo expressivo de evolução.

As capacidades desenvolvidas posteriormente encontram-se registradas
no `[Unreleased]` do `CHANGELOG.md` e constituem a base candidata da
próxima release oficial:

> **Integra Care v1.1.0 — Jornada Assistencial Inteligente**

A `v1.1.0` somente será considerada publicada quando o ciclo formal
de release for encerrado.

---

# 4. Release Oficial

## Integra Care v1.0.0 — Fundação

**Data:** 03/07/2026
**Status:** Publicada

A versão `v1.0.0` representa a primeira versão institucional
consolidada do Integra Care.

Seu principal marco foi transformar a solução em uma:

> **Plataforma Modular de Gestão Longitudinal de Linhas de Cuidado.**

Esta release estabeleceu o núcleo tecnológico, assistencial e
operacional sobre o qual toda a evolução posterior da plataforma
passou a ser construída.

---

# 5. Escopo da v1.0.0

A Fundação consolidou:

## Experiência

- Portal Profissional
- APP do Responsável

## Linhas de Cuidado

- Neurodesenvolvimento
- Cardiometabólico

## Núcleo Assistencial

- Registro Longitudinal
- Timeline Clínica
- Intervenções
- Avaliações
- Plano Terapêutico Singular — PTS
- Objetivos terapêuticos
- Agenda de Cuidados
- Dashboards assistenciais
- Analytics

## Arquitetura

- API centralizada
- Arquitetura Multi-Clínica
- Arquitetura Multi-Módulo
- Controle de perfis e permissões
- Banco de dados PostgreSQL
- Containers Docker
- Migrações estruturadas

---

# 6. Infraestrutura Consolidada na Fundação

A `v1.0.0` consolidou a infraestrutura oficial da plataforma:

- ambientes DEV, HML e Produção;
- fluxo oficial de promoção entre ambientes;
- backend hospedado na Render;
- Portal Profissional hospedado na Vercel;
- APP do Responsável hospedado na Vercel;
- PostgreSQL como banco relacional central;
- containers Docker;
- migrações com Alembic;
- Produção e Homologação estruturalmente controladas;
- rotina de backups.

## Domínios Oficiais de Produção

- Portal Profissional: `https://care.meyio.com.br`
- APP do Responsável: `https://app.care.meyio.com.br`
- API: `https://api.care.meyio.com.br`

---

# 7. Marcos da v1.0.0

Entre os principais marcos da Fundação estão:

- estabilização da Linha de Cuidado Neurodesenvolvimento;
- estabilização da Linha de Cuidado Cardiometabólico;
- consolidação do Registro Longitudinal;
- implementação do Plano Terapêutico Singular;
- implementação da Agenda de Cuidados;
- consolidação do APP do Responsável;
- consolidação da Timeline Clínica;
- estruturação dos ambientes DEV, HML e Produção;
- primeiro merge oficial de Homologação para Produção;
- criação dos domínios oficiais;
- início da documentação oficial da plataforma;
- preparação da plataforma para seus primeiros cases.

A `v1.0.0` estabeleceu a fundação.

A partir dela, o desafio deixou de ser apenas construir a plataforma
e passou a ser transformar longitudinalidade em uma jornada
assistencial operacional e inteligente.

---

# 8. Ciclo de Evolução Pós-v1.0.0

Após a Fundação, o Integra Care iniciou um novo ciclo de desenvolvimento.

Esse ciclo ampliou significativamente o papel da plataforma.

A arquitetura deixou de se limitar à sequência:

```text
Registro
   ↓
Armazenamento
   ↓
Visualização
```

e passou a evoluir para:

```text
Registro
   ↓
Longitudinalidade
   ↓
Inteligência Clínica
   ↓
Jornada Assistencial
   ↓
Conhecimento Estruturado
   ↓
Decisão
```

Essa evolução constitui a base da próxima geração funcional da
plataforma dentro da série `1.x`.

---

# 9. Próxima Release Candidata

## Integra Care v1.1.0 — Jornada Assistencial Inteligente

**Data:** A definir
**Status:** Candidata / Em consolidação

A `v1.1.0` representa a evolução do Integra Care de uma plataforma
longitudinal funcional para um **Sistema Operacional da Jornada
Assistencial**.

Seu princípio central é conectar:

```text
Planejamento
      ↓
Execução
      ↓
Registro
      ↓
Longitudinalidade
      ↓
Inteligência
      ↓
Decisão
```

O profissional deixa de visualizar apenas informações registradas
e passa a operar uma jornada assistencial estruturada, acompanhando
o que foi planejado, o que foi realizado, como o paciente evoluiu e
quais sinais merecem atenção.

---

# 10. Grandes Marcos Candidatos da v1.1.0

## 10.1 Cockpit Assistencial

O Portal Profissional evoluiu para oferecer uma visão operacional
da assistência.

O Cockpit Assistencial passa a reunir:

- resumo da operação;
- pacientes;
- sessões;
- atividades realizadas;
- pendências;
- pacientes prioritários;
- atividade recente;
- evolução;
- ações rápidas.

O objetivo é reduzir a fragmentação da informação e aproximar
o profissional das decisões necessárias para o cuidado diário.

---

## 10.2 Arquitetura Agregada e Escalabilidade dos Cockpits

A evolução dos Cockpits introduz uma arquitetura agregada voltada à
escalabilidade da experiência.

Fluxos que anteriormente dependiam da carga da população seguida de
requisições adicionais por paciente passam a utilizar contratos
agregados no backend.

Essa evolução reduz fan-out de chamadas HTTP, centraliza a composição
dos indicadores e prepara os Cockpits para populações maiores.

Os principais contratos agregados são:

~~~text
GET /cockpit/profissional
GET /cockpit/gestao
~~~

O Clinical Engine permanece como fonte oficial da inteligência
clínica. Os Cockpits consomem e organizam essa inteligência sem criar
regras clínicas paralelas.

A evolução foi validada com populações administrativas superiores a
uma centena de pessoas acompanhadas, substituindo o modelo anterior
baseado em múltiplas chamadas por paciente.

---

## 10.3 Cockpit de Gestão e Gestão Populacional

A plataforma passa a oferecer uma experiência gerencial específica
para os perfis ADMIN e ADMIN_CLINICA.

O Cockpit de Gestão organiza a leitura da operação em seis dimensões
principais:

- visão executiva;
- situação da população;
- prioridades de atenção;
- operação assistencial;
- estrutura assistencial;
- atividade recente.

A experiência distingue explicitamente:

- risco clínico;
- continuidade longitudinal;
- acompanhamento ativo;
- atividade assistencial.

A ausência de Registro Diário por 7 dias ou mais passa a representar
Alerta Crítico de Continuidade, sem transformar automaticamente essa
condição em alto risco clínico.

O perfil ADMIN possui visão global da operação, enquanto o perfil
ADMIN_CLINICA permanece restrito ao seu escopo de clínica ou unidade.

O Cockpit é estruturado prioritariamente pelo papel do usuário, e não
pelo segmento do cliente, permitindo reutilização do mesmo núcleo
gerencial em diferentes contextos de operação.

---

## 10.4 Sistema Operacional da Jornada Assistencial

A jornada passa a ser representada de forma integrada:

```text
Diagnóstico
     ↓
Avaliações
     ↓
PTS
     ↓
Objetivos
     ↓
Planejamento
     ↓
Agenda de Cuidados
     ↓
Sessões Assistenciais
     ↓
Registro de Atendimento
     ↓
Registro Diário + Intervenções
     ↓
Timeline
     ↓
Evolução
     ↓
Inteligência Clínica
     ↓
Relatórios
```

Esse modelo passa a representar uma das principais assinaturas
funcionais do Integra Care.

---

## 10.5 Planejado × Realizado

A `v1.1.0` introduz uma distinção fundamental na arquitetura
assistencial:

> **O que foi planejado não é necessariamente o que foi realizado.**

A Agenda de Cuidados representa o planejamento.

As Sessões Assistenciais representam a operacionalização desse
planejamento.

O Registro de Atendimento documenta a execução efetiva do cuidado.

A diferença entre planejado e realizado passa, portanto, a constituir
informação relevante para acompanhamento da jornada assistencial.

---

## 10.6 Sessões Assistenciais

As Sessões Assistenciais conectam o planejamento ao cuidado executado.

A plataforma passa a permitir:

- geração das sessões;
- acompanhamento das sessões programadas;
- identificação das sessões do dia;
- registro do atendimento;
- narrativa assistencial;
- definição de próximos passos;
- incorporação do atendimento à longitudinalidade do paciente.

Com isso, a Agenda deixa de representar apenas planejamento e passa
a alimentar diretamente a operação assistencial.

---

## 10.7 Visão 360° do Paciente

A experiência do paciente evolui para concentrar diferentes dimensões
da jornada clínica.

Entre elas:

- diagnósticos;
- avaliações;
- PTS;
- objetivos;
- planejamento;
- sessões;
- atendimentos;
- registros diários;
- intervenções;
- Timeline;
- evolução clínica;
- inteligência clínica;
- relatórios.

O paciente passa a ser compreendido pela sequência de acontecimentos
ao longo do tempo, e não apenas por registros isolados.

---

## 10.8 Clinical Engine

A inteligência clínica passa a constituir uma camada explícita da
arquitetura.

O Clinical Engine utiliza dados longitudinais para produzir elementos
de apoio à leitura clínica, incluindo:

- risco;
- tendência;
- prioridade;
- protocolo;
- interpretação;
- eixo dominante;
- momento clínico;
- Painel Clínico Inteligente;
- resumo clínico automático.

O objetivo da inteligência não é substituir julgamento profissional.

Seu papel é:

> **transformar dados longitudinais em sinais clínicos estruturados
> que apoiem a tomada de decisão.**

---

## 10.9 Estado Atual, Recorrência, Tendência e Histórico

A evolução do Clinical Engine introduz uma separação semântica
importante:

```text
Estado atual
≠
Recorrência
≠
Tendência
≠
Histórico
```

Um evento histórico relevante não deve necessariamente representar
o estado atual do paciente.

Da mesma forma, a ausência atual de determinado sintoma não elimina
o valor clínico do histórico.

Essa distinção permite produzir interpretações mais coerentes com
a longitudinalidade real do paciente.

---

## 10.10 Registro Diário Multicanal

O Registro Diário evolui de uma funcionalidade restrita às interfaces
da plataforma para uma capacidade de captura longitudinal
multicanal.

Os registros podem ser originados por:

```text
Portal Profissional
        │
        ├──────────────┐
        ▼              ▼
APP do Responsável   WhatsApp
        │              │
        └──────┬───────┘
               ▼
      Registro Longitudinal
               ▼
        Clinical Engine
               ▼
 Timeline / Painel / Relatórios
```

Essa evolução aproxima a coleta de dados da rotina real do paciente
e de seus responsáveis.

---

## 10.11 WhatsApp Business

A integração com WhatsApp Business amplia a capacidade de coleta
longitudinal do Integra Care.

O canal conversacional permite realizar o Registro Diário sem exigir
que o responsável esteja utilizando diretamente o APP no momento
do preenchimento.

As informações coletadas passam pelo fluxo da plataforma e são
incorporadas à mesma arquitetura longitudinal utilizada pelos demais
canais.

---

## 10.12 Report Engine

A `v1.1.0` incorpora uma nova camada arquitetural:

> **Report Engine**

Seu objetivo é transformar dados e evidências distribuídas na
plataforma em conhecimento estruturado e comunicável.

O pipeline conceitual é:

```text
Dados
  ↓
Contexto
  ↓
Indicadores
  ↓
Evidências
  ↓
Interpretação
  ↓
Narrativa
  ↓
Canonical Report
  ↓
Renderer
  ↓
Documento
```

O Report Engine foi concebido para ser reutilizável entre diferentes
tipos de relatórios e diferentes públicos.

---

## 10.13 CLN-001 — Relatório Longitudinal Inteligente

O primeiro relatório canônico construído sobre o Report Engine é o:

> **CLN-001 — Relatório Longitudinal Inteligente**

O relatório consolida informações relevantes da jornada do paciente
e as organiza em uma representação clínica estruturada.

Entre seus componentes estão:

- identificação;
- resumo executivo;
- situação atual;
- narrativa longitudinal;
- dados do PTS;
- diagnósticos;
- acontecimentos assistenciais;
- sessões;
- inteligência clínica;
- geração em PDF.

O CLN-001 representa a primeira materialização do princípio:

> **dados → conhecimento clínico estruturado.**

---

# 11. Significado Estratégico da v1.1.0

A `v1.0.0` respondeu à pergunta:

> **Como estruturar longitudinalmente uma linha de cuidado dentro de uma
> plataforma única?**

A `v1.1.0` passa a responder:

> **Como transformar essa longitudinalidade em uma jornada assistencial
> operacional, interpretável e orientada à decisão?**

Essa mudança representa um avanço importante no posicionamento
tecnológico do Integra Care.

A plataforma passa progressivamente de um sistema de registro e
acompanhamento para uma infraestrutura capaz de conectar:

**Cuidado → Dados → Longitudinalidade → Inteligência → Decisão.**


A evolução também amplia a inteligência da plataforma para além da leitura individual da jornada, incorporando uma visão **populacional e operacional** para os perfis de gestão, sem confundir indicadores gerenciais com interpretação clínica.

---

# 12. Estado de Consolidação da v1.1.0

Grande parte das capacidades candidatas à `v1.1.0` já foi:

- desenvolvida;
- validada em DEV;
- homologada;
- promovida para Produção;
- validada funcionalmente em ambiente produtivo.

Entretanto, a existência dessas funcionalidades em Produção não
substitui o processo formal de release.

Até que o fechamento seja realizado, essas alterações permanecem
registradas no `[Unreleased]` do `CHANGELOG.md`.

Quando a release for oficialmente encerrada:

```text
[Unreleased]
     ↓
v1.1.0
     ↓
Data da publicação
     ↓
Registro oficial
```


Entre as capacidades já implementadas, homologadas e promovidas para
Produção estão também:

- a arquitetura agregada dos Cockpits, reduzindo o fan-out de
  requisições por paciente;
- o Cockpit de Gestão para ADMIN e ADMIN_CLINICA;
- os indicadores de acompanhamento ativo, cobertura assistencial,
  continuidade longitudinal, atenção necessária, atividade
  assistencial e estrutura da operação.

---

# 13. Roadmap de Releases

## v1.0.0 — Fundação

**Status:** Publicada

Consolidação da plataforma, arquitetura longitudinal, linhas iniciais
de cuidado e infraestrutura oficial.

## v1.1.0 — Jornada Assistencial Inteligente

**Status:** Candidata / Em consolidação

Consolidação da jornada assistencial, Sessões Assistenciais,
Clinical Engine, captura multicanal e Report Engine.

## Próximas Evoluções

As releases posteriores poderão incorporar, conforme validação
estratégica e assistencial:

- evolução do Clinical Engine;
- evolução do Report Engine;
- novos relatórios;
- inteligência assistencial;
- novas integrações;
- evolução do Dimensionamento Inteligente;
- Planejamento Financeiro Assistencial;
- aprendizados dos primeiros cases;
- novas linhas de cuidado;
- Linha de Cuidado Oncológica;
- automações e agentes inteligentes;
- novas capacidades gerenciais e populacionais.

As funcionalidades futuras somente deverão ser associadas a uma
versão específica quando houver planejamento formal suficiente para
isso.

---

# 14. Critérios para uma Release Oficial

Uma versão somente será considerada oficialmente publicada após
cumprir o fluxo:

```text
Desenvolvimento
      ↓
DEV
      ↓
HML
      ↓
Validação
      ↓
Documentação
      ↓
Produção
      ↓
Validação Pós-Deploy
      ↓
Registro da Release
```

A publicação deverá preservar:

- rastreabilidade;
- estabilidade;
- documentação;
- compatibilidade arquitetural;
- integridade das regras de negócio;
- consistência entre ambientes;
- histórico de evolução.

---

# 15. Relação com o CHANGELOG.md

O `13_RELEASES.md` registra:

- releases oficiais;
- grandes ciclos de evolução;
- significado de cada versão;
- marcos tecnológicos;
- marcos assistenciais;
- evolução estratégica da plataforma.

O `CHANGELOG.md` registra:

- funcionalidades adicionadas;
- alterações funcionais;
- alterações técnicas;
- correções;
- refinamentos;
- mudanças relevantes desde a última release.

Portanto:

```text
13_RELEASES.md
      ↓
História e significado das versões

CHANGELOG.md
      ↓
Detalhamento das mudanças
```

Os dois documentos são complementares.

---

# 16. Histórico de Releases

| Versão | Data | Nome | Status |
|---|---|---|---|
| `v1.0.0` | 03/07/2026 | Fundação | Publicada |
| `v1.1.0` | A definir | Jornada Assistencial Inteligente | Candidata / Em consolidação |

---

# 17. Governança das Releases

Toda nova release deverá possuir:

1. número de versão;
2. nome ou marco representativo;
3. data oficial;
4. escopo consolidado;
5. validação técnica;
6. validação funcional;
7. documentação correspondente;
8. atualização do `CHANGELOG.md`;
9. atualização deste documento.

Nenhuma versão deverá ser criada retroativamente apenas para
representar grupos de commits ou períodos de desenvolvimento.

O histórico deve refletir **releases reais da plataforma**, e não
simplesmente a cronologia interna do desenvolvimento.

---

# 18. Considerações Finais

A história das releases do Integra Care representa mais do que a
evolução de um software.

Ela registra a construção progressiva de uma arquitetura destinada
a organizar a jornada assistencial longitudinal.

A `v1.0.0` estabeleceu a fundação.

A próxima geração funcional amplia essa base para conectar
planejamento, execução, longitudinalidade, inteligência clínica
e geração estruturada de conhecimento.

> **v1.0.0 — Fundação**

> **v1.1.0 — Jornada Assistencial Inteligente**

A evolução continuará seguindo o mesmo princípio:

> **Uma única plataforma. Um único núcleo assistencial. Múltiplas
> linhas de cuidado.**

---

**Integra Care Health Platform**
