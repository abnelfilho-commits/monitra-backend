# Regras de Negócio do Integra Care

> **Versão:** 1.0.0\
> **Data:** 03/07/2026\
> **Empresa:** Meyio DDS Digital\
> **Documento:** 09_REGRAS_NEGOCIO.md\
> **Status:** Oficial

------------------------------------------------------------------------

# 1. Objetivo

Este documento reúne as regras de negócio que orientam o funcionamento
do Integra Care.

Mais do que definir comportamentos do sistema, ele registra a lógica
assistencial que fundamenta a plataforma e orienta sua evolução.

Todas as novas funcionalidades deverão respeitar os princípios aqui
estabelecidos.

# 2. Princípios Fundamentais

-   Cuidado centrado no paciente
-   Continuidade da assistência
-   Registro longitudinal
-   Planejamento antes da execução
-   Tomada de decisão baseada em dados
-   Integração entre assistência, operação e gestão
-   Reutilização do núcleo assistencial

# 3. Registro Longitudinal

## RN-001

Todo evento clínico relevante deve compor o histórico longitudinal do
paciente.

Incluem-se:

-   Registros diários
-   Avaliações
-   Intervenções
-   Protocolos
-   PTS
-   Evolução clínica
-   Indicadores

## RN-002

O histórico longitudinal deve preservar a sequência temporal dos
acontecimentos.

Eventos anteriores não devem ser alterados, garantindo rastreabilidade e
integridade das informações.

# 4. Plano Terapêutico Singular (PTS)

## RN-010

Todo planejamento assistencial deve iniciar por um PTS.

## RN-011

Cada paciente poderá possuir apenas um PTS ativo por linha de cuidado.

## RN-012

O PTS organiza:

-   Objetivos
-   Prioridades
-   Atividades
-   Profissionais
-   Cronograma

## RN-013

Todo PTS poderá ser encerrado, mantendo seu histórico disponível.

# 5. Agenda de Cuidados

## RN-020

Toda atividade planejada deverá estar vinculada a um objetivo do PTS.

## RN-021

Cada atividade poderá possuir:

-   Frequência
-   Duração
-   Profissional responsável
-   Período de execução

## RN-022

A Agenda representa o planejamento operacional da assistência.

# 6. Registro Diário

## RN-030

O Registro Diário representa a percepção cotidiana do paciente ou
responsável.

## RN-031

Cada linha de cuidado poderá possuir formulários específicos.

## RN-032

Os registros alimentam automaticamente:

-   Timeline
-   Analytics
-   Indicadores
-   Dashboards

# 7. Avaliações

## RN-040

Avaliações permanecem vinculadas ao paciente e à linha de cuidado.

## RN-041

Os resultados devem permanecer disponíveis para comparação longitudinal.

# 8. Intervenções

## RN-050

Toda intervenção deve possuir:

-   Data
-   Profissional
-   Descrição
-   Paciente
-   Linha de cuidado

## RN-051

Intervenções integram o histórico longitudinal.

# 9. Timeline

## RN-060

A Timeline representa a consolidação cronológica da jornada
assistencial.

Integra:

-   Registros
-   Avaliações
-   Intervenções
-   Protocolos
-   PTS

## RN-061

A Timeline constitui a principal fonte de consulta da evolução clínica.

# 10. Planejamento Financeiro Assistencial

## RN-070

Todo planejamento financeiro deriva da assistência planejada.

Nunca o contrário.

Fluxo:

``` text
PTS
 ↓
Agenda
 ↓
Procedimentos
 ↓
Plano
 ↓
Tabela
 ↓
Custos
 ↓
Receitas
 ↓
Resultado Financeiro
```

## RN-071

O sistema deverá permitir projeções financeiras futuras baseadas na
assistência planejada.

# 11. Dimensionamento Inteligente

## RN-080

O dimensionamento será calculado automaticamente a partir da Agenda de
Cuidados.

## RN-081

O sistema deverá estimar:

-   Horas necessárias
-   Profissionais
-   Ocupações
-   Carga semanal
-   Capacidade instalada

# 12. Linhas de Cuidado

## RN-090

Todas as linhas de cuidado compartilham o mesmo núcleo tecnológico.

## RN-091

Cada linha implementa apenas suas regras clínicas específicas.

## RN-092

Novas linhas poderão ser adicionadas sem alteração da arquitetura
central.

# 13. Linha de Cuidado Oncológica (Roadmap)

## RN-100

Seguirá os mesmos princípios estruturantes da plataforma.

Premissas iniciais:

-   Jornada longitudinal
-   Protocolos terapêuticos
-   Controle de medicamentos de alto custo
-   Rastreabilidade
-   Controle de adesão
-   Indicadores assistenciais
-   Indicadores financeiros

**Observação:** As regras detalhadas serão definidas após validação
funcional com Rudinei, Dra. Jordânia e MT Saúde.

# 14. Indicadores

## RN-110

Todos os indicadores devem ser derivados de dados assistenciais.

## RN-111

Não serão permitidos indicadores alimentados manualmente quando puderem
ser calculados automaticamente.

# 15. Segurança

## RN-120

Toda operação deverá respeitar o perfil do usuário.

## RN-121

A plataforma utiliza autenticação JWT.

## RN-122

Todas as operações deverão ser registradas para garantir
rastreabilidade.

# 16. Evolução da Plataforma

## RN-130

Toda nova funcionalidade deverá:

-   Possuir planejamento funcional
-   Ser validada pelos especialistas
-   Respeitar a arquitetura oficial
-   Possuir documentação oficial
-   Seguir o fluxo DEV → HML → Produção

# 17. Governança

Toda alteração relevante nas regras de negócio deverá:

-   Ser registrada neste documento
-   Receber identificador RN
-   Possuir histórico de revisão
-   Preservar compatibilidade arquitetural

# 18. Considerações Finais

As regras de negócio do Integra Care representam a formalização do
conhecimento assistencial acumulado durante a evolução da plataforma.

Elas orientam o desenvolvimento de novas funcionalidades, garantem
consistência entre as diferentes linhas de cuidado e preservam a
identidade da plataforma como um sistema de gestão longitudinal da
assistência.

------------------------------------------------------------------------

## Princípio de Governança

**Nenhuma funcionalidade será implementada sem antes passar pelo
ciclo:**

Planejamento Funcional → Validação com Especialistas → Desenvolvimento →
Documentação → Implantação

------------------------------------------------------------------------

**© Meyio DDS Digital**

**Integra Care --- Plataforma Modular de Gestão Longitudinal de Linhas
de Cuidado**
