"""Real HTTP synthetic Gate 3 journey, restricted to the existing disposable runtime."""
import os
import json
import uuid
import hashlib
import hmac
from datetime import date, timedelta
import requests
from sqlalchemy import func, text
from sqlalchemy.orm import Session

URL='postgresql+psycopg2://gate1@127.0.0.1/gate1_test'
if os.getenv('DATABASE_URL') != URL or os.getenv('WHATSAPP_ACCESS_TOKEN'):
    raise RuntimeError('Requires disposable database and no real Meta transport.')
from app.database import engine
from app.models import Responsavel, ResponsavelPaciente, FormularioModulo, CampoFormulario, RegistroLongitudinal, RespostaRegistro, Paciente
from app.core.security import hash_senha
API='http://127.0.0.1:8019'
run=uuid.uuid4().hex[:10]
today=date.today()
login=requests.post(API+'/auth/login',data={'username':'gate1@example.invalid','password':'synthetic-gate1-only'},timeout=10)
assert login.status_code==200,login.status_code
headers={'Authorization':'Bearer '+login.json()['access_token']}

def call(method,path,data=None):
    response=requests.request(method,API+path,json=data,headers=headers,timeout=15)
    assert response.status_code in (200,201),(path,response.status_code)
    return response.json()

# Prior fixtures intentionally used explicit synthetic IDs. Align only this
# disposable sequence before exercising the real patient-creation endpoint.
with engine.begin() as conn:
    conn.execute(text("SELECT setval(pg_get_serial_sequence('pacientes','id'), GREATEST(COALESCE((SELECT max(id) FROM pacientes),0),1), true)"))
patients={}
for role,module in (('Neuro',1),('Cardio',2),('Multi',2),('NoRecord',2)):
    patients[role]=call('POST','/pacientes/',{'nome':'Gate3 '+role+' '+run,'data_nascimento':'2000-01-01','modulo_id':module})['id']
call('POST',f"/pacientes/{patients['Multi']}/care-lines",{'care_line':'NEURO'})
# Synthetic responsible identities and historical observation with explicit units.
actors={}
with Session(engine) as db:
    next_id=(db.query(func.max(Responsavel.id)).scalar() or 0)+1
    for index,role in enumerate(('Neuro','Cardio','Multi')):
        identity=next_id+index
        phone='556598'+str(identity).zfill(7)
        email='gate3-'+role.lower()+'-'+run+'@example.invalid'
        db.add(Responsavel(id=identity,nome='Gate3 synthetic',email=email,senha_hash=hash_senha('synthetic-gate3-only'),telefone=phone,clinica_id=1,ativo=True));db.flush()
        db.add(ResponsavelPaciente(responsavel_id=identity,paciente_id=patients[role],ativo=True))
        actors[role]={'id':identity,'phone':phone,'email':email}
    form_id=(db.query(func.max(FormularioModulo.id)).scalar() or 0)+1
    db.add(FormularioModulo(id=form_id,modulo_id=2,nome='Gate3 historical synthetic',tipo='REGISTRO_DIARIO',ativo=False));db.flush()
    fields=[]
    field_id=(db.query(func.max(CampoFormulario.id)).scalar() or 0)+1
    for index,(name,label) in enumerate((('peso','Peso (kg)'),('altura','Altura (m)'))):
        field=CampoFormulario(id=field_id+index,formulario_id=form_id,nome_campo=name,label=label,tipo_campo='numero',ativo=False)
        db.add(field);db.flush();fields.append(field.id)
    record=RegistroLongitudinal(paciente_id=patients['Multi'],modulo_id=2,formulario_id=form_id,data_registro=today-timedelta(days=10),origem='PROFISSIONAL',criado_por_usuario_id=1)
    db.add(record);db.flush()
    for fid,value in zip(fields,(80,2)):
        db.add(RespostaRegistro(registro_id=record.id,campo_id=fid,valor_numero=value))
    db.commit()
for line in ('CARDIO','NEURO'):
    call('POST','/diagnosticos/',{'paciente_id':patients['Multi'],'care_line':line,'descricao_clinica':'Gate3 diagnosis '+line,'data_diagnostico':str(today),'medico_nome':'Synthetic'})
call('POST',f"/cardiometabolico/pacientes/{patients['Multi']}/intervencoes",{'tipo':'orientacao','descricao':'Gate3 Cardio intervention','prioridade':'moderada'})
call('POST','/cardiometabolico/registro-diario',{'paciente_id':patients['Multi'],'glicemia_jejum':180,'peso':85,'observacoes':'Gate3 portal text'})
a=actors['Multi']
login=requests.post(API+'/auth/responsavel/login',data={'username':a['email'],'password':'synthetic-gate3-only'},timeout=10)
assert login.status_code==200
response=requests.post(API+f"/responsavel/pacientes/{patients['Multi']}/registros-cardio",headers={'Authorization':'Bearer '+login.json()['access_token']},json={'data':str(today-timedelta(days=1)),'peso':85,'observacoes':'Gate3 APP text'},timeout=10)
assert response.status_code==200,response.text
counter=0

def send(role,message):
    global counter
    counter+=1
    body=json.dumps({'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{
        'metadata':{'phone_number_id':'12345'},'messages':[{'id':'gate3-'+run+'-'+str(counter),
        'from':actors[role]['phone'],'type':'text','text':{'body':message}}]}}]}]},ensure_ascii=False).encode()
    signature='sha256='+hmac.new(b'synthetic-secret',body,hashlib.sha256).hexdigest()
    h={'Content-Type':'application/json','X-Hub-Signature-256':signature}
    r=requests.post(API+'/whatsapp/webhook',data=body,headers=h,timeout=10)
    assert r.status_code==200,r.status_code
    return body,h
for role,line in (('Neuro','NEURO'),('Cardio','CARDIO'),('Multi','CARDIO'),('Multi','NEURO')):
    send(role,'oi')
    if role=='Multi':send(role,line)
    answers=('1','4','2','1','0','1','1','1','Gate3 Neuro','1') if line=='NEURO' else ('1','180','140','90','85','Gate3 WhatsApp text','1')
    for answer in answers:body,h=send(role,answer)
    replay=requests.post(API+'/whatsapp/webhook',data=body,headers=h,timeout=10)
    assert replay.status_code==200
pid=patients['Multi']
timeline=call('GET',f'/cardiometabolico/pacientes/{pid}/timeline')
assert all(e['care_line']=='CARDIO' for e in timeline)
assert {e['event_type'] for e in timeline}=={'DAILY_RECORD','DIAGNOSIS','INTERVENTION'}
assert {e['origem'] for e in timeline if e['event_type']=='DAILY_RECORD'}=={'PROFISSIONAL','RESPONSAVEL_APP','RESPONSAVEL_WHATSAPP'}
for e in timeline:
    if e['origem'] in ('RESPONSAVEL_APP','RESPONSAVEL_WHATSAPP'):
        assert e['actor']=={'namespace':'responsaveis','id':a['id'],'name':None}
assert {e['metadata'].get('observacoes') for e in timeline} >= {'Gate3 APP text','Gate3 portal text','Gate3 WhatsApp text'}
before=call('GET',f'/cardiometabolico/pacientes/{pid}/evolucao')
assert before[0]['imc']==20 and all(e['imc'] is None for e in before[1:])
with Session(engine) as db:
    db.query(Paciente).filter_by(id=pid).update({'altura':1.33});db.commit()
assert call('GET',f'/cardiometabolico/pacientes/{pid}/evolucao')==before
current=call('GET',f'/cardiometabolico/pacientes/{pid}')
assert current['tendencia'] is None and current['risco']=='moderado' and current['imc'] is None
empty=call('GET',f"/cardiometabolico/pacientes/{patients['NoRecord']}")
assert empty['risco'] is None and empty['ultima_atualizacao'] is None and empty['continuidade']['classification']=='NAO_INICIADA'
assert call('GET',f"/cardiometabolico/pacientes/{patients['NoRecord']}/timeline")==[]
for role in ('Neuro','Multi'):
    neuro=call('GET',f"/timeline/pacientes/{patients[role]}")
    assert neuro and 'Gate3 WhatsApp text' not in json.dumps(neuro)
page=call('GET','/cardiometabolico/dashboard-analytics?limit=100')
priorities=page['pacientes_criticos']
assert len({p['id'] for p in priorities})==len(priorities)
assert not any(name in page['capabilities'] for name in ('pts','agenda','sessions'))
for path,status in ((f"/cardiometabolico/pacientes/{patients['Neuro']}",403),('/cardiometabolico/pacientes/4',404)):
    assert requests.get(API+path,headers=headers,timeout=10).status_code==status
assert requests.get(API+'/cardiometabolico/dashboard-analytics',timeout=10).status_code==401
with open('/tmp/cardio-gate3-runtime.json','w') as f:json.dump({'patients':patients,'run':run},f)
print('PASS Gate3 real HTTP: three channels; Neuro/Cardio/Multi-Line; diagnosis/intervention; actor/channel; replay; historical BMI; no-data; ACL; Cockpit.')
print(json.dumps({'patients':patients,'run':run}))
