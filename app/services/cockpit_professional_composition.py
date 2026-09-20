"""Line-owned presentation policies, never clinical engine dispatch."""
from app.services.patient_line_service import list_patients
from app.services.clinical_reading import ClinicalReadingService
from app.services.timeline.professional_activity import recent_neuro_activity
from app.services.care_lines import care_line_registry
from app.services import cardio_longitudinal


def neuro(db, user, line, offset, limit):
    patients=list_patients(db,user,line.code)
    readings=ClinicalReadingService().get_readings(db,[p.id for p in patients],line.code)
    priorities=[]
    for p in patients:
        r=readings[p.id]
        if r.risk in ('alto_risco','atencao'):
            priorities.append({'paciente_id':p.id,'nome':p.nome,'clinica_id':p.clinica_id,
                'profissional_id':p.profissional_id,
                'profissional_nome':p.profissional.nome if p.profissional else None,
                'care_line':line.code,'risco_atual':r.risk,'tendencia':r.trend,
                'momento_clinico':r.clinical_state,'resumo_clinico':r.summary,
                'ultimo_registro':r.reference_date,'alertas':r.alerts,**r.metadata})
    priorities.sort(key=lambda r:(r.get('pontuacao_risco') or 0,r.get('total_registros') or 0),reverse=True)
    return {'total_pacientes':len(patients),'pacientes_prioritarios':priorities[offset:offset+limit],
            'atividades_recentes':recent_neuro_activity(db,patients,line,care_line_registry),
            'pagination':{'offset':offset,'limit':limit,'total':len(priorities)},'presentation':'neuro'}


def cardio(db, user, line, offset, limit):
    data=cardio_longitudinal.cockpit(db,user,offset,limit)
    return {'total_pacientes':data['indicadores']['total_pacientes'],
            'pacientes_prioritarios':data['pacientes_criticos'],
            'atividades_recentes':data['recent_activity'], 'pagination':data['pagination'],
            'presentation':'cardio','composition':data}


COMPOSITIONS={'NEURO':neuro,'CARDIO':cardio}
