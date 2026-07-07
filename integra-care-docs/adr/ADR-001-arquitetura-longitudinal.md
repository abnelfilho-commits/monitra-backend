# ADR-001

# Adoção da Arquitetura Longitudinal

**Status:** Aprovado

**Data:** Julho/2026

**Versão:** 1.0.0

---

# Contexto

Os prontuários eletrônicos tradicionais armazenam informações de forma episódica, tratando cada atendimento como um evento independente.

Esse modelo dificulta a análise da evolução clínica do paciente, reduzindo a capacidade de identificar tendências, padrões e resultados do cuidado ao longo do tempo.

O Integra Care foi concebido para resolver esse problema.

---

# Decisão

Adotar uma arquitetura longitudinal como núcleo da plataforma.

Todas as informações produzidas durante a assistência passam a compor uma linha do tempo única do paciente.

Essa linha do tempo torna-se a principal fonte de informação para todas as demais camadas da plataforma.

---

# Consequências

## Positivas

- visão completa da evolução clínica;
- reutilização dos dados;
- suporte à tomada de decisão;
- cálculo de indicadores;
- integração entre módulos.

## Negativas

- maior complexidade inicial de modelagem;
- necessidade de padronização das estruturas de dados;
- maior responsabilidade sobre consistência temporal.

---

# Impacto Arquitetural

A arquitetura longitudinal torna-se o núcleo da plataforma.

Todos os módulos passam a consumir informações produzidas nesse histórico.

Entre eles:

- Framework Universal
- PTS
- Agenda
- Dimensionamento
- Analytics
- Inteligência Financeira Assistencial

---

# Justificativa

Essa decisão permite que novas funcionalidades sejam adicionadas sem necessidade de duplicação de dados ou reestruturação da plataforma.

O Registro Longitudinal torna-se um ativo estratégico permanente do Integra Care.