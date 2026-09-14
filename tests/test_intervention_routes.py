"""Exercise the seven legacy HTTP facades with synthetic authenticated contexts."""
import asyncio
import json
from types import SimpleNamespace
from fastapi import FastAPI
from app.database import get_db
from app.core.deps import get_usuario_atual
from app.routers import intervencoes, cardiometabolico
from app.models.modular import PacienteModulo
from test_interventions import Fixture, G, DAY


class RouteTests(Fixture):
    def request(self, method, path, payload=None, authenticated=True):
        app = FastAPI()
        app.include_router(intervencoes.router)
        app.include_router(cardiometabolico.router)
        app.dependency_overrides[get_db] = lambda: self.db
        if authenticated:
            app.dependency_overrides[get_usuario_atual] = lambda: self.user
        async def run():
            messages=[]
            delivered=False
            async def receive():
                nonlocal delivered
                if not delivered:
                    delivered=True
                    return {'type':'http.request','body':json.dumps(payload).encode(),'more_body':False}
                await asyncio.sleep(3600)
            async def send(message): messages.append(message)
            scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,
                'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'',
                'headers':[(b'content-type',b'application/json')], 'client':('127.0.0.1',1),
                'server':('test',80),'root_path':''}
            await app(scope,receive,send)
            status=next(m['status'] for m in messages if m['type']=='http.response.start')
            body=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
            return SimpleNamespace(status_code=status,json=json.loads(body))
        return asyncio.run(run())

    def payload(self, **changes):
        result={'paciente_id':10,'tipo':'ABA','descricao':'Synthetic','data_intervencao':DAY.isoformat()}
        result.update(changes)
        return result

    def operations(self, identity):
        return [('POST','/intervencoes/',self.payload()),
            ('GET','/intervencoes/paciente/10',None),
            ('GET','/intervencoes/'+str(identity),None),
            ('PUT','/intervencoes/'+str(identity),self.payload()),
            ('DELETE','/intervencoes/'+str(identity),None),
            ('POST','/cardiometabolico/pacientes/11/intervencoes',{'tipo':'nutricao','descricao':'Synthetic','prioridade':'alta'}),
            ('GET','/cardiometabolico/pacientes/11/intervencoes',None)]

    def test_seven_routes_require_authentication(self):
        r=self.generic()
        for method,path,payload in self.operations(r.source_id):
            with self.subTest(method=method,path=path):
                response=self.request(method,path,payload,authenticated=False)
                self.assertEqual(response.status_code,401,response.json)

    def test_seven_routes_reject_other_clinic_and_admin_clinica(self):
        r=self.generic()
        for role in ('PROFISSIONAL','ADMIN_CLINICA'):
            self.user.perfil=role; self.user.clinica_id=2
            for method,path,payload in self.operations(r.source_id):
                with self.subTest(role=role,method=method,path=path):
                    response=self.request(method,path,payload)
                    self.assertEqual(response.status_code,403,response.json)

    def test_seven_routes_allow_same_clinic(self):
        r=self.generic()
        for method,path,payload in self.operations(r.source_id):
            with self.subTest(method=method,path=path):
                response=self.request(method,path,payload)
                self.assertEqual(response.status_code,200,response.json)

    def test_seven_routes_preserve_admin_policy(self):
        r=self.generic()
        self.user.perfil='ADMIN'; self.user.clinica_id=None; self.user.profissional_id=None
        for method,path,payload in self.operations(r.source_id):
            with self.subTest(method=method,path=path):
                response=self.request(method,path,payload)
                self.assertEqual(response.status_code,200,response.json)

    def test_generic_shapes_author_and_immutability(self):
        response=self.request('POST','/intervencoes/',self.payload(profissional_id=999,modulo_id=999))
        self.assertEqual(response.status_code,200,response.json)
        original=response.json
        self.assertEqual(set(original),{'id','paciente_id','profissional_id','tipo','descricao','data_intervencao','created_at'})
        self.assertEqual(original['profissional_id'],50)
        identity=original['id']
        self.user.id=60
        response=self.request('PUT','/intervencoes/'+str(identity),self.payload(tipo='edited',modulo_id=2,profissional_id=60))
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['profissional_id'],50)
        self.assertEqual(response.json['created_at'],original['created_at'])
        self.assertEqual(self.service.get(self.db,G,identity,user=self.user).module_id,1)
        rejected=self.request('PUT','/intervencoes/'+str(identity),self.payload(paciente_id=11))
        self.assertEqual(rejected.status_code,409)
        self.assertIn('INTERVENTION_IDENTITY_CONFLICT',rejected.json['detail'])
        response=self.request('DELETE','/intervencoes/'+str(identity))
        self.assertEqual(response.json,{'ok':True})

    def test_cardio_shapes_and_source_only_listing(self):
        self.historical(patient=11)
        response=self.request('POST','/cardiometabolico/pacientes/11/intervencoes',{'tipo':'nutricao','descricao':'','prioridade':'alta'})
        self.assertEqual(response.json,{'success':True})
        listed=self.request('GET','/cardiometabolico/pacientes/11/intervencoes')
        self.assertEqual(len(listed.json),1)
        self.assertEqual(set(listed.json[0]),{'id','tipo','descricao','prioridade','created_at'})
        self.assertEqual(listed.json[0]['prioridade'],'alta')
        generic=self.request('GET','/intervencoes/paciente/11')
        self.assertEqual(len(generic.json),1)
        self.assertEqual(generic.json[0]['tipo'],'historical')

    def test_ambiguous_create_has_no_fallback_and_explicit_works(self):
        self.db.add(PacienteModulo(paciente_id=10,modulo_id=2,ativo=True)); self.db.commit()
        response=self.request('POST','/intervencoes/',self.payload())
        self.assertEqual(response.status_code,409)
        self.assertIn('AMBIGUOUS_CARE_LINE',response.json['detail'])
        self.assertEqual(self.service.list_for_patient(self.db,10,user=self.user),[])
        response=self.request('POST','/intervencoes/',self.payload(requested_care_line='NEURO'))
        self.assertEqual(response.status_code,200,response.json)

    def test_generic_payload_cannot_silently_become_cardio(self):
        response=self.request('POST','/intervencoes/',self.payload(paciente_id=11))
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.service.list_for_patient(self.db,11,user=self.user),[])

    def test_update_acl_uses_resource_patient(self):
        identity=self.historical(patient=20)
        response=self.request('PUT','/intervencoes/'+str(identity),self.payload())
        self.assertEqual(response.status_code,403)
