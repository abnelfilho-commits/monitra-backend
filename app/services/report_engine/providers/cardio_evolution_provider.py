from app.services.cardio_evolution import evolution
from ..base_provider import BaseProvider, ProviderResult


class CardioEvolutionProvider(BaseProvider):
    code = 'EVOLUTION_PROVIDER'
    version = '1.0'

    def collect(self, context):
        rows = evolution(context.db,[context.subject_id],context.care_line.module_id)
        start,end=context.period_start.isoformat(),context.period_end.isoformat()
        return ProviderResult(self.code,self.version,data=[r for r in rows if start<=r['data']<=end])
