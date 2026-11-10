from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import threading
import time
import uuid
from .analysis import build_brief, map_name, recent_stats
from .faceit import FaceitError, picked_map

class Jobs:
    def __init__(self,store,api,config,warmer=None):
        self.store,self.api,self.config,self.warmer=store,api,config,warmer
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='brief')
        self.io=ThreadPoolExecutor(max_workers=4,thread_name_prefix='faceit')
        self.jobs={}
        self.lock=threading.RLock()

    def start(self,match_id,team_id='',map_hint=None):
        key=(match_id,team_id,map_name(map_hint))
        with self.lock:
            for job in self.jobs.values():
                if job['_key']==key and time.time()-job['created_at']<12 and job['status']!='error':
                    return self.public(job)
            job={'id':str(uuid.uuid4()),'match_id':match_id,'status':'loading','created_at':time.time(),
                 'updated_at':time.time(),'elapsed_ms':0,'teams':[],'brief':None,'errors':[],
                 '_key':key,'team_id':team_id,'map':map_name(map_hint)}
            self.jobs[job['id']]=job
            if len(self.jobs)>50:
                for old in sorted(self.jobs.values(),key=lambda j:j['created_at'])[:-50]:
                    self.jobs.pop(old['id'],None)
            self.pool.submit(self.run,job)
            return self.public(job)

    def public(self,job):
        return copy.deepcopy({k:v for k,v in job.items() if not k.startswith('_')})

    def get(self,job_id):
        with self.lock:
            job=self.jobs.get(job_id)
            if not job:
                return None
            result=self.public(job)
            if job.get('_players') and job.get('map'):
                # Newly imported demos become visible without restarting the job.
                result['brief']=build_brief(job['_players'],self.evidence(job),job['map'],job.get('_stats'))
            return result

    def evidence(self,job):
        return self.store.reports(job.get('map'),before=job.get('as_of'),exclude_match=job['match_id'])

    def update(self,job,**values):
        with self.lock:
            job.update(values)
            job['updated_at']=time.time()
            job['elapsed_ms']=round((time.time()-job['created_at'])*1000)

    def run(self,job):
        try:
            match=self.api.match(job['match_id'])
            if match.get('game') not in (None,'cs2'):
                raise FaceitError('This match is not CS2.',400)
            teams=[{'id':key,'name':value.get('name') or value.get('nickname') or key,'players':value.get('roster',[])} for key,value in (match.get('teams') or {}).items()]
            self.update(job,teams=teams,match_status=match.get('status','UNKNOWN'))
            if str(match.get('status','')).upper()=='FINISHED':
                started=match.get('started_at')
                if not isinstance(started,(int,float)) or started<=0:
                    raise FaceitError('This completed match lacks a start timestamp, so a fair historical briefing cannot be reconstructed.',409)
                self.update(job,historical=True,as_of=started)
            chosen=job['team_id']
            nickname=str(self.config().get('nickname','')).casefold()
            if not chosen and nickname:
                chosen=next((t['id'] for t in teams if any(str(p.get('nickname','')).casefold()==nickname for p in t['players'])), '')
            if len(teams)!=2:
                raise FaceitError('Waiting for both teams to appear in the matchroom.',409)
            if not chosen or chosen not in [t['id'] for t in teams]:
                self.update(job,status='choose_team')
                return
            opponents=next(t for t in teams if t['id']!=chosen)
            selected=job['map'] or picked_map(match)
            self.update(job,team_id=chosen,opponent_name=opponents['name'],map=selected,_players=opponents['players'],_stats={})
            brief=build_brief(opponents['players'],self.evidence(job),selected)
            self.update(job,brief=brief,status='partial',first_brief_ms=round((time.time()-job['created_at'])*1000))
            if self.warmer and selected:
                self.warmer.schedule(opponents['players'],selected,job['match_id'],before=job.get('as_of'))
            futures={self.io.submit(self.api.stats,p.get('player_id',''),**({'before':job['as_of']} if job.get('as_of') else {})):p for p in opponents['players']}
            statistics={}
            errors=[]
            for future in as_completed(futures):
                p=futures[future]
                try:
                    data=future.result()
                    statistics[p['player_id']]={'overall':recent_stats(data.get('items',[]),before=job.get('as_of')),
                                               'map':recent_stats(data.get('items',[]),selected,before=job.get('as_of')) if selected else {}}
                except Exception as e:
                    errors.append(p.get('nickname','Player')+': '+str(e))
                brief=build_brief(opponents['players'],self.evidence(job),selected,statistics)
                self.update(job,_stats=statistics,brief=brief,errors=errors)
            self.update(job,status='ready' if selected else 'awaiting_map',brief=brief)
        except (FaceitError,ValueError) as e:
            self.update(job,status='error',error=str(e))
        except Exception:
            self.update(job,status='error',error='Could not build the briefing. Check the local helper console.')
