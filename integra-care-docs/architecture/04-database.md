# Integra Care

# IC-ARC-004

# Arquitetura do Banco de Dados

**Versão:** 1.0.0

**Data:** Julho/2026

**Status:** Oficial

**Classificação:** Uso Interno

---

# Objetivo

Documentar a arquitetura do banco de dados da plataforma Integra Care, apresentando sua organização, princípios de modelagem e principais componentes utilizados para suportar os módulos clínicos, assistenciais e operacionais.

---

# Visão Geral

O Integra Care utiliza banco de dados relacional PostgreSQL como repositório central das informações da plataforma.

A modelagem foi desenvolvida para suportar uma arquitetura longitudinal, permitindo registrar toda a evolução assistencial do paciente e reutilizar essas informações em diferentes módulos da plataforma.

---

# Tecnologias

- PostgreSQL
- SQLAlchemy
- Alembic
- Docker

---

# Princípios da Modelagem

O banco de dados foi projetado seguindo os seguintes princípios:

- normalização dos dados;
- reutilização de entidades;
- integridade referencial;
- rastreabilidade;
- escalabilidade;
- separação entre dados clínicos, assistenciais e administrativos.

---

# Organização

As principais entidades da plataforma estão agrupadas em domínios funcionais.

## Administração

- Usuários
- Perfis
- Clínicas
- Profissionais
- Responsáveis

---

## Pacientes

- Pacientes
- Vínculos
- Módulos Clínicos

---

## Registro Longitudinal

- Registros
- Respostas
- Timeline
- Histórico

---

## Avaliações

- Formulários
- Campos
- Protocolos
- Resultados

---

## Gestão Assistencial

- Plano Terapêutico Singular
- Objetivos
- Agenda de Cuidados

---

## Gestão Operacional

- Atividades Terapêuticas
- Ocupações
- Dimensionamento

---

# Integridade

A integridade dos dados é garantida por meio de:

- chaves primárias;
- chaves estrangeiras;
- restrições de integridade;
- validações realizadas pela aplicação.

---

# Migrações

Toda alteração estrutural deverá ser realizada por meio do Alembic.

Não deverão ser executadas alterações diretamente no banco de produção sem versionamento.

---

# Evolução

Novas tabelas deverão seguir os padrões estabelecidos pela arquitetura da plataforma.

Sempre que possível deverão reutilizar estruturas existentes.

Alterações relevantes deverão ser documentadas e, quando necessário, registradas por meio de ADR.

---

# Backup e Recuperação

Os ambientes oficiais deverão possuir rotina de backup e procedimentos documentados de recuperação.

Esses procedimentos encontram-se descritos na documentação de Deploy e Operação.

---

# Documentos Relacionados

- IC-ARC-001 — Arquitetura da Plataforma
- IC-ARC-002 — Arquitetura Backend
- IC-ARC-003 — Arquitetura Frontend

---

# Histórico de Revisões

| Versão | Data | Descrição |
|---------|------|-----------|
| 1.0.0 | Julho/2026 | Criação do documento |

---

> Este documento integra o acervo oficial de documentação do Integra Care.