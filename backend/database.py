import json
import random
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, segment TEXT NOT NULL,
                balance INTEGER NOT NULL, salary INTEGER NOT NULL,
                consent INTEGER NOT NULL, mydata INTEGER NOT NULL,
                risk_profile INTEGER NOT NULL, has_portfolio INTEGER NOT NULL,
                recent_sends INTEGER NOT NULL, recent_at REAL NOT NULL,
                maturity_days INTEGER NOT NULL, loan_balance INTEGER NOT NULL,
                card_spend INTEGER NOT NULL
              );
              CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, mode TEXT NOT NULL,
                status TEXT NOT NULL, active_agent TEXT, request TEXT NOT NULL,
                results TEXT NOT NULL DEFAULT '{}', decision TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                duration_ms REAL NOT NULL DEFAULT 0, error TEXT,
                parent_id TEXT, idempotency_key TEXT UNIQUE,
                seeded INTEGER NOT NULL DEFAULT 0
              );
              CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id),
                agent_id TEXT NOT NULL, status TEXT NOT NULL, started_at REAL NOT NULL,
                ended_at REAL, duration_ms REAL, input TEXT NOT NULL,
                output TEXT, error TEXT
              );
              CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id),
                customer_id TEXT NOT NULL REFERENCES customers(id), channel TEXT NOT NULL,
                variant TEXT NOT NULL, opened INTEGER NOT NULL DEFAULT 0,
                clicked INTEGER NOT NULL DEFAULT 0, converted INTEGER NOT NULL DEFAULT 0,
                cost INTEGER NOT NULL, created_at REAL NOT NULL, synthetic INTEGER NOT NULL DEFAULT 1,
                UNIQUE(job_id, customer_id)
              );
              CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT REFERENCES jobs(id),
                kind TEXT NOT NULL, message TEXT NOT NULL, created_at REAL NOT NULL
              );
              CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL,
                data TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
              CREATE INDEX IF NOT EXISTS idx_steps_job ON steps(job_id);
              CREATE INDEX IF NOT EXISTS idx_delivery_customer_time ON deliveries(customer_id, created_at);
              PRAGMA user_version=1;
            ''')

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        try:
            with con:
                yield con
        finally:
            con.close()

    def rows(self, sql, params=()):
        with self.connect() as con:
            return [dict(r) for r in con.execute(sql, params)]

    def one(self, sql, params=()):
        rows = self.rows(sql, params)
        return rows[0] if rows else None

    def execute(self, sql, params=()):
        with self.connect() as con:
            return con.execute(sql, params).lastrowid

    def audit(self, job_id, kind, message):
        self.execute('INSERT INTO audit(job_id,kind,message,created_at) VALUES(?,?,?,?)', (job_id, kind, message, time.time()))

    def customers(self, customer_id=None, con=None):
        now = time.time()
        sql = '''SELECT c.*, (CASE WHEN c.recent_at > ? THEN c.recent_sends ELSE 0 END) +
                 (SELECT COUNT(*) FROM deliveries d WHERE d.customer_id=c.id AND d.created_at > ?) AS sends_now
                 FROM customers c'''
        args = [now - 7 * 86400, now - 7 * 86400]
        if customer_id:
            sql += ' WHERE c.id=?'
            args.append(customer_id)
        sql += ' ORDER BY c.id'
        rows = [dict(r) for r in con.execute(sql, args)] if con else self.rows(sql, args)
        for row in rows:
            row['recent_sends'] = row.pop('sends_now')
        return rows

    def job(self, job_id):
        job = self.one('SELECT * FROM jobs WHERE id=?', (job_id,))
        if not job:
            raise KeyError('작업을 찾을 수 없습니다.')
        job['request'] = json.loads(job['request'])
        job['results'] = json.loads(job['results'])
        job['steps'] = self.rows('SELECT * FROM steps WHERE job_id=? ORDER BY id', (job_id,))
        for step in job['steps']:
            step['input'] = json.loads(step['input'])
            step['output'] = json.loads(step['output']) if step['output'] else None
        job['deliveries'] = self.rows('SELECT * FROM deliveries WHERE job_id=? ORDER BY id', (job_id,))
        job['audit'] = self.rows('SELECT * FROM audit WHERE job_id=? ORDER BY id', (job_id,))
        return job

    def seed_customers(self):
        if self.one('SELECT COUNT(*) AS n FROM customers')['n']:
            return
        rng = random.Random(20260930)
        now = time.time()
        with self.connect() as con:
            for i in range(1, 241):
                row = {'id': f'C{i:04}', 'name': ['김', '이', '박', '최', '정', '강'][i % 6] + '＊' + ['준', '은', '현', '우', '연'][i % 5], 'segment': ['직장인', '자산관리형', '사회초년생', '생활금융형'][i % 4], 'balance': rng.randrange(1, 65) * 1000000, 'salary': rng.randrange(25, 90) * 100000, 'consent': int(i % 9 != 0), 'mydata': int(i % 3 != 0), 'risk_profile': int(i % 7 != 0), 'has_portfolio': int(i % 5 == 0), 'recent_sends': 3 if i % 13 == 0 else 0, 'recent_at': now, 'maturity_days': rng.choice([7, 14, 30, 90]), 'loan_balance': rng.choice([0, 30000000, 85000000]), 'card_spend': rng.randrange(2, 30) * 100000}
                if i <= 8:
                    row.update(balance=18000000 + i * 1000000, consent=1, mydata=1, risk_profile=1, has_portfolio=0, recent_sends=0, maturity_days=7, loan_balance=60000000)
                if i == 3:
                    row['mydata'] = 0
                if i == 4:
                    row['consent'] = 0
                if i == 5:
                    row['recent_sends'] = 3
                if i == 6:
                    row['balance'] = 450000
                con.execute('INSERT INTO customers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', tuple(row.values()))
