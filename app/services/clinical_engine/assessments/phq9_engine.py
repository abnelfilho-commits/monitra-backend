from app.services.clinical_engine.base_engine import BaseAssessmentEngine
from app.services.phq9_contract import FIELDS


class PHQ9Engine(BaseAssessmentEngine):
    instrumento = 'PHQ9'
    versao = '1.0'

    def executar(self, context):
        if context.modulo_id != 3 or not context.metadata.get('contexto_assistencial_id'):
            raise ValueError('PHQ9_REQUIRES_CONTEXT')
        answers = context.respostas
        if set(answers) != {name for name, _, _ in FIELDS} or any(type(v) is not str or v not in {'0','1','2','3'} for v in answers.values()):
            raise ValueError('INVALID_PHQ9')
        score = sum(int(v) for v in answers.values())
        code, label = next((code,label) for ceiling,code,label in (
            (4,'MINIMA','Mínima'),(9,'LEVE','Leve'),(14,'MODERADA','Moderada'),
            (19,'MODERADAMENTE_GRAVE','Moderadamente grave'),(27,'GRAVE','Grave')) if score <= ceiling)
        alerts = []
        if answers['phq9_9'] != '0':
            alerts.append('Resposta positiva ao item 9. É necessária avaliação profissional de segurança e investigação de pensamentos de morte ou autoagressão, independentemente da pontuação total. O item isolado não determina o nível de risco.')
        return dict(instrumento=self.instrumento,instrumento_label='PHQ-9',versao=self.versao,
                    score=score,classificacao=label,classificacao_codigo=code,
                    interpretacao=f'Intensidade de sintomas na faixa {label.lower()} do PHQ-9, referente às últimas duas semanas. Resultado de rastreamento; não estabelece diagnóstico e deve ser interpretado por profissional habilitado.',
                    conduta='Revisar as respostas e o contexto clínico com a Pessoa; o instrumento não substitui avaliação clínica.',
                    alertas=alerts,metadata={'engine_version':'1.0','respostas':dict(answers),'periodo':'ULTIMAS_2_SEMANAS','contexto_assistencial_id':context.metadata['contexto_assistencial_id']})
