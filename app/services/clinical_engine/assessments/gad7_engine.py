from app.services.clinical_engine.base_engine import BaseAssessmentEngine
from app.services.gad7_contract import FIELDS


class GAD7Engine(BaseAssessmentEngine):
    instrumento = 'GAD7'
    versao = '1.0'

    def executar(self, context):
        if context.modulo_id != 3 or not context.metadata.get('contexto_assistencial_id'):
            raise ValueError('GAD7_REQUIRES_CONTEXT')
        answers = context.respostas
        if set(answers) != {name for name, _, _ in FIELDS} or any(type(v) is not str or v not in {'0','1','2','3'} for v in answers.values()):
            raise ValueError('INVALID_GAD7')
        score = sum(int(v) for v in answers.values())
        code, label = next((code,label) for ceiling,code,label in (
            (4,'MINIMA','Mínima'),(9,'LEVE','Leve'),(14,'MODERADA','Moderada'),
            (21,'GRAVE','Grave')) if score <= ceiling)
        return dict(instrumento=self.instrumento,instrumento_label='GAD-7',versao=self.versao,
                    score=score,score_max=21,classificacao=label,classificacao_codigo=code,
                    interpretacao=f'Intensidade de sintomas de ansiedade na faixa {label.lower()} do GAD-7, referente às últimas duas semanas. Resultado de rastreamento; não estabelece diagnóstico e deve ser interpretado por profissional habilitado.',
                    conduta='Revisar as respostas e o contexto clínico com a Pessoa; o instrumento não substitui avaliação clínica.',
                    alertas=[],metadata={'engine_version':'1.0','respostas':dict(answers),'periodo':'ULTIMAS_2_SEMANAS','contexto_assistencial_id':context.metadata['contexto_assistencial_id']})
