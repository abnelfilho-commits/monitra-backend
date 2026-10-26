"""Real PostgreSQL lock coordination, using an owned migrated database."""
import hashlib
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from sqlalchemy import text
from sqlalchemy.orm import Session
import test_whatsapp_convite_envio as delivery
from app.services.whatsapp_locks import acquire, transport, message, Resource, Phase, LockOrderError, LockUnavailable


@unittest.skipUnless(delivery.foundation.URL, 'Exclusive disposable PostgreSQL required')
class LockTests(unittest.TestCase):
    setUpClass = classmethod(delivery.DeliveryTests.setUpClass.__func__)
    cleanup = classmethod(delivery.DeliveryTests.cleanup.__func__)

    def test_variants_serialize_not_identify(self):
        self.assertEqual(transport('test', '5511900000001'), transport('test', '551100000001'))
        self.assertNotEqual(transport('other', '5511900000001'), transport('test', '551100000001'))

    def test_message_key_backward_compatible(self):
        value=json.dumps(['invitation-status-v1','123','wamid.synthetic'],separators=(',',':'))
        self.assertEqual(message('123','wamid.synthetic').key(),int.from_bytes(hashlib.sha256(value.encode()).digest()[:8],'big',signed=True))

    def test_order_and_duplicate_acquisition(self):
        with Session(self.engine) as db:
            resources=[Resource(p,'test',('1',)) for p in reversed(list(Phase))]
            acquire(db,resources,timeout_ms=100)
            acquire(db,resources)
            self.assertEqual(len(db.info['whatsapp_lock_plan'][1]),6)
            db.rollback()
            acquire(db,[resources[-1]])
            db.rollback()

    def test_late_inversion_rolls_back(self):
        with Session(self.engine) as db:
            acquire(db,[Resource(Phase.PERSISTENCE,'test',('1',))])
            with self.assertRaises(LockOrderError):
                acquire(db,[Resource(Phase.OPERATION,'test',('1',))])
            self.assertFalse(db.in_transaction())

    def test_timeout_rollback_and_recovery(self):
        resource=transport('test','551100000001')
        with Session(self.engine) as first, Session(self.engine) as second:
            acquire(first,[resource])
            second.execute(text('CREATE TEMP TABLE rollback_probe (id integer)'))
            with self.assertRaises(LockUnavailable):
                acquire(second,[transport('test','5511900000001')],timeout_ms=100)
            self.assertFalse(second.in_transaction())
            self.assertIsNone(second.scalar(text("SELECT to_regclass('pg_temp.rollback_probe')")))
            second.rollback()
            first.rollback()
            acquire(second,[resource],timeout_ms=100)
            second.rollback()

    def test_concurrent_reverse_plans_complete(self):
        ready=Event(); release=Event(); entered=Event()
        resources=[message('test','wamid.a'),message('test','wamid.b')]
        def first():
            with Session(self.engine) as db:
                acquire(db,resources);ready.set()
                if not release.wait(5): raise AssertionError('release timeout')
                db.commit()
        def second():
            with Session(self.engine) as db:
                acquire(db,list(reversed(resources)),timeout_ms=2000);entered.set();db.commit()
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(first)
            self.assertTrue(ready.wait(5))
            b=pool.submit(second)
            try: self.assertFalse(entered.wait(.15))
            finally: release.set()
            a.result(5);b.result(5)
        self.assertTrue(entered.is_set())

    def test_emitters_independent(self):
        with Session(self.engine) as first, Session(self.engine) as second:
            acquire(first,[transport('one','551100000001')])
            acquire(second,[transport('two','551100000001')],timeout_ms=100)
            first.rollback();second.rollback()

    def test_canonical_no_key_update_preserved(self):
        from app.services.daily_record.concurrency import lock_patient
        from sqlalchemy import event
        statements=[]
        def capture(conn,cursor,statement,parameters,context,executemany): statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            with Session(self.engine) as db:
                acquire(db,[transport('test','551100000001')])
                lock_patient(db,-1)
                db.rollback()
        finally: event.remove(self.engine,'before_cursor_execute',capture)
        self.assertTrue(any('FOR NO KEY UPDATE' in s for s in statements))
