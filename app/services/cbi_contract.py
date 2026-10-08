"""CBI Brazilian Portuguese for healthcare professionals, Moser et al. (2023), S1.
Literal items/order/options: https://doi.org/10.47626/2237-6089-2021-0362
https://minio.scielo.br/documentstore/2238-0019/Bd9NkmTgpNKKNs9dyPCDWLk/a932a59c4b9aea4c211e2adcfc539fbe5fb81b41.pdf
Scoring: https://nfa.dk/media/a4wheblj/cbi-scales.pdf
CBI freely usable with attribution: Borritz M et al., Scand J Public Health,
2006;34:49-58. No global score or universal diagnostic thresholds.
Complete 19-item applications only; no imputation/partial-domain computation.
WB4 is reverse-scored (same energy item as original English work item 7).
"""
CODE = 'CBI'
NAME = 'CBI'
VERSION = 'BR_HCP_2023_1'
INSTRUCTION = 'CBI — versão brasileira para profissionais de saúde (Moser et al., 2023). Responda às 19 questões considerando suas experiências. O domínio relacionado aos pacientes se refere ao trabalho com pacientes. Esta aplicação completa pressupõe trabalho e atendimento a pacientes; não preencha respostas fictícias quando um domínio não se aplicar.'
FREQUENCY = [('4','Sempre'),('3','Frequentemente'),('2','Às vezes'),('1','Raramente'),('0','Nunca')]
DEGREE = [('4','Em um grau muito alto'),('3','Em um grau alto'),('2','Em algum grau'),('1','Em baixo grau'),('0','Em um grau muito baixo')]
DOMAINS = [
 {'codigo':'PB','nome':'Burnout Pessoal','itens':[f'cbi_pb{i}' for i in range(1,7)]},
 {'codigo':'WB','nome':'Burnout relacionado ao trabalho','itens':[f'cbi_wb{i}' for i in range(1,8)]},
 {'codigo':'CB','nome':'Burnout relacionado aos pacientes','itens':[f'cbi_cb{i}' for i in range(1,7)]},
]
FIELDS = [
 ('cbi_pb1','Com que frequência você se sente cansado (a)?',FREQUENCY),
 ('cbi_pb2','Com que frequência você fica exausto (a) fisicamente?',FREQUENCY),
 ('cbi_pb3','Com que frequência você fica exausto (a) emocionalmente?',FREQUENCY),
 ('cbi_pb4','Com que frequência você pensa: “Eu não aguento mais”?',FREQUENCY),
 ('cbi_pb5','Com que frequência você se sente esgotado (a)?',FREQUENCY),
 ('cbi_pb6','Com que frequência você se sente fraco (a) e suscetível à doença?',FREQUENCY),
 ('cbi_wb1','Você se sente esgotado (a) no fim de um dia de trabalho?',FREQUENCY),
 ('cbi_wb2','Você fica exausto (a) pela manhã ao pensar em mais um dia de trabalho?',FREQUENCY),
 ('cbi_wb3','Você se sente mais cansado a cada hora de trabalho?',FREQUENCY),
 ('cbi_wb4','Você tem energia suficiente para família e amigos durante os momentos de lazer?',FREQUENCY),
 ('cbi_wb5','O seu trabalho é exaustivo emocionalmente?',DEGREE),
 ('cbi_wb6','O seu trabalho lhe frustra?',DEGREE),
 ('cbi_wb7','Você se sente esgotado por causa do seu trabalho?',DEGREE),
 ('cbi_cb1','Você acha difícil trabalhar com pacientes?',DEGREE),
 ('cbi_cb2','Trabalhar com pacientes suga a sua energia?',DEGREE),
 ('cbi_cb3','Você acha frustrante trabalhar com pacientes?',DEGREE),
 ('cbi_cb4','Você sente que está dando mais do que recebe quando você trabalha com pacientes?',DEGREE),
 ('cbi_cb5','Você está cansado (a) de trabalhar com pacientes?',FREQUENCY),
 ('cbi_cb6','Você às vezes se pergunta quanto tempo será capaz de continuar trabalhando com pacientes?',FREQUENCY),
]
REVERSED = 'cbi_wb4'
