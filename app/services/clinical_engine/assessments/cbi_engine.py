from decimal import Decimal, ROUND_HALF_UP
from app.services.clinical_engine.base_engine import BaseAssessmentEngine
from app.services.cbi_contract import FIELDS, DOMAINS, REVERSED, VERSION


class CBIEngine(BaseAssessmentEngine):
    instrumento = 'CBI'
    versao = VERSION

    def executar(self, context):
        if context.modulo_id != 3 or not context.metadata.get('contexto_assistencial_id'):
            raise ValueError('CBI_REQUIRES_CONTEXT')
        answers = context.respostas
        if set(answers) != {name for name, _, _ in FIELDS} or any(type(v) is not str or v not in {'0','1','2','3','4'} for v in answers.values()):
            raise ValueError('INVALID_CBI')
        points = {key: (100-int(value)*25 if key == REVERSED else int(value)*25) for key,value in answers.items()}
        domains = []
        for domain in DOMAINS:
            total = sum(points[key] for key in domain['itens'])
            count = len(domain['itens'])
            domains.append(dict(domain, score=float((Decimal(total)/count).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),
                                score_max=100,soma=total,quantidade_itens=count))
        return dict(instrumento='CBI',instrumento_label='CBI',versao=VERSION,dominios=domains,
                    interpretacao='Resultados por domínio do CBI, de 0 a 100: valores maiores indicam maior exaustão relatada naquele domínio. Não há escore global nesta avaliação. Os resultados não constituem diagnóstico isoladamente e devem ser interpretados no contexto clínico e profissional.',
                    metadata={'engine_version':'1.0','respostas':dict(answers),'pontuacoes_itens':points,
                              'rotulos_respostas':{key:dict(options)[answers[key]] for key,_,options in FIELDS},
                              'dominio_por_item':{key:d['codigo'] for d in DOMAINS for key in d['itens']},
                              'item_invertido':REVERSED,'metodo':'MEDIA_ARITMETICA_POR_DOMINIO_19_RESPOSTAS',
                              'fonte':'Moser et al. 2023, doi:10.47626/2237-6089-2021-0362; Borritz et al. 2006, Scand J Public Health 34:49-58',
                              'contexto_assistencial_id':context.metadata['contexto_assistencial_id']})
