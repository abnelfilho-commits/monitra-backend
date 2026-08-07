# Report Engine Specification

**Projeto:** Integra Care  
**Versão:** 1.0  
**Status:** Draft  
**Autor:** Meyio DDS Digital

---

# 1. Objetivo

## Visão Geral

O Report Engine é o framework responsável pela geração dos relatórios inteligentes do Integra Care.

Seu objetivo é transformar os dados e as inteligências produzidas pelos módulos da plataforma em documentos institucionais, padronizados e orientados à tomada de decisão.

O Report Engine **não produz inteligência clínica**.

Ele integra as inteligências produzidas pelos Engines especializados da plataforma e constrói uma narrativa longitudinal referente ao período analisado.

---

## Responsabilidades

- Gerar relatórios clínicos, gerenciais e institucionais.
- Integrar diferentes domínios da plataforma.
- Produzir narrativas longitudinais.
- Gerar documentos em múltiplos formatos.
- Preservar a Fonte Única da Verdade.

---

## Não faz

- Não recalcula protocolos.
- Não substitui o Clinical Engine.
- Não interpreta dados brutos.
- Não acessa diretamente o banco de dados.
- Não altera a inteligência produzida pelos Engines especializados.

---

# 2. Arquitetura Geral

```
                   PostgreSQL
                        │
                        ▼
                  Domain Services
                        │
                        ▼
                    Providers
                        │
                        ▼
             Clinical Engines
      (Leituras Oficiais dos Domínios)
                        │
                        ▼
                 Report Engine
                        │
                        ▼
            Narrativa Longitudinal
                        │
                        ▼
              Canonical Report
                        │
                        ▼
                  Renderers
         PDF • HTML • Preview
```

---

## Fluxo

1. Os Providers coletam os dados.
2. Os Engines especializados produzem as leituras oficiais.
3. O Report Engine integra essas leituras.
4. O Composer monta o Modelo Canônico do Relatório.
5. O Renderer gera o formato final.

---

# 3. Princípios Arquiteturais

- Fonte Única da Verdade.
- Separação entre Inteligência e Comunicação.
- Baixo acoplamento.
- Alta reutilização.
- Independência entre conteúdo e apresentação.
- Arquitetura orientada por composição.

# 4. Componentes do Report Engine

O Report Engine é composto por componentes especializados, cada um responsável por uma etapa do pipeline de geração dos relatórios.

Cada componente possui responsabilidade única e bem definida, reduzindo acoplamento e facilitando evolução da arquitetura.

---

## 4.1 Report Registry

### Responsabilidade

Registrar todos os relatórios disponíveis na plataforma.

Cada relatório é definido de forma declarativa através de uma `ReportDefinition`.

### Responsabilidades

- Registrar relatórios disponíveis.
- Informar Providers necessários.
- Informar Engines utilizados.
- Informar Sections.
- Informar Template.
- Informar Renderer.
- Validar parâmetros obrigatórios.

### Não faz

- Não consulta banco.
- Não produz conteúdo.
- Não gera PDF.

---

## 4.2 Providers

### Responsabilidade

Coletar e normalizar dados provenientes dos módulos da plataforma.

Os Providers reutilizam serviços já existentes do Integra Care, evitando duplicação de regras de negócio.

### Responsabilidades

- Coletar dados.
- Normalizar estruturas.
- Preservar referências de origem.
- Informar warnings de coleta.

### Não faz

- Não interpreta dados.
- Não produz indicadores.
- Não gera narrativas.

### Providers previstos

- PatientProvider
- DiagnosisProvider
- AssessmentProvider
- PTSProvider
- SessionProvider
- LongitudinalProvider
- InterventionProvider
- TimelineProvider
- AnalyticsProvider

---

## 4.3 Clinical Engines

### Responsabilidade

Produzir a inteligência oficial de cada domínio da plataforma.

Cada Engine é responsável exclusivamente pela leitura do seu domínio.

Exemplos:

- Leitura Clínica
- Leitura Diagnóstica
- Leitura do PTS
- Leitura Assistencial
- Leitura dos Protocolos

### Não faz

- Não gera relatórios.
- Não conhece PDF.
- Não produz narrativa longitudinal.

---

## 4.4 Report Engine

### Responsabilidade

Integrar as leituras produzidas pelos Engines especializados e construir a narrativa longitudinal do período analisado.

### Responsabilidades

- Integrar domínios.
- Produzir narrativa longitudinal.
- Organizar a jornada assistencial.
- Consolidar indicadores do período.

### Não faz

- Não substitui o Clinical Engine.
- Não recalcula protocolos.
- Não altera leituras oficiais.

---

## 4.5 Report Composer

### Responsabilidade

Montar o Modelo Canônico do Relatório.

Recebe Sections e Components produzidos durante o pipeline e organiza a estrutura lógica do relatório.

### Responsabilidades

- Ordenar Sections.
- Organizar Components.
- Produzir o objeto Report.

### Não faz

- Não interpreta dados.
- Não renderiza documentos.

---

## 4.6 Templates

### Responsabilidade

Definir a identidade visual do relatório.

O Template controla exclusivamente a apresentação.

### Responsabilidades

- Layout.
- Tipografia.
- Espaçamento.
- Cores.
- Cabeçalho.
- Rodapé.

### Não faz

- Não altera conteúdo.
- Não interpreta dados.

---

## 4.7 Renderers

### Responsabilidade

Transformar o Modelo Canônico em formatos de saída.

### Renderers previstos

- PDF Renderer
- HTML Renderer
- Preview Renderer

### Não faz

- Não produz inteligência.
- Não altera narrativas.
- Não modifica indicadores.

---

## 4.8 Validators

### Responsabilidade

Validar a consistência estrutural do relatório antes da renderização.

### Responsabilidades

- Validar Sections obrigatórias.
- Validar Components.
- Validar integridade do Report.
- Registrar warnings.

### Não faz

- Não corrige dados.
- Não altera conteúdo.

---

## Estrutura Física

```text
report_engine/

├── core/
├── registry/
├── providers/
├── engines/
├── composers/
├── sections/
├── components/
├── templates/
├── renderers/
├── validators/
├── models/
├── schemas/
└── utils/
```

---

## Resumo da Arquitetura

```text
Report Registry
        │
        ▼
    Providers
        │
        ▼
Clinical Engines
        │
        ▼
 Report Engine
        │
        ▼
Report Composer
        │
        ▼
 Canonical Report
        │
        ▼
    Renderer
        │
        ▼
 PDF / HTML
```

# 5. Modelo de Domínio

O Report Engine utiliza um conjunto reduzido de objetos de domínio para representar o conhecimento produzido durante a geração de um relatório.

Esses objetos são independentes do formato de saída e compõem o Modelo Canônico do Relatório.

---

## 5.1 Report

Representa o relatório completo.

É o objeto final produzido pelo Report Composer e consumido pelos Renderers.

```text
Report

├── Metadata
├── Subject
├── Period
├── Sections
├── Warnings
└── Audit
```

---

## 5.2 Subject

Representa o objeto principal do relatório.

Exemplos:

- Paciente
- Clínica
- Profissional
- Operadora
- Município

```text
Subject

├── id
├── type
├── name
└── metadata
```

---

## 5.3 Section

Representa um capítulo do relatório.

Exemplos:

- Resumo Executivo
- Leitura da Situação Atual
- Narrativa Longitudinal
- PTS
- Sessões
- Conclusão

```text
Section

├── code
├── title
├── order
└── components
```

---

## 5.4 Component

Representa um elemento visual dentro de uma Section.

Exemplos:

- Texto
- Card
- Indicador
- Tabela
- Gráfico
- Timeline
- Alerta

```text
Component

├── type
├── data
└── metadata
```

---

## 5.5 Indicator

Representa um indicador calculado durante a execução do relatório.

```text
Indicator

├── code
├── label
├── value
├── unit
├── severity
└── source
```

---

## 5.6 Evidence

Representa uma evidência produzida pelos Engines.

Toda evidência deve possuir rastreabilidade.

```text
Evidence

├── code
├── description
├── confidence
├── severity
└── sources
```

---

## 5.7 Narrative

Representa uma narrativa longitudinal produzida pelo Report Engine.

Não substitui as Leituras Oficiais dos Engines especializados.

```text
Narrative

├── title
├── content
├── audience
└── references
```

---

## 5.8 Recommendation

Representa uma recomendação apresentada ao final do relatório.

Pode possuir origem:

- Clinical Engine
- Report Engine

```text
Recommendation

├── source
├── priority
├── description
└── references
```

---

## 5.9 Warning

Representa limitações identificadas durante a geração do relatório.

Exemplos:

- Dados insuficientes
- Período sem registros
- Informações incompletas

```text
Warning

├── code
├── message
└── severity
```

---

## 5.10 Audit

Registra informações de auditoria da geração do relatório.

```text
Audit

├── generated_at
├── report_version
├── engines
├── rules
└── execution_time
```

---

## Relacionamento entre os Objetos

```text
Report
│
├── Subject
├── Sections
│      │
│      └── Components
│
├── Warnings
└── Audit

Components
│
├── Indicators
├── Evidences
├── Narratives
└── Recommendations
```

---

## Modelo Conceitual

```text
Clinical Engines
        │
        ▼
Leituras Oficiais
        │
        ▼
Report Engine
        │
        ▼
Indicators
Evidences
Narratives
Recommendations
        │
        ▼
Sections
        │
        ▼
Report
```

---

## Considerações

- Todos os objetos são independentes do formato de saída.
- Os Renderers consomem exclusivamente o objeto `Report`.
- Os objetos de domínio não possuem responsabilidade de apresentação.
- O modelo foi projetado para reutilização entre diferentes tipos de relatório.

# 6. Pipeline de Geração de Relatórios

O Report Engine executa um pipeline sequencial responsável por transformar dados da plataforma em um relatório institucional.

Cada etapa possui responsabilidade única e produz uma saída consumida pela etapa seguinte.

---

## Fluxo Geral

```text
Report Request
       │
       ▼
Report Registry
       │
       ▼
Providers
       │
       ▼
Specialized Engines
(Leituras Oficiais)
       │
       ▼
Report Engine
(Narrativa Longitudinal)
       │
       ▼
Report Composer
       │
       ▼
Canonical Report
       │
       ▼
Validators
       │
       ▼
Renderer
       │
       ▼
PDF / HTML / Preview
```

---

## 6.1 Report Request

A geração inicia com uma solicitação de relatório.

Exemplos de parâmetros:

- Código do relatório
- Objeto (Paciente, Clínica, etc.)
- Período
- Módulo
- Formato de saída

---

## 6.2 Report Registry

O Registry localiza a definição do relatório e monta o plano de execução.

Define:

- Providers
- Engines
- Sections
- Template
- Renderer

---

## 6.3 Providers

Os Providers coletam e normalizam os dados necessários para o relatório.

Resultado:

```text
Normalized Dataset
```

---

## 6.4 Clinical Engines

Os Engines especializados produzem as Leituras Oficiais de cada domínio.

Exemplos:

- Leitura Clínica
- Leitura Diagnóstica
- Leitura do PTS
- Leitura Assistencial
- Leitura dos Protocolos

Essas leituras representam a Fonte Única da Verdade da plataforma.

---

## 6.5 Report Engine

O Report Engine integra as Leituras Oficiais e produz a narrativa longitudinal do período analisado.

Resultado:

- Narrativas
- Indicadores
- Evidências
- Recomendações do período

---

## 6.6 Report Composer

Organiza o Modelo Canônico do Relatório.

Resultado:

```text
Report
```

---

## 6.7 Validators

Validam:

- Integridade estrutural
- Sections obrigatórias
- Components
- Dados mínimos para geração

Caso necessário, registram warnings.

---

## 6.8 Renderer

Transforma o objeto `Report` no formato solicitado.

Renderers previstos:

- PDF
- HTML
- Preview

---

## Responsabilidades do Pipeline

| Etapa | Responsabilidade |
|--------|------------------|
| Registry | Definir execução |
| Providers | Coletar dados |
| Clinical Engines | Produzir Leituras Oficiais |
| Report Engine | Produzir Narrativa Longitudinal |
| Composer | Montar o Report |
| Validators | Validar estrutura |
| Renderer | Gerar documento |

---

## Princípios

- Cada etapa possui responsabilidade única.
- Nenhuma etapa acessa responsabilidades da etapa seguinte.
- O Report Engine nunca substitui os Engines especializados.
- O Renderer nunca altera conteúdo.
- O PDF é apenas uma representação do objeto `Report`.

---

## Fluxo Conceitual

```text
Dados
      │
      ▼
Providers
      │
      ▼
Leituras Oficiais
(Clinical Engines)
      │
      ▼
Narrativa Longitudinal
(Report Engine)
      │
      ▼
Canonical Report
      │
      ▼
Documento
(PDF / HTML / Preview)
```

# 7. Report Registry

O Report Registry é o catálogo oficial dos relatórios disponíveis no Integra Care.

Sua responsabilidade é registrar como cada relatório deve ser executado, permitindo que novos relatórios sejam adicionados sem alterações no núcleo do Report Engine.

---

## Responsabilidades

- Registrar relatórios disponíveis.
- Definir Providers necessários.
- Definir Engines utilizados.
- Definir Sections.
- Definir Template.
- Definir Renderer.
- Validar parâmetros obrigatórios.

---

## Não faz

- Não consulta banco de dados.
- Não produz inteligência.
- Não gera narrativas.
- Não monta relatórios.
- Não gera PDF.

---

## Report Definition

Todo relatório deve possuir uma definição declarativa.

```text
ReportDefinition

├── code
├── name
├── version
├── domain
├── status
├── providers
├── engines
├── sections
├── template
├── renderer
└── parameters
```

---

## Exemplo

```yaml
code: CLN-001

slug: clinical-longitudinal-report

name: Relatório Longitudinal Inteligente

version: 1.0

domain: Clinical

providers:
  - PatientProvider
  - AssessmentProvider
  - PTSProvider
  - SessionProvider

engines:
  - ClinicalEvolutionEngine
  - AssessmentComparisonEngine
  - PTSAdherenceEngine

sections:
  - ExecutiveSummary
  - CurrentStatus
  - LongitudinalNarrative
  - Sessions
  - PTS
  - Conclusion

template: ClinicalTemplate

renderer: PDFRenderer
```

---

## Identificação dos Relatórios

Os relatórios utilizam códigos padronizados.

Exemplos:

```text
CLN-001  Relatório Longitudinal

CLN-002  Relatório PTS

CLN-003  Relatório de Sessões

FAM-001  Relatório Familiar

MGT-001  Produção Assistencial

OPR-001  Relatório Operadora

GOV-001  Relatório Municipal
```

---

## Ciclo de Vida

Cada relatório possui um status.

```text
DRAFT

IN_REVIEW

ACTIVE

DEPRECATED

ARCHIVED
```

---

## Fluxo

```text
Report Request
        │
        ▼
Report Registry
        │
        ▼
Report Definition
        │
        ▼
Execution Plan
        │
        ▼
Pipeline
```

---

## Princípios

- Todo relatório deve ser registrado.
- O núcleo do Report Engine não conhece relatórios específicos.
- Novos relatórios são adicionados por configuração.
- O Registry é a única fonte oficial de definição dos relatórios.

---

## Estrutura Física

```text
report_engine/

└── registry/

    ├── base_registry.py

    ├── report_definition.py

    ├── registry.py

    └── reports/

        ├── cln_001.py

        ├── fam_001.py

        ├── mgt_001.py

        └── ...
```

# 8. CLN-001 — Relatório Longitudinal Inteligente

O CLN-001 é o primeiro relatório implementado utilizando o Report Engine.

Seu objetivo é validar toda a arquitetura do framework e servir como referência para os demais relatórios da plataforma.

---

## Objetivo

Apresentar a evolução clínica de um paciente durante um período determinado, integrando as Leituras Oficiais produzidas pelos Engines especializados em uma narrativa longitudinal única.

O CLN-001 responde à pergunta:

> **Como evoluiu este paciente durante o período analisado?**

---

## Público-alvo

- Profissionais de Saúde
- Equipe Multidisciplinar
- Coordenadores Clínicos
- Médicos
- Auditorias Clínicas

---

## Parâmetros

- Paciente
- Período
- Módulo Clínico
- Formato de saída

---

## Providers

- PatientProvider
- DiagnosisProvider
- AssessmentProvider
- PTSProvider
- SessionProvider
- LongitudinalProvider
- InterventionProvider
- TimelineProvider
- AnalyticsProvider

---

## Engines Especializados

O CLN-001 reutiliza as Leituras Oficiais produzidas pelos Engines da plataforma.

Exemplos:

- Clinical Engine
- Diagnosis Engine
- Assessment Engine
- PTS Engine
- Session Engine
- Analytics Engine

---

## Estrutura

1. Identificação
2. Resumo Executivo
3. Leitura da Situação Atual
4. Narrativa Longitudinal
5. Linha do Tempo
6. Protocolos
7. Diagnósticos
8. Plano Terapêutico (PTS)
9. Sessões Assistenciais
10. Registro Diário
11. Intervenções
12. Indicadores
13. Conclusão
14. Recomendações

---

## Fluxo

```text
Patient
      │
      ▼
Providers
      │
      ▼
Leituras Oficiais
      │
      ▼
Narrativa Longitudinal
      │
      ▼
Canonical Report
      │
      ▼
PDF
```

---

## Princípios

- Utiliza exclusivamente Leituras Oficiais dos Engines especializados.
- Não recalcula inteligência clínica.
- Produz uma narrativa longitudinal do período.
- Preserva a Fonte Única da Verdade.
- Reutiliza integralmente a arquitetura do Report Engine.

---

## Resultado Esperado

Ao final da geração, o profissional deverá compreender:

- Como o paciente iniciou o período.
- Quais eventos ocorreram.
- Como evoluíram os principais indicadores.
- Como evoluíram os protocolos clínicos.
- Como evoluiu o PTS.
- Como foi a frequência assistencial.
- Qual é a situação clínica atual.
- Quais recomendações decorrem da jornada assistencial.

O CLN-001 estabelece o padrão arquitetural para todos os futuros relatórios do Integra Care.

# 9. Architectural Decision Records (ADRs)

Este capítulo registra as principais decisões arquiteturais adotadas durante a concepção do Report Engine.

Essas decisões orientam toda a evolução do framework e devem ser preservadas em futuras implementações.

---

## ADR-001 — Fonte Única da Verdade

Cada domínio do Integra Care possui apenas uma Leitura Oficial.

Essa leitura é produzida exclusivamente pelo Engine especializado responsável pelo domínio.

O Report Engine nunca substitui, altera ou recalcula essa inteligência.

---

## ADR-002 — Separação entre Inteligência e Comunicação

A produção de inteligência e sua comunicação são responsabilidades distintas.

Os Engines Especializados produzem as Leituras Oficiais.

O Report Engine comunica essas leituras através de uma narrativa longitudinal.

---

## ADR-003 — Estado Atual x Jornada

Os Engines Especializados respondem:

> Como está este domínio neste momento?

O Report Engine responde:

> Como evoluiu durante o período analisado?

Essa separação elimina conflitos entre o Prontuário e os Relatórios.

---

## ADR-004 — Reutilização dos Serviços da Plataforma

Os Providers devem reutilizar serviços e regras já existentes na plataforma.

O Report Engine não implementa regras duplicadas de negócio.

---

## ADR-005 — Conteúdo Independente da Apresentação

O objeto `Report` representa o Modelo Canônico do Relatório.

Templates e Renderers são responsáveis apenas pela apresentação do conteúdo.

Nenhuma decisão visual pode alterar a inteligência produzida pelo framework.

---

## ADR-006 — Arquitetura Baseada em Composição

Um relatório é composto por:

- Providers
- Engines
- Sections
- Components
- Template
- Renderer

Novos relatórios devem ser criados por composição, e não por duplicação de código.

---

## ADR-007 — Registry como Catálogo Oficial

Todo relatório deve possuir uma `ReportDefinition` registrada no Report Registry.

O núcleo do Report Engine não conhece relatórios específicos.

---

## ADR-008 — Narrativa Longitudinal

A principal responsabilidade do Report Engine é produzir a narrativa longitudinal do período analisado.

Essa narrativa integra as Leituras Oficiais produzidas pelos diferentes Engines da plataforma.

---

## ADR-009 — Implementação Incremental

A primeira versão do Report Engine prioriza simplicidade.

Funcionalidades como:

- IA Generativa
- Cache Distribuído
- Execução Paralela
- Persistência de Evidências

permanecem previstas para futuras evoluções.

---

## ADR-010 — Framework de Plataforma

O Report Engine é um framework institucional da plataforma.

Relatórios representam apenas uma das possíveis formas de comunicação da inteligência produzida pelo Integra Care.

A mesma arquitetura poderá ser reutilizada futuramente por:

- Cockpits
- Dashboards
- Assistentes Inteligentes
- APIs
- Outros canais de comunicação

# 10. Roadmap de Implementação

A implementação do Report Engine será realizada de forma incremental, priorizando a validação da arquitetura antes da expansão para novos relatórios.

---

## Fase 1 — Estrutura Base

Objetivo: criar a infraestrutura do framework.

Entregas:

- Estrutura do módulo `report_engine`
- Core
- Models
- Schemas
- Registry
- Base Providers
- Base Renderer
- Base Template

---

## Fase 2 — Pipeline

Objetivo: implementar o pipeline de geração.

Entregas:

- Providers
- Integração com os Engines Especializados
- Report Composer
- Validators
- Canonical Report

---

## Fase 3 — CLN-001

Objetivo: validar toda a arquitetura através do primeiro relatório.

Entregas:

- CLN-001
- PDF Renderer
- Clinical Template
- Geração completa do Relatório Longitudinal Inteligente

---

## Fase 4 — Evolução

Expansão do framework para novos relatórios.

Exemplos:

- CLN-002 — Relatório do PTS
- CLN-003 — Relatório de Sessões
- CLN-004 — Relatório de Avaliações
- FAM-001 — Relatório Familiar
- MGT-001 — Produção Assistencial
- MGT-002 — Dimensionamento
- OPR-001 — Operadoras
- GOV-001 — Gestão Municipal

---

## Evoluções Futuras

Após estabilização da versão 1.0, o framework poderá evoluir com:

- Templates adicionais
- HTML Renderer
- JSON Renderer
- Assinatura Digital
- Geração em lote
- Cache de relatórios
- IA para refinamento da comunicação
- Novos Engines especializados

---

## Critério de Conclusão da Sprint

A Sprint será considerada concluída quando:

- A arquitetura estiver implementada.
- O CLN-001 estiver operacional.
- O PDF for gerado a partir do Modelo Canônico.
- As Leituras Oficiais forem reutilizadas sem duplicação de lógica.
- O framework estiver preparado para suportar novos relatórios por composição.

# 11. Considerações Finais

O Report Engine estabelece a arquitetura institucional para geração de relatórios inteligentes do Integra Care.

Seu objetivo não é apenas produzir documentos, mas comunicar de forma consistente a inteligência gerada pelos diferentes domínios da plataforma.

Ao separar produção de inteligência, composição da narrativa e apresentação do conteúdo, o framework preserva a Fonte Única da Verdade e cria uma base reutilizável para relatórios, dashboards, cockpits e futuros canais de comunicação.

A implementação será incremental, iniciando pelo CLN-001, que servirá como referência arquitetural para toda a evolução do framework.