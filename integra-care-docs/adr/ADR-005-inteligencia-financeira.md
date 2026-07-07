# ADR-005

# Inteligência Financeira Assistencial

---

# Contexto

Durante apresentações comerciais surgiu a necessidade de apoiar clínicas e operadoras na estimativa de custos e planejamento econômico da assistência.

---

# Decisão

Criar uma camada de Inteligência Financeira Assistencial construída sobre estruturas já existentes da plataforma.

Não será desenvolvido um módulo financeiro tradicional.

A nova camada utilizará informações provenientes de:

- PTS
- Agenda
- Dimensionamento
- Protocolos
- Registro Longitudinal

---

# Objetivo

Produzir:

- estimativas de custos;
- simulações;
- precificação;
- apoio à negociação;
- dashboards financeiros.

---

# Justificativa

A reutilização da infraestrutura assistencial preserva a simplicidade arquitetural e fortalece a integração entre as camadas da plataforma.