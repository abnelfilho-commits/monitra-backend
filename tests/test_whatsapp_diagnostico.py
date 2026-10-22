"""D9.2-D: real PostgreSQL authorization, evidence and read-only HTTP."""
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import FastAPI
import test_whatsapp_convite_status as base
from app.routers import whatsapp_mental
from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio


@unittest.skipUnless(base.foundation.foundation.URL, 'Disposable PostgreSQL required')
class DiagnosticTests(unittest.TestCase):
    setUpClass = classmethod(base.StatusTests.setUpClass.__func__)
    cleanup = classmethod(base.StatusTests.cleanup.__func__)
    snapshot = base.StatusTests.snapshot
    command_grant = base.StatusTests.command_grant
    path = base.StatusTests.path
    response = base.StatusTests.response
    send = base.StatusTests.send
    status = base.StatusTests.status
    payload = base.StatusTests.payload
    post = base.StatusTests.post
    bind = base.StatusTests.bind
    rows = base.StatusTests.rows

    def setUp(self):
        base.StatusTests.setUp(self)
        self.app.include_router(whatsapp_mental.router)
        self.app.dependency_overrides[get_usuario_atual] = lambda: SimpleNamespace(id=self.actor)

    def get(self, institution=None):
        return self.client.get(f'/saude-mental/pessoas/{self.person}/contextos/{self.open}/whatsapp/diagnostico', params={'instituicao_id':institution or self.institution})

    def test_authorized_read_only_and_legacy(self):
        self.db.execute(text('UPDATE whatsapp_conversas_contextuais SET convite_enviado_em=:t WHERE id=:i'),dict(t=self.now,i=self.cid));self.db.commit()
        before=self.snapshot()
        r=self.get();self.assertEqual(r.status_code,200,r.text)
        c=r.json()['conversas'][0]
        self.assertTrue(c['ausencia_rastreabilidade_historica']);self.assertEqual(c['tentativas'],[])
        self.assertEqual(c['observacao_historica'],'Aceitação local histórica conhecida; entrega não confirmada.')
        self.assertEqual({k:v[1] for k,v in before.items()},{k:v[1] for k,v in self.snapshot().items()})

    def test_wrong_institution_denied(self):
        self.assertEqual(self.get(999999).status_code,403)

    def test_without_read_grant_denied_even_with_write(self):
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'),dict(i=self.grant_ids[self.open,'ASSISTENCIAL_LER']));self.db.commit()
        self.assertEqual(self.get().status_code,403)

    def test_all_attempt_states_and_sanitized_response(self):
        for n,state in enumerate(('PREPARADO','EM_EXECUCAO','ACEITO','REJEITADO','INCERTO'),1):
            self.db.add(Envio(conversa_id=self.cid,tentativa=n,correlacao_id=str(uuid4()),phone_number_id='12345',
                estado=state,wamid=self.wamid if state=='ACEITO' else None,
                confirmado_em=self.now if state=='ACEITO' else None,motivo_sanitizado='SECRET_PRIVATE_PHONE'))
        self.db.commit()
        r=self.get();self.assertEqual(r.status_code,200,r.text)
        attempts=r.json()['conversas'][0]['tentativas']
        self.assertEqual([a['resultado_incerto'] for a in attempts],[False,True,False,False,True])
        self.assertTrue(attempts[2]['aceito_meta']);self.assertTrue(attempts[3]['rejeitado_meta'])
        self.assertTrue(all(not a['entrega_confirmada'] for a in attempts))
        for forbidden in ('SECRET','telefone','phone_number_id','respostas_json','token'):
            self.assertNotIn(forbidden,r.text)

    def test_out_of_order_contradictory_evidence(self):
        self.bind()
        for state,stamp in (('read','1792706900'),('delivered','1792706800'),('sent','1792707000'),('failed','1792707100')):
            self.assertEqual(self.post([self.status(state,timestamp=stamp)]).status_code,200)
        a=self.get().json()['conversas'][0]['tentativas'][0]
        self.assertEqual(a['ultimo_evento']['status'],'failed')
        self.assertEqual(a['maior_confirmacao_observada'],'read')
        self.assertTrue(a['evidencia_contraditoria']);self.assertTrue(a['entrega_confirmada'])
        self.assertEqual(len(a['eventos']),4)

    def test_uncorrelated_not_exposed(self):
        self.bind(emitter='different')
        self.assertEqual(self.post([self.status('failed',errors=[{'code':123,'error_subcode':456}])]).status_code,200)
        a=self.get().json()['conversas'][0]['tentativas'][0]
        self.assertEqual(a['eventos'],[]);self.assertIsNone(a['ultimo_evento'])

    def test_unknown_status_does_not_block_valid_siblings_or_messages(self):
        message={'id':'incoming-'+uuid4().hex,'from':'5511999999999','type':'text','text':{'body':'oi'}}
        with patch.object(base.whatsapp,'process_message',return_value=(None, None)) as received, patch.object(base.whatsapp,'deliver_reply'):
            r=self.post([self.status('future_meta_status'),self.status('delivered')],messages=[message])
            self.assertEqual(r.status_code,200,r.text);received.assert_called_once()
        self.assertEqual([r['status'] for r in self.rows()],['delivered'])

    def test_admin_and_support_without_grants_denied(self):
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE contexto_assistencial_id=:c'),dict(c=self.open))
        for profile in ('ADMIN','SUPORTE'):
            self.db.execute(text('UPDATE usuarios SET perfil=:p WHERE id=:i'),dict(p=profile,i=self.actor));self.db.commit()
            self.assertEqual(self.get().status_code,403)

    def test_read_grant_sufficient_without_write(self):
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'),dict(i=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']));self.db.commit()
        self.assertEqual(self.get().status_code,200)
