# API Oficial --- Integra Care

> **Versão:** 1.0.0\
> **Empresa:** Meyio DDS Digital\
> **Documento:** 10_API.md\
> **Status:** Oficial

------------------------------------------------------------------------

# 1. Objetivo

Documentar a API oficial do Integra Care, sua finalidade, seus
princípios arquiteturais, autenticação, autorização, organização
funcional e regras de integração.

Este documento não substitui o Swagger/OpenAPI. A documentação
interativa representa o contrato técnico atual dos endpoints; este
arquivo registra a arquitetura, a governança e os princípios de uso da
API.

# 2. Papel da API

A API é o núcleo de integração da plataforma:

``` text
Portal Profissional ─┐
                     │
APP do Responsável ──┼──► API Integra Care ──► PostgreSQL
                     │
Futuras Integrações ─┘
```

Entre suas principais responsabilidades estão:

-   autenticação;
-   autorização;
-   aplicação das regras de negócio;
-   persistência de dados;
-   Registro Longitudinal;
-   PTS;
-   Agenda de Cuidados;
-   avaliações e protocolos;
-   indicadores;
-   analytics.

# 3. Tecnologias

A API utiliza:

-   FastAPI
-   Python
-   SQLAlchemy
-   Alembic
-   PostgreSQL
-   JWT
-   Swagger / OpenAPI
-   Docker

# 4. Ambientes da API

## DEV

API local utilizada para desenvolvimento e testes iniciais.

## HML

API de Homologação utilizada para testes integrados e validação antes da
publicação.

## Produção

Domínio oficial:

`https://api.care.meyio.com.br`

Documentação Swagger:

`https://api.care.meyio.com.br/docs`

# 5. Princípios Arquiteturais

A API segue os seguintes princípios:

-   API centralizada;
-   separação entre frontend e backend;
-   arquitetura multi-clínica;
-   arquitetura multi-módulo;
-   controle por perfil;
-   regras de negócio centralizadas no backend;
-   rastreabilidade;
-   compatibilidade com futuras integrações.

# 6. Autenticação

Fluxo conceitual:

``` text
Login
  ↓
Validação de credenciais
  ↓
Token JWT
  ↓
Requisições autenticadas
  ↓
Validação de perfil e escopo
```

Credenciais, tokens reais, chaves e segredos não devem ser registrados
nesta documentação.

# 7. Perfis e Autorização

A API considera os principais perfis:

-   `ADMIN`
-   `ADMIN_CLINICA`
-   `PROFISSIONAL`
-   `RESPONSAVEL`

Além do perfil, o acesso pode depender dos vínculos com:

-   clínica;
-   profissional;
-   paciente;
-   responsável;
-   módulo clínico.

> **Autenticar identifica quem é o usuário. Autorizar define o que ele
> pode acessar.**

# 8. Organização Funcional dos Endpoints

Os endpoints são organizados conceitualmente pelos seguintes domínios:

-   Autenticação e Usuário Atual
-   Clínicas
-   Usuários
-   Profissionais
-   Responsáveis
-   Pacientes
-   Módulos Clínicos
-   Registros Longitudinais
-   Intervenções
-   Avaliações e Protocolos
-   Plano Terapêutico Singular
-   Objetivos Terapêuticos
-   Atividades Terapêuticas
-   Ocupações Profissionais
-   Agenda de Cuidados
-   Dimensionamento
-   Neurodesenvolvimento
-   Cardiometabólico
-   Dashboards e Analytics
-   APP do Responsável

A lista técnica atualizada de rotas, parâmetros e schemas deve ser
consultada no Swagger/OpenAPI do ambiente correspondente.

# 9. Padrões de Requisição e Resposta

O formato principal de comunicação é JSON.

A API utiliza códigos HTTP para representar o resultado das operações.

  Código   Significado
  -------- -------------------------
  `200`    Sucesso
  `201`    Recurso criado
  `400`    Requisição inválida
  `401`    Usuário não autenticado
  `403`    Acesso negado
  `404`    Recurso não encontrado
  `409`    Conflito
  `422`    Erro de validação
  `500`    Erro interno

As requisições devem respeitar:

-   schemas definidos;
-   tipos de dados;
-   campos obrigatórios;
-   regras de negócio;
-   permissões do usuário.

# 10. Registro Longitudinal

O Registro Longitudinal é um dos principais elementos arquiteturais do
Integra Care.

A API consolida eventos provenientes de diferentes origens e linhas de
cuidado, preservando informações como:

-   paciente;
-   módulo;
-   tipo de evento;
-   data;
-   origem;
-   conteúdo clínico.

Essa estrutura permite acompanhar a jornada assistencial do paciente ao
longo do tempo.

# 11. Integração com Portal e APP

## Portal Profissional

O Portal consome a API conforme:

-   perfil do usuário;
-   clínica;
-   permissões;
-   linhas de cuidado habilitadas.

## APP do Responsável

O APP utiliza fluxos próprios para o responsável e respeita os vínculos
entre paciente e responsável.

Portal e APP compartilham o mesmo núcleo longitudinal da plataforma.

# 12. Swagger e OpenAPI

O Swagger é a referência dinâmica para:

-   visualizar os endpoints atuais;
-   consultar schemas;
-   verificar parâmetros;
-   consultar respostas;
-   testar requisições autorizadas.

> **O Swagger representa o contrato técnico atual. O `10_API.md`
> representa a arquitetura, a governança e os princípios de uso da
> API.**

# 13. Versionamento da API

Na versão `v1.0.0`, a API evolui junto com a plataforma.

Para futuras integrações externas e contratos públicos de integração,
poderá ser adotado versionamento explícito, por exemplo:

``` text
/api/v1/
```

Essa estrutura será implementada somente quando houver necessidade
arquitetural validada.

# 14. Segurança

A API utiliza princípios como:

-   HTTPS;
-   autenticação JWT;
-   controle por perfil;
-   isolamento multi-clínica;
-   permissões por módulo;
-   validação de entrada;
-   segredos fora do código;
-   CORS controlado.

Detalhes complementares são tratados no `12_SEGURANCA.md`.

# 15. Integrações Futuras

A arquitetura deverá permitir evolução para integrações autorizadas com:

-   operadoras;
-   hospitais;
-   municípios;
-   sistemas legados;
-   parceiros tecnológicos;
-   padrões de interoperabilidade.

Toda integração deverá preservar segurança, rastreabilidade e governança
dos dados.

# 16. Governança da API

Toda mudança relevante deverá seguir:

**Planejamento → Desenvolvimento → Testes → HML → Validação →
Documentação → Produção**

Mudanças que alterem contratos existentes exigem análise de:

-   compatibilidade;
-   impacto no Portal;
-   impacto no APP;
-   impacto em integrações;
-   migração de dados, quando aplicável.

# 17. Limites deste Documento

Este arquivo não deve armazenar:

-   tokens;
-   senhas;
-   segredos;
-   chaves privadas;
-   credenciais;
-   dados reais de pacientes;
-   cópia integral e duplicada de todos os endpoints.

Essa separação mantém a documentação segura, sustentável e alinhada à
evolução técnica da plataforma.

# 18. Considerações Finais

A API é o núcleo de integração e aplicação das regras de negócio do
Integra Care.

Sua evolução deve preservar:

-   segurança;
-   compatibilidade;
-   rastreabilidade;
-   isolamento de acesso;
-   consistência dos dados;
-   capacidade de expansão.

------------------------------------------------------------------------

**© Meyio DDS Digital**

**Integra Care --- Plataforma Modular de Gestão Longitudinal de Linhas
de Cuidado**
