# Changelog do Integra Care

Todas as mudanças relevantes do **Integra Care Health Platform** serão
documentadas neste arquivo.

Este documento é baseado nos princípios do **Keep a Changelog** e utiliza
**Versionamento Semântico**.

---

## [Unreleased]

### Added

#### Jornada Assistencial

- Cockpit Assistencial do Profissional, consolidando informações relevantes
  para acompanhamento da operação assistencial.
- Cards de resumo com pacientes, sessões do dia, atendimentos realizados
  e pendências.
- Ações rápidas para acesso aos principais fluxos assistenciais.
- Priorização de pacientes no Cockpit Assistencial.
- Visualização de atividades recentes e evolução clínica.
- Sessões Assistenciais geradas a partir do planejamento da Agenda de Cuidados.
- Visualização das sessões programadas por paciente.
- Registro de Atendimento vinculado à Sessão Assistencial.
- Registro longitudinal do atendimento realizado.
- Campo de narrativa do atendimento.
- Registro estruturado de próximos passos.
- Navegação entre Agenda de Cuidados, Sessões Assistenciais e Registro
  de Atendimento.
- Consolidação da relação entre cuidado planejado e cuidado realizado.

#### Cockpit de Gestão

- Implementação do Cockpit de Gestão para os perfis ADMIN e ADMIN_CLINICA.
- Visão Executiva com Pessoas Acompanhadas, Acompanhamento Ativo,
  Cobertura Assistencial, Atenção Necessária e Profissionais Ativos.
- Situação da População com separação entre Risco Clínico e
  Continuidade Longitudinal.
- Classificação da Continuidade Longitudinal em REGULAR, ATENÇÃO,
  CRÍTICA e NÃO INICIADA.
- Alerta Crítico de Continuidade para pessoas com 7 dias ou mais sem
  Registro Diário, sem conversão automática em alto risco clínico.
- Priorização gerencial com motivos explícitos e rastreáveis.
- Indicadores de Atividade Assistencial por período.
- Estrutura da Operação por clínica/unidade para o perfil ADMIN.
- Atividade Recente consolidada no Cockpit de Gestão.
- Escopo global para ADMIN e escopo por clínica/unidade para
  ADMIN_CLINICA.

#### Experiência Longitudinal do Paciente

- Evolução da visão 360° do paciente.
- Integração de diagnósticos à jornada longitudinal.
- Integração de Sessões Assistenciais à Timeline Clínica.
- Integração do Registro de Atendimento à jornada longitudinal.
- Evolução da Timeline Clínica com consolidação de diferentes tipos de
  acontecimentos assistenciais.
- Evolução da visualização do Registro Diário.
- Evolução da visualização das avaliações clínicas.
- Aprimoramento da experiência de acompanhamento do PTS, objetivos,
  planejamento e Agenda de Cuidados.
- Evolução da experiência de acompanhamento longitudinal das linhas
  Neurodesenvolvimento e Cardiometabólica.

#### Avaliações Clínicas

- Evolução da experiência de aplicação e acompanhamento do M-CHAT.
- Evolução da experiência de aplicação e acompanhamento do Denver II.
- Indicador de progresso das avaliações.
- Integração das avaliações à experiência longitudinal do paciente.

#### Registro Diário

- Evolução do Registro Diário realizado pelo Profissional.
- Evolução do Registro Diário realizado pelo Responsável.
- Padronização da referência temporal entre registros de “Hoje” e “Ontem”.
- Aprimoramento das regras de Saúde Intestinal.
- Tratamento condicional da consistência das fezes quando não há evacuação.
- Evolução das regras de irritabilidade, crise sensorial e seletividade
  alimentar.
- Padronização da escala de seletividade alimentar:
  `NENHUMA`, `LEVE`, `MODERADA` e `GRAVE`.

#### Integração WhatsApp

- Integração do WhatsApp Business ao Registro Diário do Responsável.
- Fluxo conversacional estruturado para coleta das informações do
  Registro Diário.
- Persistência das respostas do WhatsApp na arquitetura longitudinal
  do Integra Care.
- Suporte à referência temporal de “Hoje” e “Ontem” no fluxo conversacional.
- Configuração de webhook para recebimento das mensagens.
- Configuração de token definitivo da integração WhatsApp Business.
- Validação do fluxo de Registro Diário pelo WhatsApp em ambiente produtivo.

#### Clinical Engine Neuro

- Evolução do motor de inteligência clínica da Linha de Cuidado
  Neurodesenvolvimento.
- Classificação automatizada de risco clínico.
- Análise de tendência longitudinal.
- Definição automatizada de prioridade assistencial.
- Definição de protocolo assistencial.
- Identificação de eixo clínico dominante.
- Geração de interpretação clínica automatizada.
- Classificação do Momento Clínico do paciente.
- Painel Clínico Inteligente.
- Resumo Clínico Automático.
- Diferenciação conceitual entre estado clínico atual, recorrência,
  tendência e histórico longitudinal.
- Interpretação do sono a partir da janela longitudinal recente.
- Interpretação da irritabilidade com base no estado clínico mais recente.
- Interpretação da crise sensorial com base no estado clínico mais recente.
- Tratamento de valor `0` como ausência do sintoma, e não como ausência
  de dados, quando existe base clínica.
- Diferenciação entre ausência de evacuação e alteração da consistência
  das fezes na interpretação de Saúde Intestinal.
- Análise alimentar considerando registros atuais e histórico recente.
- Identificação automática de melhora dos parâmetros alimentares em
  relação ao histórico.
- Preservação do histórico clínico nos gráficos de evolução mesmo quando
  o estado atual apresenta melhora.

#### Report Engine

- Criação do Framework Inteligente de Relatórios do Integra Care.
- Arquitetura reutilizável para geração automática de conhecimento clínico.
- Pipeline de geração de relatórios baseado em coleta de dados,
  indicadores, evidências, interpretação, narrativa, representação
  canônica e renderização.
- Registry de relatórios.
- Estrutura de Providers para composição do contexto dos relatórios.
- Canonical Report como representação intermediária dos relatórios.
- Estrutura de Renderers.
- Renderer PDF.
- Integração do Report Engine com informações longitudinais do paciente.

#### Relatório Longitudinal Inteligente — CLN-001

- Implementação do primeiro relatório clínico canônico do Report Engine.
- Criação do relatório `clinical-longitudinal-report`.
- Identificação do paciente e contexto assistencial.
- Resumo executivo.
- Situação clínica atual.
- Narrativa longitudinal.
- Integração de informações do PTS.
- Integração de diagnósticos.
- Integração de eventos assistenciais.
- Integração de Sessões Assistenciais.
- Integração com a inteligência clínica.
- Geração do relatório em PDF.
- Disponibilização do download pelo Portal Profissional.

#### Planejamento e Gestão Assistencial

- Evolução do Dimensionamento Inteligente.
- Evolução do Planejamento Financeiro Assistencial.
- Aprimoramento da relação entre demanda assistencial, capacidade
  instalada e dimensionamento de equipe.

#### Implantação e Cases

- Preparação da plataforma para operação dos primeiros cases.
- Preparação e documentação do Case Mirassol d’Oeste.
- Evolução da estratégia de implantação das linhas de cuidado.
- Planejamento da futura Linha de Cuidado Oncológica.

#### Documentação e Estratégia

- Conclusão da Biblioteca Oficial de documentação do Integra Care.
- Evolução da documentação institucional e estratégica.
- Desenvolvimento do Integra Care Growth Blueprint.
- Definição da necessidade do Integra Care Engineering Playbook.
- Início da revisão documental pós-1.0.
- Início da revisão do Manual do Usuário — Profissional.

---

### Changed

#### Arquitetura e Escalabilidade dos Cockpits

- Substituição do padrão de múltiplas requisições por paciente por
  contratos agregados de Cockpit no backend.
- Implementação dos endpoints agregados `GET /cockpit/profissional`
  e `GET /cockpit/gestao`.
- Centralização da composição dos indicadores no backend.
- Eliminação do fan-out de risco e eventos longitudinais por paciente
  no carregamento inicial dos Cockpits.
- Preservação do Clinical Engine como fonte oficial da inteligência
  clínica.
- Introdução do contrato canônico `cockpit_v2` no Cockpit de Gestão,
  mantendo temporariamente compatibilidade aditiva com o contrato
  anterior.
- Transformação do antigo Dashboard Neurodesenvolvimento dos perfis
  administrativos em Cockpit de Gestão populacional e operacional.

#### Arquitetura Assistencial

- Evolução do Integra Care de uma plataforma longitudinal funcional para
  uma arquitetura assistencial integrada.
- Consolidação da jornada:

  `Diagnóstico → Avaliações → PTS → Planejamento → Sessões →
  Registro Diário + Intervenções → Timeline → Evolução → Relatório`

- Consolidação da distinção entre cuidado planejado e cuidado realizado.
- Ampliação da arquitetura longitudinal para incorporar Sessões Assistenciais
  e Registros de Atendimento.
- Evolução da plataforma para captura longitudinal por múltiplos canais.

#### Clinical Engine

- Refinamento da semântica dos indicadores clínicos do módulo Neuro.
- Irritabilidade e crise sensorial deixaram de ser interpretadas apenas
  como médias históricas e passaram a representar adequadamente o
  estado clínico mais recente no Painel Clínico Inteligente.
- Manutenção do histórico longitudinal nos gráficos independentemente
  do estado atual.
- Refinamento da análise de alimentação para distinguir situação atual
  de ocorrências históricas.
- Refinamento da interpretação intestinal para identificar a natureza
  da alteração observada.
- Evolução das narrativas automáticas para reduzir interpretações
  incompatíveis com o estado clínico atual.

#### Registro Diário

- Padronização das escalas utilizadas pelo Portal Profissional,
  APP do Responsável, WhatsApp e Clinical Engine.
- Padronização da seletividade alimentar de valores legados
  `NAO/INTENSA` para `NENHUMA/GRAVE`.
- Refinamento do comportamento dos campos dependentes de evacuação.
- Evolução da experiência do Registro Diário no APP do Responsável.

#### Experiência do Profissional

- Evolução da página do paciente para concentrar Status Clínico,
  Resumo Clínico Automático, Painel Clínico Inteligente, Timeline
  e Evolução Clínica.
- Aprimoramento da navegação entre os componentes da jornada assistencial.
- Evolução da experiência de confirmação e acompanhamento da Agenda
  de Cuidados.
- Evolução da experiência de download do Relatório Longitudinal Inteligente.

#### Infraestrutura e Deploy

- Evolução contínua do fluxo oficial `DEV → HML → Validação → PROD`.
- Sincronização das alterações validadas entre branches de homologação
  e produção.
- Atualização das configurações CORS para os domínios oficiais do
  Integra Care.
- Atualização da identificação da API de homologação para Integra Care API.
- Preparação da infraestrutura produtiva para os primeiros cases.
- Padronizada a identidade institucional do Portal Profissional com
  título, descrição, idioma e favicons oficiais do Integra Care.

---

### Fixed

#### Clinical Engine Neuro

- Corrigida a interpretação de valor `0` em irritabilidade e crise sensorial,
  que poderia ser apresentado como “Sem dados” apesar da existência de
  registro clínico.
- Corrigida a escala narrativa de irritabilidade para manter coerência
  com os valores estruturados do Registro Diário.
- Corrigida a escala narrativa de crise sensorial para manter coerência
  com os valores estruturados.
- Corrigida a interpretação de seletividade alimentar para utilizar
  `NENHUMA` e `GRAVE`.
- Corrigida a permanência indevida de alertas alimentares provocados por
  registros históricos quando os registros atuais indicavam melhora.
- Corrigida a interpretação genérica de alterações intestinais para
  distinguir ausência de evacuação de alteração recorrente da
  consistência das fezes.
- Corrigida a leitura de campos booleanos opcionais na consulta dos
  registros Neuro, evitando converter ausência de resposta em `false`.

#### Portal Profissional

- Corrigida a apresentação dos estados de irritabilidade e crise sensorial
  no Painel Clínico Inteligente.
- Corrigidas cores dos indicadores clínicos para distinguir ausência
  de sintoma de ausência de dados.
- Refinados os textos auxiliares dos indicadores clínicos.
- Ajustada a apresentação da Base Clínica utilizada pelo painel.
- Ajustada a experiência de navegação em Agenda, Sessões e Registro
  de Atendimento.
- Corrigidos fluxos de confirmação da Agenda de Cuidados.

- Corrigida a navegação das prioridades do Cockpit Assistencial para
  utilizar corretamente `paciente_id`.

#### APP do Responsável

- Corrigido o comportamento da consistência das fezes quando não houve
  evacuação.
- Refinada a experiência de preenchimento do Registro Diário.
- Corrigida a interpretação temporal dos registros de “Hoje” e “Ontem”.

#### WhatsApp

- Corrigido o fluxo de autenticação do webhook.
- Corrigidos comportamentos do fluxo conversacional do Registro Diário.
- Corrigida a interpretação de referência temporal no registro realizado
  pelo WhatsApp.

---

### Technical

- Evolução dos serviços responsáveis pelo Clinical Engine Neuro.
- Evolução das regras clínicas em `neuro_clinical_rules`.
- Consolidação de `registros_longitudinais` e `respostas_registro`
  como base da leitura clínica longitudinal.
- Ampliação da arquitetura de serviços para Sessões Assistenciais.
- Inclusão do tipo longitudinal `ATENDIMENTO_SESSAO`.
- Implementação da arquitetura do Report Engine.
- Implementação do `ReportService`.
- Implementação do `CanonicalReport`.
- Implementação da estrutura de Renderers.
- Implementação do PDF canônico.
- Integração progressiva entre Clinical Engine e Report Engine.
- Evolução das consultas longitudinais para preservar corretamente
  valores numéricos, textuais e booleanos.
- Validação de builds do Portal Profissional antes das promoções entre
  ambientes.
- Validação sintática dos serviços Python antes das promoções.
- Manutenção do fluxo de branches `homolog → main` para publicação
  das versões validadas.

---

### Validation

- Fluxos principais do Profissional validados em HML.
- M-CHAT e Denver II validados após evolução da experiência de progresso.
- Sessões Assistenciais e Registro de Atendimento validados.
- Registro Diário do APP do Responsável validado.
- Registro Diário via WhatsApp validado.
- Token definitivo do WhatsApp Business validado.
- Backend promovido e validado em PROD.
- Portal Profissional promovido e validado em PROD.
- Clinical Engine Neuro refinado e validado em PROD.
- Painel Clínico Inteligente validado em PROD com dados longitudinais reais.
- Validação da preservação do histórico de evolução clínica após
  refinamento da leitura do estado atual.

---

## [1.0.0] — 03/07/2026

### Added

- Portal Profissional
- APP do Responsável
- Linha de Cuidado Neurodesenvolvimento
- Linha de Cuidado Cardiometabólico
- Arquitetura multi-clínica
- Arquitetura multi-módulo
- Registro Longitudinal
- Timeline consolidada
- Intervenções
- Framework de Avaliações
- Protocolo M-CHAT
- Método Denver
- Plano Terapêutico Singular (PTS)
- Objetivos terapêuticos
- Atividades terapêuticas
- Ocupações profissionais
- Agenda de Cuidados
- Dimensionamento de Equipe
- Dashboards assistenciais
- Analytics
- Perfis `ADMIN`, `ADMIN_CLINICA`, `PROFISSIONAL` e `RESPONSAVEL`

### Changed

- Evolução do antigo conceito Monitra para **Integra Care**
- Consolidação do produto como Plataforma Modular de Gestão
  Longitudinal de Linhas de Cuidado
- Padronização dos ambientes DEV, HML e Produção
- Definição do fluxo oficial `DEV → HML → Validação → Produção`
- Adoção dos novos domínios institucionais
- Separação definitiva entre Portal Profissional e APP do Responsável

### Fixed

- Persistência e exibição dos registros longitudinais
- Isolamento de dados por linha de cuidado
- Timeline Neuro e Cardiometabólico
- Cálculos e indicadores Cardiometabólicos
- Navegação conforme perfil do usuário
- Fluxo do APP do Responsável
- Sincronização estrutural entre HML e Produção

### Security

- Autenticação JWT
- Controle de acesso por perfis
- Isolamento multi-clínica
- Permissões por módulo
- HTTPS nos domínios oficiais
- Desativação de acessos não autorizados
- Remoção dos domínios antigos da operação

### Infrastructure

- Backend hospedado na Render
- Portal Profissional hospedado na Vercel
- APP do Responsável hospedado na Vercel
- Banco de dados PostgreSQL
- Containers Docker
- Migrações com Alembic
- Ambientes DEV, HML e Produção
- Primeiro merge oficial de Homologação para Produção
- Backups completos de Produção e Homologação
- Domínio oficial do Portal: `https://care.meyio.com.br`
- Domínio oficial do APP: `https://app.care.meyio.com.br`
- Domínio oficial da API: `https://api.care.meyio.com.br`

### Documentation

- `00_HOME.md`
- `01_VISAO_GERAL.md`
- `02_ARQUITETURA.md`
- `05_ADMINISTRADOR.md`
- `06_PROFISSIONAL.md`
- `07_RESPONSAVEL_APP.md`
- `08_GUIA_IMPLANTACAO.md`
- `09_REGRAS_NEGOCIO.md`
- `13_RELEASES.md`
- `14_PLANO_DIRETOR.md`

---

# Regra de Manutenção

Toda alteração relevante deverá ser registrada inicialmente na seção:

[Unreleased]

No momento da publicação de uma nova versão, as alterações deverão ser
movidas para uma seção identificada pela versão e pela data:

[Unreleased]
      ↓
[nova versão] — data

O `CHANGELOG.md` integra o processo oficial de evolução e publicação do
Integra Care.

Fluxo de release:

**Desenvolvimento → HML → Validação → Documentação → Produção →
Registro da Release**

---

**Integra Care Health Platform**