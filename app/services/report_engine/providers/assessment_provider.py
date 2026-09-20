from ..base_provider import BaseProvider, ProviderResult


class AssessmentProvider(BaseProvider):
    code = 'ASSESSMENT_PROVIDER'
    version = '2.0'

    def collect(self, context):
        rows = [{**e, 'instrumento':e['metadata']['instrument'],
                 'score':e['metadata']['score'], 'classificacao':e['metadata']['classification']}
                for e in context.collected_data['TIMELINE_PROVIDER'] if e['tipo_evento']=='ASSESSMENT']
        return ProviderResult(self.code,self.version,data=rows,metadata={'total_assessments':len(rows)})
