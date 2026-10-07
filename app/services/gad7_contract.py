"""GAD-7, Portuguese for Brazil, literal seven-item content from the official PDF.
Source: https://www.phqscreeners.com/images/sites/g/files/g10060481/f/201412/GAD7_Portuguese%20for%20Brazil.pdf
Scoring: Spitzer et al. 2006, https://doi.org/10.1001/archinte.166.10.1092
The instrument explicitly permits reproduction, translation, display and distribution.
No diagnostic algorithm, probability or platform risk classification.
"""
CODE = 'GAD7'
NAME = 'GAD-7'
INSTRUCTION = 'Durante as últimas 2 semanas, com que freqüência você foi incomodado/a pelos problemas abaixo?'
OPTIONS = [('0','Nenhuma vez'),('1','Vários dias'),('2','Mais da metade dos dias'),('3','Quase todos os dias')]
QUESTIONS = [
 'Sentir-se nervoso/a, ansioso/a ou muito tenso/a',
 'Não ser capaz de impedir ou de controlar as preocupações',
 'Preocupar-se muito com diversas coisas',
 'Dificuldade para relaxar',
 'Ficar tão agitado/a que se torna difícil permanecer sentado/a',
 'Ficar facilmente aborrecido/a ou irritado/a',
 'Sentir medo como se algo horrível fosse acontecer',
]
FIELDS = [(f'gad7_{i}', question, OPTIONS) for i, question in enumerate(QUESTIONS,1)]
