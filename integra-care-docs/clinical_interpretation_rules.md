# Clinical Interpretation Rules
Version: 1.0

## Objetivo

Produzir uma interpretação clínica estruturada a partir da combinação das evidências coletadas pelos Providers do Report Engine.

Este Engine não descreve fatos.

Ele interpreta o significado clínico dos fatos disponíveis.

---

# Fontes de Conhecimento

PatientProvider

DiagnosisProvider

PTSProvider

AssessmentProvider

TimelineProvider

SessionProvider

ClinicalEngineProvider

---

# Princípios

- Nunca inventar informações.

- Toda interpretação deve ser suportada por evidências objetivas.

- O Engine interpreta.

- A IA poderá posteriormente reescrever a linguagem, mas nunca alterar a interpretação produzida.

---

# Regra CI-001
Continuidade Assistencial

Se existir:

- PTS ativo

- Sessões planejadas

- Eventos longitudinais

Produzir:

"O paciente apresenta continuidade assistencial documentada ao longo do período analisado."

---

# Regra CI-002
Consistência das Evidências

Se existir:

- Avaliações clínicas

- Eventos longitudinais

Produzir:

"As evidências clínicas registradas fornecem base consistente para acompanhamento evolutivo."

---

# Regra CI-003
Momento Clínico Estável

Se:

risco = baixo

tendência = estável

Produzir:

"As evidências disponíveis são compatíveis com manutenção da estratégia assistencial atualmente adotada."

---

# Regra CI-004
Necessidade de Intensificação

Se:

risco = alto

ou

tendência = piora

Produzir:

"As evidências sugerem necessidade de reavaliação clínica e intensificação do acompanhamento."

---

# Regra CI-005
Insuficiência de Evidências

Se não houver informações suficientes.

Produzir:

"As evidências disponíveis ainda são insuficientes para uma interpretação clínica consistente."

---

# Ordem de Construção

1. Continuidade Assistencial

2. Consistência das Evidências

3. Interpretação do Momento Clínico

4. Conclusão Clínica