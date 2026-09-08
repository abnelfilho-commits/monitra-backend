Regras de Negócio do Integra Care

Versão: 1.1.0
Data: 24/08/2026
Empresa: Integra Care Health Platform
Documento: 09_REGRAS_NEGOCIO.md
Status: Oficial

1. Objetivo

Este documento reúne as regras de negócio que orientam o funcionamento do Integra Care Health Platform.

Mais do que definir comportamentos do sistema, ele formaliza a lógica assistencial, operacional e de inteligência que fundamenta a plataforma e orienta sua evolução.

As regras aqui descritas constituem referência para:

planejamento funcional;
desenvolvimento;
validação;
homologação;
implantação;
documentação;
evolução das linhas de cuidado;
construção dos mecanismos de inteligência assistencial.

Toda nova funcionalidade deverá respeitar os princípios e regras estabelecidos neste documento.

2. Princípios Fundamentais

O Integra Care adota como princípios:

cuidado centrado no paciente;
continuidade da assistência;
longitudinalidade;
planejamento antes da execução;
separação entre planejado e realizado;
tomada de decisão baseada em dados;
integração entre assistência, operação e gestão;
reutilização do núcleo assistencial;
rastreabilidade;
interpretação contextual dos dados;
preservação do histórico;
inteligência como apoio à decisão;
modularidade por linhas de cuidado.

A plataforma deve preservar uma distinção fundamental:

Um dado isolado representa um momento. A longitudinalidade representa uma trajetória.

3. Registro Longitudinal
RN-001

Todo evento assistencial ou clínico relevante deverá poder compor o histórico longitudinal do paciente.

Incluem-se, conforme aplicável:

registros diários;
avaliações;
diagnósticos;
intervenções;
PTS;
objetivos terapêuticos;
agenda de cuidados;
sessões assistenciais;
registros de atendimento;
protocolos;
evolução clínica;
indicadores;
relatórios clínicos.
RN-002

O histórico longitudinal deverá preservar a sequência temporal dos acontecimentos.

Eventos anteriores não deverão ser sobrescritos por informações posteriores quando isso comprometer a rastreabilidade ou a compreensão histórica da jornada.

RN-003

As diferentes fontes de informação deverão convergir para um núcleo longitudinal comum, evitando a existência de históricos clínicos paralelos para o mesmo paciente.

RN-004

A origem do dado deverá ser preservada sempre que necessária à interpretação e à rastreabilidade.

O dado poderá ter origem, entre outras possibilidades, no:

profissional;
responsável;
paciente;
sistema;
integração;
canal conversacional autorizado.
4. Plano Terapêutico Singular — PTS
RN-010

O PTS representa o planejamento assistencial estruturado do paciente.

RN-011

Cada paciente poderá possuir apenas um PTS ativo por linha de cuidado, salvo quando uma regra específica da linha determinar comportamento diferente.

RN-012

O PTS poderá organizar:

objetivos;
prioridades;
atividades;
profissionais;
cronograma;
estratégias assistenciais.
RN-013

Todo PTS poderá ser encerrado, preservando seu histórico.

RN-014

O encerramento de um PTS não deverá apagar objetivos, atividades, registros ou evidências produzidas durante sua vigência.

RN-015

Objetivos encerrados deverão permanecer disponíveis para consulta longitudinal.

5. Agenda de Cuidados
RN-020

Toda atividade assistencial planejada deverá, quando aplicável, estar vinculada a um objetivo do PTS.

RN-021

Cada atividade poderá possuir:

frequência;
duração;
ocupação profissional;
profissional responsável;
período de execução;
situação.
RN-022

A Agenda de Cuidados representa o planejamento operacional da assistência.

RN-023

Planejamento assistencial e execução assistencial são conceitos distintos.

Agenda representa o que deveria acontecer. Sessão representa o que efetivamente acontece.

RN-024

A Agenda de Cuidados poderá ser utilizada como fonte para cálculo de demanda assistencial, dimensionamento de equipe e projeções operacionais.

6. Registro Diário
RN-030

O Registro Diário representa a observação estruturada de aspectos relevantes da vida cotidiana e da condição clínica do paciente entre os diferentes momentos formais da assistência.

RN-031

Cada linha de cuidado poderá possuir formulário próprio e regras específicas de interpretação.

RN-032

Os registros poderão alimentar automaticamente:

Timeline;
Painel Clínico;
Clinical Engine;
Analytics;
indicadores;
dashboards;
evolução clínica;
relatórios.
RN-033

O Registro Diário poderá ser realizado por diferentes canais autorizados, desde que todos persistam informações compatíveis com o núcleo longitudinal.

Entre os canais previstos estão:

Portal Profissional;
APP do Responsável;
interfaces conversacionais integradas, como WhatsApp;
futuras integrações autorizadas.
RN-034

A interface utilizada para coleta não deverá alterar o significado clínico do dado.

Múltiplos canais de entrada. Uma única verdade longitudinal.

RN-035

Campos não respondidos deverão ser tratados como ausência de informação, e não automaticamente como resposta negativa.

RN-036

Valores booleanos deverão preservar semanticamente a distinção entre:

true;
false;
ausência de resposta.
RN-037

Campos dependentes deverão respeitar a lógica clínica do campo principal.

Exemplo: quando não houver evacuação, a consistência das fezes não deverá ser interpretada como se uma evacuação tivesse ocorrido.

7. Avaliações
RN-040

Avaliações deverão permanecer vinculadas ao paciente e à respectiva linha de cuidado.

RN-041

Os resultados deverão permanecer disponíveis para comparação longitudinal.

RN-042

Instrumentos estruturados deverão preservar:

respostas;
resultado;
interpretação;
data de aplicação;
contexto necessário à compreensão do resultado.
RN-043

O progresso de preenchimento de uma avaliação deverá representar seu estado real de execução.

RN-044

Instrumentos como M-CHAT e Denver deverão manter suas regras específicas independentes da infraestrutura genérica de avaliações.

8. Intervenções
RN-050

Toda intervenção deverá possuir informações suficientes para identificar:

data;
profissional;
descrição;
paciente;
linha de cuidado.
RN-051

Intervenções integram o histórico longitudinal.

RN-052

Intervenções deverão permanecer disponíveis para análise em conjunto com registros diários, avaliações, sessões e demais eventos assistenciais.

9. Timeline Clínica
RN-060

A Timeline Clínica representa a consolidação cronológica da jornada assistencial.

RN-061

A Timeline constitui uma das principais fontes de consulta da evolução clínica do paciente.

RN-062

A Timeline poderá integrar, conforme disponibilidade e relevância:

Registro Diário;
avaliações;
intervenções;
sessões assistenciais;
registros de atendimento;
diagnósticos;
PTS;
outros eventos longitudinalmente relevantes.
RN-063

Eventos provenientes de diferentes funcionalidades deverão ser apresentados de maneira temporalmente coerente.

RN-064

A Timeline não deverá criar uma nova cópia da verdade clínica.

Ela deverá consolidar informações provenientes das respectivas fontes oficiais.

10. Planejamento Financeiro Assistencial
RN-070

Todo planejamento financeiro assistencial deverá derivar da assistência planejada.

Nunca o contrário.

Fluxo conceitual:

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
RN-071

O sistema poderá permitir projeções financeiras futuras baseadas na assistência planejada.

11. Dimensionamento Inteligente
RN-080

O dimensionamento assistencial deverá ser calculado a partir da demanda planejada na Agenda de Cuidados.

RN-081

O sistema poderá estimar:

horas necessárias;
profissionais;
ocupações;
carga semanal;
demanda assistencial;
capacidade instalada;
relação entre demanda e capacidade.
RN-082

O dimensionamento deverá distinguir necessidade assistencial de capacidade disponível.

RN-083

Sempre que possível, indicadores de dimensionamento deverão ser calculados automaticamente a partir dos dados estruturados da plataforma.

12. Linhas de Cuidado
RN-090

Todas as linhas de cuidado compartilham o mesmo núcleo tecnológico e longitudinal.

RN-091

Cada linha deverá implementar apenas as regras clínicas específicas necessárias ao seu contexto assistencial.

RN-092

Novas linhas poderão ser incorporadas sem reconstrução do núcleo arquitetural central.

RN-093

Regras específicas de uma linha de cuidado não deverão ser automaticamente aplicadas a outra.

RN-094

A identidade do paciente deverá permanecer única mesmo quando ele participar de múltiplas linhas de cuidado.

13. Linha de Cuidado Oncológica — Roadmap
RN-100

A futura Linha de Cuidado Oncológica deverá seguir os mesmos princípios estruturantes da plataforma.

Premissas atualmente previstas:

jornada longitudinal;
protocolos terapêuticos;
controle de medicamentos de alto custo;
rastreabilidade;
controle de adesão;
indicadores assistenciais;
indicadores financeiros.

Status: Em planejamento.

As regras detalhadas somente deverão ser incorporadas a este documento após validação funcional pelos especialistas e responsáveis de negócio.

14. Indicadores
RN-110

Todos os indicadores deverão ser derivados, sempre que possível, dos dados estruturados da operação e da assistência.

RN-111

Não deverão existir indicadores alimentados manualmente quando puderem ser calculados automaticamente a partir das fontes oficiais da plataforma.

RN-112

Indicadores deverão preservar rastreabilidade até os dados que lhes deram origem sempre que tecnicamente e funcionalmente aplicável.

RN-113

Um indicador não deverá ser apresentado como fato clínico quando representar inferência, classificação ou interpretação calculada.

15. Segurança e Controle de Acesso
RN-120

Toda operação deverá respeitar o perfil e o contexto de acesso do usuário.

RN-121

A plataforma utiliza autenticação baseada em JWT.

RN-122

Operações relevantes deverão preservar rastreabilidade.

RN-123

O acesso às informações deverá respeitar os vínculos organizacionais, assistenciais e funcionais aplicáveis.

RN-124

A arquitetura deverá preservar separação entre autenticação, autorização e regra de negócio.

16. Evolução da Plataforma
RN-130

Toda nova funcionalidade deverá:

possuir planejamento funcional;
ser validada quando envolver regra assistencial ou de negócio relevante;
respeitar a arquitetura oficial;
possuir documentação compatível com sua relevância;
seguir o fluxo oficial de evolução e publicação.

Fluxo de referência:

Planejamento
     ↓
Desenvolvimento
     ↓
DEV
     ↓
HML
     ↓
Validação
     ↓
PROD
     ↓
Documentação / Release
17. Sessões Assistenciais
RN-140

Sessão Assistencial representa uma ocorrência concreta da assistência, derivada ou não de um planejamento prévio.

RN-141

Quando originada da Agenda de Cuidados, a sessão deverá preservar sua relação com o planejamento que lhe deu origem.

RN-142

Uma sessão poderá possuir estados de execução compatíveis com seu ciclo de vida.

RN-143

O sistema deverá distinguir claramente:

Planejado → Agendado → Realizado

quando esses estados forem aplicáveis ao fluxo assistencial.

RN-144

O histórico das sessões deverá permanecer associado ao paciente e disponível para acompanhamento longitudinal.

RN-145

A existência de uma atividade planejada não deverá ser interpretada automaticamente como atendimento realizado.

18. Registro de Atendimento
RN-150

O Registro de Atendimento documenta clinicamente o que ocorreu durante uma sessão assistencial.

RN-151

O registro deverá estar associado ao paciente e, quando aplicável, à sessão correspondente.

RN-152

O Registro de Atendimento deverá permitir narrativa profissional suficiente para representar o atendimento realizado.

RN-153

Próximos passos poderão ser registrados de forma estruturada para apoiar continuidade assistencial.

RN-154

Registros de Atendimento deverão integrar a visão longitudinal do paciente.

RN-155

Planejamento, sessão e registro de atendimento representam entidades conceitualmente distintas.

PLANEJAMENTO
      ↓
   SESSÃO
      ↓
ATENDIMENTO
      ↓
HISTÓRICO LONGITUDINAL
19. Inteligência Clínica
RN-160

O Clinical Engine transforma dados longitudinais estruturados em indicadores e interpretações de apoio à decisão.

RN-161

A inteligência clínica poderá considerar, conforme a linha de cuidado:

score;
risco;
tendência;
prioridade;
protocolos;
eixo clínico predominante;
momento clínico;
padrões longitudinais;
sinais relevantes.
RN-162

Nenhum indicador isolado deverá ser considerado sinônimo do estado clínico global do paciente.

RN-163

A interpretação clínica deverá distinguir explicitamente quatro dimensões:

Estado Atual ≠ Recorrência ≠ Tendência ≠ Histórico

Estado Atual

Representa a condição observada no registro ou conjunto de registros mais recentes definido pela regra.

Recorrência

Representa repetição de determinado sinal dentro de uma janela longitudinal.

Tendência

Representa a direção de mudança observada ao longo do tempo.

Histórico

Representa acontecimentos anteriores que permanecem clinicamente relevantes para contextualização, sem necessariamente caracterizar o estado atual.

RN-164

Melhora recente não deverá ser anulada automaticamente pela existência de alterações históricas.

RN-165

Da mesma forma, um registro recente satisfatório não deverá apagar a existência de um padrão histórico relevante.

RN-166

As janelas temporais utilizadas por cada indicador deverão ser coerentes com a natureza do fenômeno analisado.

20. Momento Clínico
RN-170

O Momento Clínico representa uma interpretação sintética da condição assistencial atual do paciente.

RN-171

O Momento Clínico deverá priorizar informações atuais e recentes, sem confundir eventos históricos com condição presente.

RN-172

A classificação poderá considerar conjuntamente diferentes sinais e indicadores produzidos pelo Clinical Engine.

RN-173

A descrição do Momento Clínico deverá utilizar linguagem compreensível ao profissional e compatível com os dados disponíveis.

RN-174

Ausência de sinal crítico predominante não significa ausência absoluta de histórico clínico relevante.

21. Painel Clínico Inteligente
RN-180

O Painel Clínico deverá apresentar uma síntese interpretativa dos principais eixos acompanhados pela linha de cuidado.

RN-181 — Neurodesenvolvimento

No módulo Neuro, o painel poderá considerar:

sono;
irritabilidade;
crise sensorial;
saúde intestinal;
alimentação;
outros eixos posteriormente validados.
RN-182 — Sono

O indicador de sono poderá utilizar agregação de registros recentes quando o objetivo for representar padrão recente de qualidade do sono.

RN-183 — Irritabilidade

A apresentação da irritabilidade atual deverá refletir prioritariamente o registro mais recente quando o card estiver conceitualmente representando estado atual.

RN-184 — Crise Sensorial

A apresentação de crise sensorial atual deverá refletir prioritariamente o registro mais recente quando o card representar estado atual.

RN-185 — Saúde Intestinal

A análise intestinal deverá distinguir, sempre que possível:

ausência de evacuação;
consistência alterada das fezes;
ausência de informação.
RN-186

Ausência de evacuação recorrente deverá poder ser apresentada explicitamente como tal, evitando mensagens genéricas quando a causa do indicador for conhecida.

RN-187

Alteração recorrente da consistência das fezes deverá poder ser apresentada explicitamente quando esse for o padrão identificado.

RN-188 — Alimentação

A seletividade alimentar deverá utilizar a classificação vigente:

NENHUMA  → 0
LEVE     → 1
MODERADA → 2
GRAVE    → 3
RN-189

A interpretação alimentar deverá distinguir condição recente de histórico alimentar.

Quando os registros mais recentes forem satisfatórios e houver alterações no histórico recente, o sistema poderá reconhecer melhora em relação ao histórico, em vez de manter automaticamente uma classificação negativa.

22. Resumo Clínico Automático
RN-190

O Resumo Clínico deverá transformar os indicadores estruturados do Painel Clínico em narrativa interpretativa.

RN-191

A narrativa deverá refletir os dados efetivamente disponíveis.

RN-192

O sistema deverá preferir descrições específicas quando conhecer a origem de uma alteração.

Exemplo:

"ausência de evacuação em registros recentes"

é preferível a uma descrição excessivamente genérica quando esse for efetivamente o fenômeno identificado.

RN-193

O resumo não deverá afirmar recorrência quando os dados representarem apenas um evento atual.

RN-194

O resumo não deverá afirmar condição atual negativa exclusivamente em razão de registros históricos quando os dados recentes demonstrarem melhora.

RN-195

Quando os registros recentes indicarem estabilidade e melhora de determinado eixo em relação ao histórico, essa evolução poderá ser explicitada na narrativa.

23. Cardiometabólico
RN-200

A Linha Cardiometabólica deverá utilizar o mesmo núcleo longitudinal da plataforma, preservando suas regras clínicas específicas.

RN-201

O Registro Diário Cardiometabólico poderá acompanhar indicadores como:

glicemia;
pressão arterial;
peso;
IMC;
demais parâmetros posteriormente incorporados.
RN-202

O Clinical Engine Cardiometabólico poderá produzir classificações de risco, tendência e protocolos de acompanhamento a partir dos dados disponíveis.

RN-203

A visão individual e a visão populacional deverão derivar das mesmas fontes estruturadas de dados.

RN-204

Regras de interpretação Cardiometabólica deverão permanecer desacopladas das regras específicas do Neurodesenvolvimento.

24. Visão 360° do Paciente
RN-210

A Visão 360° deverá consolidar diferentes dimensões relevantes da jornada assistencial sem substituir suas fontes oficiais.

RN-211

A visão poderá reunir informações provenientes de:

diagnósticos;
registros diários;
avaliações;
PTS;
agenda;
sessões;
atendimentos;
intervenções;
Timeline;
evolução;
indicadores;
relatórios.
RN-212

A Visão 360° deverá facilitar compreensão contextual do paciente sem eliminar a possibilidade de acesso ao dado original.

25. Report Engine
RN-220

O Report Engine constitui o framework responsável pela transformação de dados longitudinais em documentos estruturados de conhecimento.

RN-221

O pipeline conceitual deverá seguir:

COLETA
  ↓
INDICADORES
  ↓
EVIDÊNCIAS
  ↓
INTERPRETAÇÕES
  ↓
NARRATIVA
  ↓
VISUALIZAÇÃO
  ↓
DOCUMENTO
RN-222

Relatórios deverão ser produzidos a partir de fontes oficiais da plataforma.

RN-223

O Report Engine deverá ser modular e reutilizável entre diferentes tipos de relatório.

RN-224

A geração narrativa não deverá alterar o dado clínico original.

RN-225

Sempre que possível, conclusões e interpretações deverão manter relação rastreável com suas evidências de origem.

RN-226

Relatórios poderão possuir públicos, finalidades e estruturas diferentes sem duplicar a lógica central de coleta e interpretação.

26. Relatório Longitudinal Inteligente — CLN-001
RN-230

O Relatório Longitudinal Inteligente deverá consolidar a trajetória assistencial do paciente dentro de um período definido.

RN-231

O relatório poderá integrar informações provenientes de diferentes componentes da jornada longitudinal.

RN-232

Sua estrutura deverá separar dados, evidências, interpretação e narrativa de maneira coerente.

RN-233

O relatório deverá representar a trajetória do paciente, e não apenas uma fotografia isolada do momento atual.

RN-234

A narrativa longitudinal poderá considerar:

PTS;
objetivos;
diagnósticos;
Registro Diário;
avaliações;
Agenda de Cuidados;
sessões;
atendimentos;
intervenções;
Clinical Engine;
evolução temporal.
RN-235

O PDF gerado deverá representar uma materialização do relatório, enquanto a inteligência e os dados que o originaram permanecem independentes da camada de apresentação.

27. Geração de Conhecimento
RN-240

O Integra Care deverá distinguir:

DADO
 ↓
INFORMAÇÃO
 ↓
INDICADOR
 ↓
INTERPRETAÇÃO
 ↓
CONHECIMENTO
 ↓
APOIO À DECISÃO
RN-241

Dados brutos não deverão ser apresentados automaticamente como interpretação clínica.

RN-242

Interpretações produzidas automaticamente deverão ser tratadas como apoio à decisão, não como substituição da avaliação profissional.

RN-243

A plataforma deverá preservar, sempre que possível, a possibilidade de compreender quais informações contribuíram para uma interpretação automática.

RN-244

A inteligência deverá ampliar a capacidade de leitura longitudinal da assistência, sem apagar a origem dos dados.

28. Governança das Regras Clínicas
RN-250

Toda regra clínica automatizada deverá possuir definição explícita e implementação rastreável.

RN-251

Alterações relevantes em thresholds, classificações, janelas temporais ou critérios interpretativos deverão ser tratadas como evolução de regra de negócio.

RN-252

Regras clínicas específicas deverão permanecer associadas à respectiva linha de cuidado.

RN-253

Mudanças em nomenclaturas clínicas deverão ser propagadas de forma coerente entre:

formulários;
backend;
Clinical Engine;
frontend;
relatórios;
documentação.
RN-254

Valores históricos válidos não deverão ser reinterpretados silenciosamente quando houver alteração de nomenclatura ou regra sem que a compatibilidade seja previamente avaliada.

29. Governança da Plataforma

Toda alteração relevante nas regras de negócio deverá:

ser registrada neste documento;
receber identificador RN;
possuir histórico de revisão;
preservar compatibilidade arquitetural;
identificar quando a regra é geral ou específica de uma linha de cuidado;
ser validada antes de ser considerada oficial quando envolver decisão clínica ou assistencial.
30. Gestão Populacional e Cockpit de Gestão

RN-260

O escopo do Cockpit de Gestão deverá respeitar o papel administrativo
do usuário.

O perfil ADMIN possui visão global da operação.

O perfil ADMIN_CLINICA possui visão restrita à clínica ou unidade à
qual está vinculado.

O escopo global do ADMIN não deverá ser restringido pelo `clinica_id`
eventualmente associado ao seu usuário.

RN-261

Para fins gerenciais, Pessoa Acompanhada representa paciente ativo
pertencente ao escopo administrativo considerado.

RN-262

Uma pessoa será considerada em Acompanhamento Ativo quando possuir ao
menos uma evidência assistencial válida nos últimos 30 dias.

RN-263

São consideradas evidências válidas para Acompanhamento Ativo:

Registro Diário;
Sessão Assistencial realizada;
Avaliação Clínica concluída;
Intervenção registrada.

RN-264

Para os indicadores de Acompanhamento Ativo e Atividade Assistencial,
somente Sessões Assistenciais efetivamente realizadas deverão ser
consideradas.

O agendamento de uma sessão, isoladamente, não caracteriza execução
assistencial.

RN-265

Cobertura Assistencial representa a proporção entre Pessoas em
Acompanhamento Ativo e Pessoas Acompanhadas dentro do mesmo escopo.

A regra de cálculo é:

~~~text
Cobertura Assistencial =
Pessoas em Acompanhamento Ativo / Pessoas Acompanhadas × 100
~~~

Quando não houver Pessoas Acompanhadas no escopo, a cobertura deverá
ser apresentada como zero, evitando divisão inválida.

RN-266

Continuidade Longitudinal representa a regularidade do Registro Diário
e deverá considerar o tempo transcorrido desde o último registro.

A classificação vigente é:

0 a 3 dias — REGULAR;
4 a 6 dias — ATENÇÃO;
7 dias ou mais — CRÍTICA;
nenhum Registro Diário — NÃO INICIADA.

RN-267

A ausência de Registro Diário por 7 dias ou mais deverá caracterizar
Alerta Crítico de Continuidade.

Essa condição não deverá, isoladamente, classificar a pessoa como alto
risco clínico.

RN-268

Risco Clínico e Continuidade Longitudinal representam dimensões
distintas.

O Risco Clínico deverá ser determinado pelo Clinical Engine.

A Continuidade Longitudinal deverá ser determinada pela regularidade
dos Registros Diários conforme as regras vigentes.

RN-269

Atenção Necessária representa o conjunto de pessoas únicas que possuam
ao menos um motivo objetivo de atenção clínica ou de continuidade.

RN-270

Os motivos que levam uma pessoa à condição de Atenção Necessária
deverão permanecer explícitos e rastreáveis.

Na versão atual, são considerados:

RISCO_CLINICO_ALTO;
ATENCAO_CLINICA;
PIORA_CLINICA;
CONTINUIDADE_CRITICA;
CONTINUIDADE_ATENCAO.

RN-271

A condição NÃO INICIADA deverá permanecer identificável na análise de
Continuidade Longitudinal.

Na versão atual, essa condição não deverá, isoladamente, incluir
automaticamente a pessoa em Atenção Necessária.

RN-272

Uma pessoa que possua múltiplos motivos de atenção deverá ser
contabilizada uma única vez no indicador Atenção Necessária.

Todos os motivos associados deverão, entretanto, ser preservados para
explicação e priorização.

RN-273

Para fins do Cockpit de Gestão, Profissional Ativo representa
profissional habilitado e atualmente vinculado à estrutura
assistencial considerada.

Essa classificação não exige atividade assistencial registrada nos
últimos 30 dias.

RN-274

Atividade Assistencial representa o volume de acontecimentos
assistenciais efetivamente realizados dentro do período considerado.

As categorias deverão permanecer separadas:

Registros Diários;
Sessões Assistenciais realizadas;
Avaliações Clínicas concluídas;
Intervenções.

A ausência de atividade em determinada categoria deverá ser
representada por zero.

RN-275

Na visão global do perfil ADMIN, a Estrutura da Operação deverá
permitir leitura por clínica ou unidade contendo, no mínimo:

Pessoas Acompanhadas;
Acompanhamento Ativo;
Cobertura Assistencial;
Atenção Necessária;
Profissionais Ativos.

Os totais da estrutura deverão ser reconciliáveis com os indicadores
globais equivalentes.

RN-276

O Cockpit de Gestão não deverá criar score gerencial opaco para
substituir os motivos objetivos de atenção.

A priorização deverá preservar, sempre que aplicável, a possibilidade
de identificar por que uma pessoa requer atenção.

31. Considerações Finais

As Regras de Negócio do Integra Care formalizam o conhecimento assistencial, funcional e operacional acumulado durante a evolução da plataforma.

Elas não representam apenas regras de software.

Representam a tradução de problemas reais da assistência em comportamentos consistentes, rastreáveis e reutilizáveis dentro da plataforma.

O Integra Care evolui sobre uma arquitetura na qual:

o planejamento organiza o cuidado;
a execução registra o que aconteceu;
a longitudinalidade preserva a trajetória;
e a inteligência transforma essa trajetória em conhecimento.

Princípio de Governança

Nenhuma funcionalidade relevante deverá ser considerada concluída sem passar pelo ciclo compatível com sua natureza:

Problema Real
     ↓
Regra de Negócio
     ↓
Planejamento Funcional
     ↓
Desenvolvimento
     ↓
Validação
     ↓
Homologação
     ↓
Produção
     ↓
Documentação

Histórico de Revisões
Versão	Data	Descrição
1.0.0	03/07/2026	Primeira versão oficial das Regras de Negócio
1.1.0	24/08/2026	Atualização da jornada assistencial, Sessões, Registro de Atendimento, Registro Diário multicanal, Clinical Engine, Momento Clínico, Painel Clínico Inteligente, regras Neuro/Cardio, Report Engine e governança da inteligência clínica

1.2.0   08/09/2026      Gestão populacional, acompanhamento ativo, cobertura assistencial, continuidade longitudinal, atenção necessária e regras do Cockpit de Gestão
© Integra Care Health Platform

Integra Care — Plataforma Modular de Gestão Longitudinal de Linhas de Cuidado