# Integra Care

# Documento Técnico

# Arquitetura Backend

Versão: 1.0.0

Status: Oficial

---

# 1. Objetivo

O backend do Integra Care foi desenvolvido utilizando FastAPI seguindo princípios de modularidade, separação de responsabilidades e escalabilidade.

A arquitetura permite evolução contínua sem necessidade de reestruturação do núcleo da aplicação.

---

# 2. Stack Tecnológica

Linguagem

- Python 3.11

Framework

- FastAPI

ORM

- SQLAlchemy

Migrações

- Alembic

Banco

- PostgreSQL

Autenticação

- JWT

Documentação

- OpenAPI / Swagger

Containerização

- Docker

---

# 3. Estrutura

app/

routers/

services/

models/

schemas/

core/

database.py

main.py

---

# 4. Responsabilidades

Routers

Recebem requisições HTTP.

Não possuem regra de negócio.

---

Services

Executam regras de negócio.

Concentram toda lógica da aplicação.

---

Models

Representam entidades do banco.

---

Schemas

Validam entrada e saída das APIs.

---

Core

Configuração.

Segurança.

Autenticação.

---

# 5. Fluxo

Cliente

↓

Router

↓

Service

↓

Model

↓

Banco

↓

Resposta

---

# 6. Princípios

Separação de responsabilidades.

Baixo acoplamento.

Alta coesão.

Código reutilizável.

Testabilidade.

---

# 7. Convenções

Toda API deverá possuir:

Router

Schema

Model

Service

Documentação

---

# 8. Segurança

JWT

Hash de senhas

Validação de permissões

Perfis

ADMIN

ADMIN_CLINICA

PROFISSIONAL

RESPONSAVEL

---

# 9. Versionamento

As APIs deverão permanecer compatíveis sempre que possível.

Mudanças incompatíveis deverão gerar nova versão.

---

# 10. Escalabilidade

Novos módulos deverão reutilizar:

Autenticação

Registro Longitudinal

Framework Universal

PTS

Agenda

Analytics