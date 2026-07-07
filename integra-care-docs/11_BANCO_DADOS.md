# Banco de Dados --- Integra Care

> **Versão:** 1.0.0\
> **Empresa:** Meyio DDS Digital\
> **Documento:** 11_BANCO_DADOS.md\
> **Status:** Oficial

------------------------------------------------------------------------

# 1. Objetivo

Documentar a arquitetura de dados do Integra Care, seus princípios,
principais domínios, relacionamentos, migrações, ambientes e regras de
governança.

Este documento não reproduz integralmente o schema SQL. Seu objetivo é
explicar como os dados estão organizados, como os principais domínios se
relacionam e quais regras protegem a consistência, a rastreabilidade e a
segurança das informações.

# 2. Tecnologia

A camada de dados utiliza:

-   PostgreSQL
-   SQLAlchemy como ORM
-   Alembic para migrações
-   Docker no ambiente local

Arquitetura conceitual:

``` text
Portal Profissional ─┐
                     │
APP do Responsável ──┼──► API FastAPI
                     │          ↓
Futuras Integrações ─┘      SQLAlchemy
                                ↓
                           PostgreSQL
```

# 3. Princípios da Arquitetura de Dados

A arquitetura segue os seguintes princípios:

-   banco relacional;
-   integridade referencial;
-   arquitetura multi-clínica;
-   arquitetura multi-módulo;
-   histórico longitudinal;
-   rastreabilidade;
-   separação entre identidade do paciente e suas linhas de cuidado;
-   evolução controlada por migrações;
-   preservação do histórico assistencial.

> **Um paciente possui uma identidade única na plataforma e pode
> participar de múltiplas linhas de cuidado.**

# 4. Organização por Domínios

## Institucional

Abrange entidades relacionadas a:

-   clínicas;
-   usuários;
-   profissionais;
-   responsáveis.

## Pacientes e Vínculos

Abrange:

-   pacientes;
-   paciente ↔ módulo;
-   paciente ↔ responsável;
-   profissional ↔ módulo.

## Núcleo Longitudinal

Abrange:

-   registros;
-   respostas;
-   eventos;
-   Timeline;
-   origem dos registros.

## Avaliações

Abrange:

-   formulários;
-   campos;
-   respostas;
-   resultados;
-   protocolos.

## Planejamento Assistencial

Abrange:

-   PTS;
-   objetivos;
-   atividades terapêuticas;
-   ocupações profissionais;
-   vínculos atividade ↔ ocupação;
-   Agenda de Cuidados.

## Inteligência

Abrange estruturas utilizadas para:

-   indicadores;
-   scores;
-   riscos;
-   tendências;
-   views;
-   analytics.

# 5. Arquitetura Multi-Clínica

Estrutura conceitual:

``` text
Plataforma
    ↓
Clínicas
    ↓
Usuários / Profissionais / Pacientes
```

A clínica funciona como uma dimensão fundamental de isolamento
institucional.

> **Usuários sem permissão global devem acessar somente os dados
> compatíveis com seu vínculo institucional.**

A aplicação das regras de acesso deve ocorrer de forma coordenada entre
autenticação, autorização, consultas e regras de negócio.

# 6. Arquitetura Multi-Módulo

Estrutura conceitual:

``` text
Paciente
   │
   ├── Neurodesenvolvimento
   │
   ├── Cardiometabólico
   │
   └── Futuras linhas
```

A relação entre paciente e linha de cuidado não exige a duplicação do
cadastro principal do paciente.

Esse princípio permite:

-   visão integrada;
-   expansão modular;
-   redução de duplicidade;
-   preservação da identidade única do paciente.

# 7. Núcleo Longitudinal

O histórico do paciente pode reunir eventos de diferentes tipos:

-   Registro Diário;
-   Avaliação;
-   Intervenção;
-   PTS;
-   evolução clínica;
-   outros eventos futuros.

Modelo conceitual:

``` text
Paciente
   ↓
Linha de Cuidado
   ↓
Eventos ao Longo do Tempo
   ↓
Timeline
   ↓
Indicadores e Analytics
```

O núcleo longitudinal deve preservar contexto, origem, data e vínculo
com a linha de cuidado.

# 8. Formulários e Respostas Dinâmicas

A arquitetura utiliza estruturas como:

-   `formularios_modulo`;
-   `campos_formulario`;
-   `respostas_registro`.

Esse modelo permite evoluir formulários e informações clínicas sem
exigir uma nova coluna fixa para cada dado coletado.

A abordagem favorece:

-   flexibilidade;
-   reutilização;
-   expansão por linha de cuidado;
-   evolução controlada dos instrumentos.

# 9. Plano Terapêutico Singular

Relacionamento conceitual:

``` text
Paciente
   ↓
PTS
   ↓
Objetivos
   ↓
Agenda de Cuidados
   ↓
Atividades Terapêuticas
   ↓
Ocupações Profissionais
```

> **O planejamento assistencial deve permanecer vinculado ao paciente, à
> linha de cuidado e ao histórico do PTS.**

O encerramento de um PTS não deve eliminar seu histórico.

# 10. Views e Camada Analítica

Views podem ser utilizadas para:

-   consolidação da Timeline;
-   consultas analíticas;
-   redução de duplicação de lógica;
-   apoio aos dashboards.

> **Views são parte da arquitetura do banco e devem evoluir de forma
> coordenada com tabelas, modelos e endpoints.**

Alterações estruturais devem avaliar explicitamente o impacto sobre
views existentes.

# 11. Identificadores e Relacionamentos

A arquitetura utiliza:

-   chaves primárias;
-   chaves estrangeiras;
-   integridade referencial;
-   relações explícitas;
-   prevenção de duplicidades;
-   constraints, quando aplicável.

Exemplos conceituais:

``` text
paciente_id
clinica_id
modulo_id
profissional_id
responsavel_id
pts_id
objetivo_id
atividade_id
ocupacao_id
```

Os relacionamentos devem preservar clareza e rastreabilidade entre os
domínios.

# 12. Migrações com Alembic

Fluxo oficial:

``` text
Alteração do modelo
      ↓
Migração
      ↓
Teste em DEV
      ↓
Aplicação em HML
      ↓
Validação
      ↓
Backup
      ↓
Aplicação em Produção
```

> **Alterações estruturais no banco devem ser rastreáveis e
> reproduzíveis.**

Alterações manuais em Produção devem ser evitadas e nunca realizadas sem
documentação, avaliação de impacto e plano de recuperação.

# 13. Ambientes de Banco

A plataforma utiliza bancos distintos para:

-   DEV;
-   HML;
-   Produção.

> **Cada ambiente deve possuir seu próprio banco e suas próprias
> credenciais.**

O ambiente DEV nunca deve apontar para HML ou Produção.

# 14. Backup e Restauração

Princípios obrigatórios:

-   realizar backup antes de operações sensíveis;
-   identificar claramente o ambiente de origem;
-   identificar claramente o ambiente de destino;
-   validar a restauração;
-   verificar compatibilidade estrutural;
-   registrar a operação.

> **Restaurar um banco não é apenas copiar dados. É necessário garantir
> compatibilidade entre estrutura, migrações e código publicado.**

# 15. Dados Sensíveis

Este documento não deve armazenar:

-   senhas;
-   credenciais;
-   connection strings reais;
-   dados reais de pacientes;
-   dumps;
-   tokens;
-   segredos.

Exemplos técnicos devem utilizar dados fictícios.

# 16. Regras de Integridade

A arquitetura deve preservar as seguintes regras:

-   não duplicar o paciente por linha de cuidado;
-   não apagar histórico por simples desativação de usuário;
-   preservar o vínculo entre evento e módulo;
-   preservar a origem do registro;
-   impedir inconsistências por duplicidade;
-   manter datas assistenciais distintas das datas técnicas, quando
    necessário.

# 17. Governança de Alterações

Toda mudança relevante no banco deve avaliar impacto em:

-   models;
-   schemas;
-   routers;
-   services;
-   views;
-   endpoints;
-   Portal Profissional;
-   APP do Responsável;
-   relatórios;
-   dashboards;
-   migrações.

Uma mudança no banco raramente afeta apenas a camada de dados.

# 18. Documentação Técnica Detalhada

A estrutura exata e atualizada deve ser consultada por meio de:

-   models SQLAlchemy;
-   migrations Alembic;
-   schema real do PostgreSQL;
-   documentação arquitetural vigente.

O `11_BANCO_DADOS.md` representa a visão oficial da arquitetura de dados
e não um dump estático do banco.

# 19. Evolução Futura

A arquitetura deverá suportar a evolução para:

-   Linha de Cuidado Oncológica;
-   Planejamento Financeiro Assistencial;
-   novas linhas de cuidado;
-   integrações;
-   interoperabilidade;
-   crescimento do volume longitudinal;
-   analytics avançado.

# 20. Considerações Finais

> **No Integra Care, o banco de dados não representa apenas o estado
> atual do paciente. Ele preserva a história da sua jornada
> assistencial.**

A arquitetura de dados deve evoluir sem perder:

-   integridade;
-   rastreabilidade;
-   isolamento;
-   histórico;
-   capacidade de expansão.

------------------------------------------------------------------------

**© Meyio DDS Digital**

**Integra Care --- Plataforma Modular de Gestão Longitudinal de Linhas
de Cuidado**
