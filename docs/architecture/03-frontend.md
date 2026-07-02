# Integra Care

# IC-ARC-003

# Arquitetura Frontend

**Versão:** 1.0.0

**Data:** Julho/2026

**Status:** Oficial

**Classificação:** Uso Interno

---

# Objetivo

Documentar a arquitetura do Frontend da plataforma Integra Care, descrevendo sua organização, tecnologias utilizadas e princípios de desenvolvimento.

---

# Tecnologias

O Frontend da plataforma utiliza:

- React
- Vite
- JavaScript
- React Router
- Axios
- CSS

---

# Estrutura

O Frontend está organizado em módulos independentes, permitindo evolução contínua da plataforma.

Principais componentes:

- Login
- Dashboard
- Pacientes
- Prontuário
- Registro Diário
- Avaliações
- Timeline
- Plano Terapêutico Singular (PTS)
- Agenda de Cuidados
- Dimensionamento
- Administração

---

# Organização

A estrutura do projeto segue separação por responsabilidades.

Exemplos:

- páginas
- componentes
- serviços
- hooks
- utilitários
- assets

---

# Comunicação com Backend

Toda comunicação ocorre por meio das APIs REST do Backend.

As requisições utilizam autenticação JWT.

---

# Controle de Acesso

A interface adapta automaticamente menus e funcionalidades conforme o perfil do usuário.

Perfis suportados:

- Administrador
- Administrador de Clínica
- Profissional
- Responsável

---

# Navegação

A navegação da plataforma é baseada em rotas protegidas.

Após autenticação, o usuário acessa apenas os módulos autorizados para seu perfil.

---

# Princípios

O desenvolvimento Frontend observa os seguintes princípios:

- simplicidade;
- reutilização de componentes;
- padronização visual;
- baixo acoplamento;
- facilidade de manutenção.

---

# Evolução

Novas funcionalidades deverão reutilizar componentes existentes sempre que possível.

Mudanças estruturais deverão ser documentadas e avaliadas quanto ao impacto arquitetural.

---

# Documentos Relacionados

- IC-ARC-001 — Arquitetura da Plataforma
- IC-ARC-002 — Arquitetura Backend

---

# Histórico de Revisões

| Versão | Data | Descrição |
|---------|------|-----------|
| 1.0.0 | Julho/2026 | Criação do documento |

---

> Este documento integra o acervo oficial de documentação do Integra Care.