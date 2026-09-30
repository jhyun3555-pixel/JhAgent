import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from backend.database import Database
from backend.engine import Engine
from backend.analytics import create_report, csv_report, html_report
from backend.validation import validate_request
from backend.policy import forbidden_text


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / 'test.db')
        self.db.seed_customers()
        self.engine = Engine(self.db, delay=0)

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def event(self, customer='C0001', event='salary', **extra):
        jid = self.engine.submit({'mode':'event','event_type':event,'customer_id':customer,'amount':4200000,'channel':'push',**extra}, background=False)
        self.engine.run(jid, fast=True)
        return self.db.job(jid)

    def campaign(self, **extra):
        jid = self.engine.submit({'mode':'campaign','brief':'여유자금 포트폴리오 안내 캠페인','domain':'portfolio','min_balance':10000000,'budget':10000,'max_audience':20,'channel':'push',**extra}, background=False)
        self.engine.run(jid, fast=True)
        return self.db.job(jid)

    def test_consent_gate_and_customer_choice(self):
        job = self.event()
        self.assertEqual(job['status'], 'waiting_customer')
        self.assertEqual(len(job['deliveries']), 1)
        with self.assertRaises(ValueError):
            self.engine.decide(job['id'], 'accept', consent=False, background=False)
        self.engine.decide(job['id'], 'accept', consent=True, background=False)
        self.engine.run(job['id'], fast=True)
        job = self.db.job(job['id'])
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(job['results']['performance']['converted'], 1)
        self.assertEqual(len(job['deliveries']), 1)
        with self.assertRaises(ValueError):
            self.engine.decide(job['id'], 'accept', consent=True)

    def test_policy_no_consent_and_frequency(self):
        for cid in ('C0004', 'C0005'):
            with self.subTest(cid=cid):
                job = self.event(cid)
                self.assertEqual(job['status'], 'blocked')
                self.assertFalse(job['deliveries'])
                self.assertTrue(job['results']['compliance']['reasons'])

    def test_no_opportunity_stops_before_content(self):
        job = self.event('C0006', 'quiet')
        self.assertEqual(job['status'], 'no_action')
        self.assertNotIn('content', job['results'])
        self.assertFalse(job['deliveries'])

    def test_mydata_skill_routes_before_tax_review(self):
        job = self.event('C0003', 'tax')
        self.assertEqual(job['results']['opportunity']['domain'], 'mydata')
        self.assertEqual(job['status'], 'waiting_customer')

    def test_all_six_domain_tools(self):
        from backend.skills.opportunities import discover
        c = self.db.customers('C0001')[0]
        for event, expected in [('salary','portfolio'),('maturity','deposit'),('loan','loan'),('card','card'),('tax','tax')]:
            with self.subTest(event=event):
                self.assertEqual(discover(c,event)[0]['domain'],expected)
        c['mydata']=0
        self.assertEqual(discover(c,'tax')[0]['domain'],'mydata')

    def test_campaign_approval_audience_and_budget(self):
        job = self.campaign()
        self.assertEqual(job['status'], 'waiting_approval')
        self.assertFalse(job['deliveries'])
        self.assertNotIn('C0004', job['results']['audience']['customer_ids'])
        self.assertNotIn('C0005', job['results']['audience']['customer_ids'])
        self.engine.decide(job['id'], 'approve', background=False)
        self.engine.run(job['id'], fast=True)
        job = self.db.job(job['id'])
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(len(job['deliveries']), 20)
        self.assertEqual(job['results']['performance']['cost'], 400)

    def test_over_budget_and_no_audience_block(self):
        for kwargs in ({'budget':0},{'min_balance':999999999}):
            job=self.campaign(**kwargs)
            self.assertEqual(job['status'],'blocked')
            self.assertFalse(job['deliveries'])

    def test_final_policy_recheck_after_approval(self):
        job=self.campaign()
        cid=job['results']['audience']['customer_ids'][0]
        self.db.execute('UPDATE customers SET consent=0 WHERE id=?',(cid,))
        self.engine.decide(job['id'],'approve',background=False)
        self.engine.run(job['id'],fast=True)
        after=self.db.job(job['id'])
        self.assertEqual(after['status'],'failed')
        self.assertFalse(after['deliveries'])

    def test_idempotent_creation_and_outbox(self):
        req={'mode':'event','event_type':'salary','customer_id':'C0001'}
        first=self.engine.submit(req,key='same',background=False)
        self.assertEqual(first,self.engine.submit(req,key='same',background=False))
        with self.assertRaises(ValueError):
            self.engine.submit({**req,'customer_id':'C0002'},key='same',background=False)
        self.engine.run(first,fast=True)
        self.engine.dispatch(self.db.job(first),preview=True)
        self.assertEqual(len(self.db.job(first)['deliveries']),1)

    def test_subprocess_isolation_and_failure_resume(self):
        job=self.event(inject_failure='insight')
        self.assertEqual(job['status'],'failed')
        self.assertEqual(len(job['steps']),2)
        self.engine.retry(job['id'])
        self.engine.pool.shutdown(wait=True)
        after=self.db.job(job['id'])
        self.assertEqual(after['status'],'waiting_customer')
        self.assertEqual(sum(s['agent_id']=='supervisor' for s in after['steps']),1)
        self.assertEqual(sum(s['agent_id']=='insight' for s in after['steps']),2)

    def test_recovery_preserves_approval_and_marks_inflight_failed(self):
        waiting=self.campaign()
        pending=self.engine.submit({'mode':'event','event_type':'quiet','customer_id':'C0001'},background=False)
        other=Engine(self.db,delay=0)
        self.assertEqual(self.db.job(waiting['id'])['status'],'waiting_approval')
        self.assertEqual(self.db.job(pending)['status'],'failed')
        other.close()

    def test_cancel_and_reject_never_dispatch(self):
        job=self.campaign()
        self.engine.decide(job['id'],'reject',background=False)
        self.assertEqual(self.db.job(job['id'])['status'],'cancelled')
        self.assertFalse(self.db.job(job['id'])['deliveries'])
        jid=self.engine.submit({'mode':'event','event_type':'salary','customer_id':'C0001'},background=False)
        self.engine.cancel(jid)
        self.engine.run(jid,fast=True)
        self.assertFalse(self.db.job(jid)['steps'])

    def test_report_is_immutable_reconciles_and_escapes(self):
        job=self.campaign(brief='=HYPERLINK("evil") <script>alert(1)</script>')
        self.engine.decide(job['id'],'approve',background=False)
        self.engine.run(job['id'],fast=True)
        report=create_report(self.db,7)
        self.assertEqual(report['data']['metrics']['sent'],20)
        self.assertEqual(sum(v['sent'] for v in report['data']['variants']),20)
        self.assertIn("'=HYPERLINK",csv_report(report))
        self.assertNotIn('<script>alert(1)</script>',html_report(report))
        before=json.dumps(report)
        self.event()
        self.assertEqual(json.dumps(report),before)

    def test_validation_and_forbidden_claims(self):
        for bad in (float('nan'),float('inf'),True,-1,'100',1.2):
            with self.assertRaises(ValueError):
                validate_request({'mode':'event','event_type':'salary','customer_id':'C0001','amount':bad})
        with self.assertRaises(ValueError):
            self.engine.submit({'mode':'event','event_type':'salary','customer_id':"';DROP TABLE jobs;--"},background=False)
        self.assertEqual(forbidden_text('원금보장, 확정\n수익'),['원금 보장','확정 수익'])
        self.assertEqual(len(self.db.customers()),240)

    def test_concurrent_outbox_frequency_is_atomic(self):
        jobs=[]
        for _ in range(4):
            jid=self.engine.submit({'mode':'event','event_type':'salary','customer_id':'C0001','channel':'push'},background=True)
            jobs.append(jid)
        self.engine.pool.shutdown(wait=True)
        sent=self.db.one('SELECT COUNT(*) n FROM deliveries')['n']
        self.assertEqual(sent,3)
        self.assertTrue(any(self.db.job(j)['status'] in ('blocked','failed') for j in jobs))

    def test_provider_failures_do_not_silently_fallback(self):
        from backend.provider import generate
        with patch.dict(os.environ,{'AGENT_PROVIDER':'openai','OPENAI_API_KEY':'','OPENAI_MODEL':''}):
            with self.assertRaises(ValueError):
                generate(['title'],'draft',{'title':'fallback'})


if __name__=='__main__':
    unittest.main()
