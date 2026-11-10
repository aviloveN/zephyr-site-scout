import json
import sqlite3
import threading
import time

class Store:
    def __init__(self, path):
        self.db=sqlite3.connect(str(path),check_same_thread=False)
        self.lock=threading.RLock()
        with self.db:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS reports (match_id TEXT PRIMARY KEY, map TEXT NOT NULL, played_at REAL NOT NULL, value TEXT NOT NULL)')
            self.db.execute('CREATE INDEX IF NOT EXISTS report_map_date ON reports(map,played_at)')

    def cache_get(self,key):
        with self.lock:
            row=self.db.execute('SELECT value FROM cache WHERE key=? AND expires>?',(key,time.time())).fetchone()
            return json.loads(row[0]) if row else None

    def cache_set(self,key,value,ttl):
        with self.lock,self.db:
            self.db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,json.dumps(value,allow_nan=False),time.time()+ttl))

    def put_report(self,report):
        with self.lock,self.db:
            self.db.execute('INSERT OR REPLACE INTO reports VALUES(?,?,?,?)',(report['match_id'],report['map'],report['played_at'],json.dumps(report,allow_nan=False)))
            self.db.execute('DELETE FROM reports WHERE played_at < ?',(time.time()-30*86400,))
            self.db.execute('DELETE FROM cache WHERE expires < ?',(time.time(),))

    def reports(self,map_id=None,before=None,exclude_match=None):
        with self.lock:
            clauses=['played_at>?']
            params=[time.time()-30*86400]
            if map_id:
                clauses.append('map=?');params.append(map_id)
            if before is not None:
                clauses.append('played_at<?');params.append(before)
            if exclude_match:
                clauses.append('match_id!=?');params.append(exclude_match)
            rows=self.db.execute('SELECT value FROM reports WHERE '+' AND '.join(clauses)+' ORDER BY played_at DESC LIMIT 200',params).fetchall()
            return [json.loads(r[0]) for r in rows]

    def has_report(self,match_id):
        with self.lock:
            return bool(self.db.execute('SELECT 1 FROM reports WHERE match_id=? AND played_at>?',(match_id,time.time()-30*86400)).fetchone())

    def counts(self):
        reports=self.reports()
        players=set()
        for report in reports:
            for rnd in report['rounds']:
                players.update(rnd.get('ct_roster',[]))
        return {'demos':len(reports),'players':len(players)}
