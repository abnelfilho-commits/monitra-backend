# ADR-002

# Framework Universal de Avaliações

**Status:** Aprovado

**Data:** Julho/2026

---

# Contexto

A plataforma precisava suportar diversos protocolos clínicos sem criar uma implementação específica para cada instrumento.

A criação de um módulo independente para cada avaliação aumentaria significativamente o custo de manutenção e reduziria a capacidade de expansão.

---

# Decisão

Construir um Framework Universal capaz de reutilizar a mesma infraestrutura para diferentes instrumentos clínicos.

Cada protocolo compartilha:

- formulários;
- campos;
- regras;
- motor de cálculo;
- histórico;
- visualização.

---

# Consequências

## Positivas

- reutilização;
- padronização;
- manutenção simplificada;
- rápida incorporação de novos protocolos.

---

# Impacto

O Framework Universal torna-se a base para expansão clínica da plataforma.

Novos protocolos passam a ser adicionados utilizando a mesma infraestrutura.

---

# Justificativa

A decisão reduz significativamente o custo de evolução do produto e aumenta sua escalabilidade.