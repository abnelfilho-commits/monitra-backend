# Changelog do Integra Care

Todas as mudanças relevantes do **Integra Care** serão documentadas
neste arquivo.

Este documento é baseado nos princípios do **Keep a Changelog** e
utiliza **Versionamento Semântico**.

------------------------------------------------------------------------

## \[Unreleased\]

### Added

-   Planejamento Financeiro Assistencial
-   Evolução do Dimensionamento Inteligente
-   Preparação e documentação do Case Mirassol
-   Planejamento da Linha de Cuidado Oncológica
-   Conclusão da Biblioteca Oficial
-   Sprint BOOK 1.0

------------------------------------------------------------------------

## \[1.0.0\] --- 03/07/2026

### Added

-   Portal Profissional
-   APP do Responsável
-   Linha de Cuidado Neurodesenvolvimento
-   Linha de Cuidado Cardiometabólico
-   Arquitetura multi-clínica
-   Arquitetura multi-módulo
-   Registro Longitudinal
-   Timeline consolidada
-   Intervenções
-   Framework de Avaliações
-   Protocolo M-CHAT
-   Método Denver
-   Plano Terapêutico Singular (PTS)
-   Objetivos terapêuticos
-   Atividades terapêuticas
-   Ocupações profissionais
-   Agenda de Cuidados
-   Dimensionamento de Equipe
-   Dashboards assistenciais
-   Analytics
-   Perfis `ADMIN`, `ADMIN_CLINICA`, `PROFISSIONAL` e `RESPONSAVEL`

### Changed

-   Evolução do antigo conceito Monitra para **Integra Care**
-   Consolidação do produto como Plataforma Modular de Gestão
    Longitudinal de Linhas de Cuidado
-   Padronização dos ambientes DEV, HML e Produção
-   Definição do fluxo oficial `DEV → HML → Validação → Produção`
-   Adoção dos novos domínios institucionais
-   Separação definitiva entre Portal Profissional e APP do Responsável

### Fixed

-   Persistência e exibição dos registros longitudinais
-   Isolamento de dados por linha de cuidado
-   Timeline Neuro e Cardiometabólico
-   Cálculos e indicadores Cardiometabólicos
-   Navegação conforme perfil do usuário
-   Fluxo do APP do Responsável
-   Sincronização estrutural entre HML e Produção

### Security

-   Autenticação JWT
-   Controle de acesso por perfis
-   Isolamento multi-clínica
-   Permissões por módulo
-   HTTPS nos domínios oficiais
-   Desativação de acessos não autorizados
-   Remoção dos domínios antigos da operação

### Infrastructure

-   Backend hospedado na Render
-   Portal Profissional hospedado na Vercel
-   APP do Responsável hospedado na Vercel
-   Banco de dados PostgreSQL
-   Containers Docker
-   Migrações com Alembic
-   Ambientes DEV, HML e Produção
-   Primeiro merge oficial de Homologação para Produção
-   Backups completos de Produção e Homologação
-   Domínio oficial do Portal: `https://care.meyio.com.br`
-   Domínio oficial do APP: `https://app.care.meyio.com.br`
-   Domínio oficial da API: `https://api.care.meyio.com.br`

### Documentation

-   `00_HOME.md`
-   `01_VISAO_GERAL.md`
-   `02_ARQUITETURA.md`
-   `05_ADMINISTRADOR.md`
-   `06_PROFISSIONAL.md`
-   `07_RESPONSAVEL_APP.md`
-   `08_GUIA_IMPLANTACAO.md`
-   `09_REGRAS_NEGOCIO.md`
-   `13_RELEASES.md`
-   `14_PLANO_DIRETOR.md`

------------------------------------------------------------------------

# Regra de Manutenção

Toda alteração relevante deverá ser registrada inicialmente na seção:

``` text
[Unreleased]
```

No momento da publicação de uma nova versão, as alterações deverão ser
movidas para uma seção identificada pela versão e pela data:

``` text
[Unreleased]
      ↓
[nova versão] — data
```

O `CHANGELOG.md` integra o processo oficial de evolução e publicação do
Integra Care.

Fluxo de release:

**Desenvolvimento → HML → Validação → Documentação → Produção → Registro
da Release**

------------------------------------------------------------------------

**© Meyio DDS Digital**

**Integra Care --- Plataforma Modular de Gestão Longitudinal de Linhas
de Cuidado**
