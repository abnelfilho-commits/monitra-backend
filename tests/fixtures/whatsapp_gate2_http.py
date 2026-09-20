"""Actual local HTTP signed journeys; no real Meta transport or secrets."""
import os
import hashlib
import hmac
import json
import uuid
from datetime import date, timedelta
import requests
from sqlalchemy import text

if os.environ.get('DATABASE_URL') != 'postgresql+psycopg2://gate1@127.0.0.1/gate1_test':
    raise RuntimeError('Disposable Gate 2 only.')
from app.database import engine
API='http://127.0.0.1:8019'
prefix=uuid.uuid4().hex
counter=0
reference_date=date.today()-timedelta(days=int(os.getenv('WHATSAPP_GATE_DAY_OFFSET','0')))


def send(actor,content):
    global counter
    counter+=1
    body=json.dumps({'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':{
        'metadata':{'phone_number_id':'12345'},'messages':[{'id':prefix+'-'+str(counter),
        'from':'55659999900'+str(actor),'type':'text','text':{'body':content}}]}}]}]},ensure_ascii=False).encode()
    headers={'Content-Type':'application/json','X-Hub-Signature-256':'sha256='+hmac.new(
        b'synthetic-secret',body,hashlib.sha256).hexdigest()}
    response=requests.post(API+'/whatsapp/webhook',data=body,headers=headers,timeout=10)
    assert response.status_code==200,response.status_code
    return body,headers

assert requests.post(API+'/whatsapp/teste',json={},timeout=10).status_code==404
assert requests.post(API+'/whatsapp/webhook',json={},timeout=10).status_code==403
for actor,line in ((10,'NEURO'),(11,'CARDIO'),(12,'CARDIO'),(12,'NEURO')):
    send(actor,'oi')
    if actor==12:send(actor,line)
    values=('1','4','2','1','0','1','1','1','synthetic neuro','1') if line=='NEURO' else (
        '1','180','140','90','85','  synthetic Cardio observation\nexact  ','1')
    for value in values:body,headers=send(actor,value)
    # Retry the final confirmation over HTTP: no second record or transition.
    assert requests.post(API+'/whatsapp/webhook',data=body,headers=headers,timeout=10).status_code==200
with engine.connect() as conn:
    rows=conn.execute(text('''SELECT paciente_id,modulo_id,origem,criado_por_responsavel_id,data_registro
        FROM registros_longitudinais WHERE criado_por_responsavel_id IN (10,11,12) AND data_registro=:day
        ORDER BY criado_por_responsavel_id,modulo_id'''),{'day':reference_date}).all()
    assert [tuple(r[:4]) for r in rows]==[(1,1,'RESPONSAVEL_WHATSAPP',10),(2,2,'RESPONSAVEL_WHATSAPP',11),
        (3,1,'RESPONSAVEL_WHATSAPP',12),(3,2,'RESPONSAVEL_WHATSAPP',12)],rows
    assert all(r[4]==reference_date for r in rows)
    assert conn.execute(text("SELECT count(*) FROM whatsapp_mensagens WHERE message_id LIKE :prefix"),
        {'prefix':prefix+'-%'}).scalar()==counter
print('PASS actual signed HTTP: Neuro, Cardio, Multi-Line in both contexts, authorship, date and final-message replay.')
