# Arquitetura da Plataforma Integra Care

> **Versão:** 1.0.0\
> **Data:** 03/07/2026\
> **Empresa:** Meyio DDS Digital\
> **Documento:** 02_ARQUITETURA.md\
> **Status:** Oficial

> **"Uma única plataforma. Um único núcleo assistencial. Múltiplas
> linhas de cuidado."**

------------------------------------------------------------------------

# 1. Objetivo

Este documento apresenta a arquitetura oficial do **Integra Care**,
descrevendo os princípios arquiteturais, a organização dos componentes,
os ambientes, os fluxos operacionais e as decisões que sustentam a
evolução da plataforma.

Seu objetivo é fornecer uma visão completa para desenvolvedores,
arquitetos de software, equipes de infraestrutura e gestores técnicos.

# 2. Visão Arquitetural

O Integra Care foi concebido como uma **plataforma modular de gestão
longitudinal de linhas de cuidado**.

Sua arquitetura permite que diferentes especialidades compartilhem uma
infraestrutura única, preservando regras clínicas específicas de cada
contexto assistencial.

# 3. Princípios Arquiteturais

-   Plataforma única
-   Núcleo assistencial compartilhado
-   Regras clínicas independentes
-   Escalabilidade por linhas de cuidado
-   Reutilização máxima de componentes

# 4. Arquitetura Conceitual

``` text
                     Integra Care

              Plataforma Central

                      │

      ┌───────────────┼───────────────┐

      ▼               ▼               ▼

 Neurodesenvolvimento Cardiometabólico Oncologia*

      └───────────────┼───────────────┘

                      ▼

           Registro Longitudinal

                      ▼

            Analytics Assistencial

                      ▼

           Dashboards Estratégicos
```

\* Linha prevista no roadmap.

# 5. Arquitetura Física

``` text
care.meyio.com.br
Portal Profissional (React + Vite)

app.care.meyio.com.br
APP Responsável (React + Vite)

api.care.meyio.com.br
Backend (FastAPI)

PostgreSQL
Docker
```

# 6. Componentes

## Portal Profissional

-   Administração
-   Profissionais
-   Gestores
-   Dashboards
-   PTS
-   Agenda
-   Registro Longitudinal

## APP do Responsável

-   Login
-   Registro Diário
-   Histórico
-   Acompanhamento

## API

-   Regras de negócio
-   Autenticação
-   Analytics
-   Persistência

## Banco de Dados

PostgreSQL como banco relacional central.

# 7. Arquitetura de Software

## Backend

-   FastAPI
-   SQLAlchemy
-   Alembic
-   PostgreSQL
-   Docker

Estrutura:

``` text
app/
├── routers
├── services
├── models
├── schemas
├── database
├── security
├── utils
└── core
```

## Frontend

-   React
-   Vite

``` text
src/
├── pages
├── components
├── services
├── hooks
├── contexts
├── layouts
└── utils
```

# 8. Ambientes

  Ambiente   Objetivo
  ---------- ------------------
  DEV        Desenvolvimento
  HML        Homologação
  Produção   Operação oficial

Fluxo:

``` text
DEV
 ↓
HML
 ↓
Validação
 ↓
Produção
```

# 9. Fluxo de Autenticação

``` text
Usuário
 ↓
Portal / APP
 ↓
JWT
 ↓
API
 ↓
Banco
 ↓
Acesso autorizado
```

# 10. Fluxo Assistencial

``` text
Paciente
 ↓
PTS
 ↓
Objetivos
 ↓
Agenda
 ↓
Registro Diário
 ↓
Intervenções
 ↓
Timeline
 ↓
Analytics
 ↓
Dashboards
```

# 11. Fluxo Financeiro Assistencial

``` text
PTS
 ↓
Agenda
 ↓
Procedimentos
 ↓
Plano
 ↓
Tabela
 ↓
Custos
 ↓
Receitas
 ↓
Resultado Financeiro
```

# 12. Fluxo Oncológico (Roadmap)

``` text
Diagnóstico
 ↓
PTS Oncológico
 ↓
Protocolo
 ↓
Medicamentos
 ↓
Sessões
 ↓
Registro Longitudinal
 ↓
Indicadores
 ↓
Resultados
```

# 13. Segurança

-   HTTPS
-   JWT
-   Multi-clínica
-   Multi-módulo
-   Controle de perfis
-   Preparado para LGPD

# 14. Deploy

  Camada       Tecnologia
  ------------ ------------
  Portal       Vercel
  APP          Vercel
  Backend      Render
  Banco        PostgreSQL
  Containers   Docker

Domínios:

-   https://care.meyio.com.br
-   https://app.care.meyio.com.br
-   https://api.care.meyio.com.br

# 15. Escalabilidade

``` text
Integra Care
      │
Núcleo Compartilhado
      │
Neuro | Cardio | Oncologia | Futuras Linhas
```

# 16. Roadmap Arquitetural

## Curto Prazo

-   Planejamento Financeiro Assistencial
-   Dimensionamento Inteligente
-   Documentação Oficial

## Médio Prazo

-   Linha de Cuidado Oncológica
-   Dashboards Executivos
-   IA Assistencial

## Longo Prazo

-   Novas linhas de cuidado
-   APIs públicas
-   Ecossistema Integra Care

# 17. ADRs

-   ADR-001 --- Plataforma modular por linhas de cuidado.
-   ADR-002 --- Registro longitudinal como núcleo.
-   ADR-003 --- API única para Portal e APP.
-   ADR-004 --- Núcleo assistencial compartilhado.
-   ADR-005 --- PTS como centro do planejamento.
-   ADR-006 --- Planejamento Financeiro derivado da assistência.
-   ADR-007 --- Crescimento por linhas de cuidado.

# 18. Considerações Finais

A arquitetura do Integra Care foi projetada para evoluir continuamente,
permitindo incorporar novas linhas de cuidado sem comprometer
estabilidade, padronização e reutilização dos componentes.

------------------------------------------------------------------------

**© Meyio DDS Digital**

**Integra Care --- Plataforma Modular de Gestão Longitudinal de Linhas
de Cuidado**
