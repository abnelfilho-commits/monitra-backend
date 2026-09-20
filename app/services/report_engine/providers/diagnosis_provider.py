from sqlalchemy import or_, and_
from app.models import Diagnostico
from app.services.diagnostico_service import DiagnosticoService
from ..base_provider import BaseProvider, ProviderResult


class DiagnosisProvider(BaseProvider):
    code = 'DIAGNOSIS_PROVIDER'
    version = '2.0'

    def collect(self, context):
        records = context.db.query(Diagnostico).filter(
            Diagnostico.paciente_id==context.subject_id,
            Diagnostico.modulo_id==context.care_line.module_id,
            or_(Diagnostico.data_diagnostico.between(context.period_start,context.period_end),
                and_(Diagnostico.status=='ATIVO',Diagnostico.data_diagnostico<context.period_start)))\
            .order_by(Diagnostico.data_diagnostico.desc(),Diagnostico.id.desc()).all()
        history = [{**DiagnosticoService.serializar_para_relatorio(r),
                    'temporal_scope':'ACTIVE_BEFORE_PERIOD' if r.data_diagnostico<context.period_start else 'IN_PERIOD'} for r in records]
        data={'historico':history,'total_diagnosticos':len(history),
              **{key:[d for d in history if d['status']==status] for key,status in
                 [('ativos','ATIVO'),('revisados','REVISADO'),('cancelados','CANCELADO')]}}
        return ProviderResult(self.code,self.version,data=data)
