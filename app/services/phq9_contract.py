"""PHQ-9, Portuguese for Brazil. Reproduction permission is granted by the instrument.
Source: https://www.phqscreeners.com/images/sites/g/files/g10060481/f/201412/PHQ9_Portuguese%20for%20Brazil.pdf
Scoring: Kroenke et al. 2001 https://pmc.ncbi.nlm.nih.gov/articles/PMC1495268/
Nine scored items; no diagnostic algorithm or custom platform risk classification.
"""
CODE = 'PHQ9'
NAME = 'PHQ-9'
INSTRUCTION = 'Durante as últimas 2 semanas, com que frequência você foi incomodado/a por qualquer um dos problemas abaixo?'
OPTIONS = [('0','Nenhuma vez'),('1','Vários dias'),('2','Mais da metade dos dias'),('3','Quase todos os dias')]
QUESTIONS = [
 'Pouco interesse ou pouco prazer em fazer as coisas',
 'Se sentir “para baixo”, deprimido/a ou sem perspectiva',
 'Dificuldade para pegar no sono ou permanecer dormindo, ou dormir mais do que de costume',
 'Se sentir cansado/a ou com pouca energia',
 'Falta de apetite ou comendo demais',
 'Se sentir mal consigo mesmo/a — ou achar que você é um fracasso ou que decepcionou sua família ou você mesmo/a',
 'Dificuldade para se concentrar nas coisas, como ler o jornal ou ver televisão',
 'Lentidão para se movimentar ou falar, a ponto das outras pessoas perceberem? Ou o oposto – estar tão agitado/a ou irrequieto/a que você fica andando de um lado para o outro muito mais do que de costume',
 'Pensar em se ferir de alguma maneira ou que seria melhor estar morto/a',
]
FIELDS = [(f'phq9_{i}', question, OPTIONS) for i, question in enumerate(QUESTIONS,1)]
