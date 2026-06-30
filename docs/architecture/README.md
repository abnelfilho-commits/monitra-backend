# Integra Care — Arquitetura da Plataforma

Versão: 1.0

---

# Objetivo

O Integra Care é uma plataforma de gestão longitudinal da saúde baseada em evidências clínicas.

Sua arquitetura foi concebida para suportar múltiplas linhas de cuidado (Neuro, Cardiometabólico, Saúde Mental, Geriatria, entre outras), reutilizando a mesma infraestrutura tecnológica.

O princípio fundamental é que toda inteligência clínica seja centralizada no Backend, permitindo que diferentes interfaces (Portal Profissional, App do Responsável, Dashboards, Relatórios e IA futura) utilizem uma única fonte de verdade.

---

# Pilares da Plataforma

## 1. Registro Longitudinal

Responsável por armazenar os dados clínicos coletados ao longo do tempo.

Componentes:

* formularios_modulo
* campos_formulario
* registros_longitudinais
* respostas_registro

---

## 2. Motor Universal de Avaliações Clínicas

Infraestrutura responsável por interpretar protocolos clínicos padronizados.

Exemplos:

* M-CHAT
* Denver II
* CARS
* VB-MAPP

Todos os instrumentos seguem a mesma interface de execução.

---

## 3. Clinical Engine

Responsável por correlacionar registros longitudinais, avaliações clínicas e intervenções para gerar inteligência clínica longitudinal.

Produz:

* Score
* Tendência
* Risco
* Alertas
* Resumo Clínico
* Momento Clínico
* Protocolos sugeridos

---

## 4. Camada Assistencial

Consumidores da inteligência clínica:

* Dashboard
* Timeline
* Prontuário
* Plano Terapêutico Singular (PTS)
* Agenda de Cuidados
* Relatórios
* Aplicativo do Responsável

---

# Princípios Arquiteturais

* Backend é a única fonte de verdade.
* O Frontend não contém lógica clínica.
* Todo protocolo clínico reutiliza a infraestrutura longitudinal.
* Todo resultado clínico deve ser rastreável.
* A arquitetura deve ser modular e extensível.
* Novos instrumentos devem exigir o mínimo possível de alterações estruturais.

---

# Evolução

Esta arquitetura será evoluída continuamente por meio de Architecture Decision Records (ADR), mantendo rastreabilidade das decisões técnicas e garantindo consistência ao longo da evolução da plataforma.
