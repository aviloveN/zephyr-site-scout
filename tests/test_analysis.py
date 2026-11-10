import copy
import math
import tempfile
import time
import unittest
from pathlib import Path
from server.analysis import build_brief,map_name,recent_stats,site_summary,position_profile,wilson,zone_for
from server.demo_import import normalize_replay,validate_report,identity,buy_type
from server.faceit import Faceit,match_id_from,picked_map
from server.jobs import Jobs
from server.storage import Store
from server.warmer import Warmer,approved_url
from tests.fixtures import ROSTER,MATCH,evidence,FakeFaceit

class AnalysisTests(unittest.TestCase):
    def test_map_normalization(self):
        self.assertEqual(map_name('Dust II'),'de_dust2')
        self.assertIsNone(map_name('../../etc/passwd'))
    def test_conservative_map_zones(self):
        self.assertEqual(zone_for('de_ancient','Donut'),'A')
        self.assertEqual(zone_for('de_mirage','Connector'),'MID')
        self.assertIsNone(zone_for('de_nuke','Lobby'))
    def test_positions_require_repeated_matches(self):
        report=evidence()
        profile=position_profile(ROSTER[2],[report],'de_mirage')
        self.assertEqual(profile['zone'],'B');self.assertEqual(profile['confidence'],'limited')
        profile=position_profile(ROSTER[2],[evidence(i) for i in (1,2,3)],'de_mirage')
        self.assertEqual(profile['confidence'],'moderate')
    def test_low_economy_excluded(self):
        report=evidence()
        for rnd in report['rounds']:rnd['ct_buy']='eco'
        self.assertEqual(position_profile(ROSTER[0],[report],'de_mirage')['rounds'],0)
        sites,findings,_=site_summary([report],ROSTER,'de_mirage')
        self.assertEqual(sum(s['attacks'] for s in sites),0);self.assertFalse(findings)
    def test_exact_lineup_required(self):
        report=evidence();roster=ROSTER[:-1]+['76561198000000999']
        sites,findings,shared=site_summary([report],roster,'de_mirage')
        self.assertFalse(findings);self.assertEqual(shared,0);self.assertEqual(sites[0]['attacks'],0)
    def test_large_supported_site_difference(self):
        sites,findings,shared=site_summary([evidence(i) for i in (1,2,3)],ROSTER,'de_mirage')
        self.assertEqual(shared,3);self.assertEqual(sites[0]['attacks'],36)
        self.assertEqual(findings[0]['title'],'B is worth testing first')
    def test_small_difference_does_not_make_recommendation(self):
        _,findings,_=site_summary([evidence(i,5,6) for i in (1,2,3)],ROSTER,'de_mirage')
        self.assertFalse(findings)
    def test_ambiguous_site_round_excluded(self):
        report=evidence();report['rounds'][0]['contacts']=[{'site':'A'},{'site':'B'}]
        sites,_,_=site_summary([report],ROSTER,'de_mirage')
        self.assertEqual(sites[0]['attacks'],11)
    def test_denominator_includes_failed_attacks(self):
        sites,_,_=site_summary([evidence()],ROSTER,'de_mirage')
        self.assertEqual(sites[0]['attacks'],12);self.assertEqual(sites[0]['plants_allowed'],1)
    def test_duplicate_reports_do_not_inflate_site_samples(self):
        report=evidence();sites,_,_=site_summary([report,report],ROSTER,'de_mirage')
        self.assertEqual(sites[0]['attacks'],12)
    def test_no_data_is_not_zero_percent(self):
        sites,_,_=site_summary([],ROSTER,'de_mirage')
        self.assertIsNone(sites[0]['hold_rate']);self.assertIsNone(sites[0]['retake_rate'])
    def test_sniper_is_not_mislabeled_awp(self):
        stats=recent_stats([{'stats':{'Map':'Mirage','Sniper Kills':'8','ADR':'nan'}}],'de_mirage')
        self.assertEqual(stats['sniper_kills'],8);self.assertIsNone(stats['awp_kills']);self.assertIsNone(stats['adr'])
    def test_stats_map_filter(self):
        self.assertEqual(recent_stats([{'stats':{'Map':'Inferno'}}],'de_mirage')['matches'],0)
    def test_historical_stats_exclude_target_future_and_undated_rows(self):
        before=1794000000
        rows=[{'stats':{'Map':'Mirage','Match Finished At':(before-100)*1000,'Kills':'17'}},
              {'stats':{'Map':'Mirage','Match Finished At':before*1000,'Kills':'99'}},
              {'stats':{'Map':'Mirage','Match Finished At':(before+100)*1000,'Kills':'99'}},
              {'stats':{'Map':'Mirage','Kills':'99'}}]
        stats=recent_stats(rows,'de_mirage',before=before)
        self.assertEqual(stats['matches'],1);self.assertEqual(stats['kills'],17)
    def test_bad_dates_or_duplicate_rounds_rejected(self):
        report=evidence();report['played_at']=time.time()+86400
        with self.assertRaises(ValueError):validate_report(report)
        report=evidence();report['rounds'].append(report['rounds'][0])
        with self.assertRaises(ValueError):validate_report(report)
    def test_preview_cannot_enter_live_cache(self):
        report=evidence();report['source']['kind']='synthetic_preview'
        with self.assertRaises(ValueError):validate_report(report)
    def test_valid_report(self):
        self.assertEqual(len(validate_report(evidence())['rounds']),24)
    def test_precision_loss_in_identity_rejected(self):
        self.assertEqual(identity({'steamid':float(76561198000000001)}),'')
    def test_url_allowlist(self):
        self.assertTrue(approved_url('https://demos.faceit.net/example.dem.gz'))
        for url in ['http://127.0.0.1/test','https://faceit.net.evil.com/a','https://faceit.net@evil.com/a','https://evil.com/a','file:///etc/passwd']:
            self.assertFalse(approved_url(url))
    def test_match_links(self):
        self.assertEqual(match_id_from('https://www.faceit.com/en/cs2/room/'+MATCH+'/scoreboard'),MATCH)
        with self.assertRaises(ValueError):match_id_from('https://evil.com')
    def test_picked_map_is_not_pool_guess(self):
        self.assertIsNone(picked_map({'voting':{'map':{'pick':['de_mirage','de_inferno']}}}))
        self.assertEqual(picked_map({'voting':{'map':{'pick':['de_mirage']}}}),'de_mirage')
    def test_confidence_intervals(self):
        self.assertIsNone(wilson(0,0));self.assertGreater(wilson(0,10)[1],0)
    def test_new_lineup_projection_is_explicitly_labelled(self):
        players=FakeFaceit().match(MATCH)['teams']['faction2']['roster']
        players[-1]['game_player_id']='76561198000000999'
        brief=build_brief(players,[evidence(i) for i in (1,2,3)],'de_mirage')
        self.assertEqual(brief['shared_matches'],0)
        self.assertEqual(brief['findings'][0]['type'],'site_projected')
        self.assertEqual(brief['sites'][0]['basis'],'prior_lineups')
    def test_single_match_cannot_produce_projected_site_advantage(self):
        players=FakeFaceit().match(MATCH)['teams']['faction2']['roster'];players[-1]['game_player_id']='76561198000000999'
        brief=build_brief(players,[evidence()],'de_mirage')
        self.assertEqual(brief['findings'][0]['type'],'coverage')

class ReplayTests(unittest.TestCase):
    def test_round_extraction_ignores_late_rotation(self):
        snapshots=[]
        for tick in [100,484,740,996,1252,1508]:
            for i in range(10):
                snapshots.append({'tick':tick,'steamid':str(76561198000000001+i),'team_num':3 if i<5 else 2,'is_alive':True,
                    'last_place_name':'BombsiteA' if tick<1252 else 'BombsiteB','active_weapon_name':'m4a1','current_equip_value':4500})
        report=normalize_replay('de_mirage',MATCH,time.time()-3600,[{'tick':100}],[{'tick':4000,'winner':3}],snapshots,
            [{'tick':1200,'attacker_team_num':2,'user_team_num':3,'attacker_last_place_name':'BombsiteA','user_last_place_name':'BombsiteA'}],[])
        self.assertEqual(report['rounds'][0]['opening'][0]['zone'],'A')
        self.assertEqual(report['rounds'][0]['contacts'][0]['site'],'A')
        self.assertEqual(report['rounds'][0]['ct_buy'],'full')
    def test_unknown_equipment_is_not_full_buy(self):
        self.assertEqual(buy_type([None]*5),'unknown')

class StorageAndJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'cache.sqlite3')
    def tearDown(self):
        self.store.db.close();self.tmp.cleanup()
    def test_cache_expires(self):
        self.store.cache_set('x',{'a':1},-1);self.assertIsNone(self.store.cache_get('x'))
    def test_store_deduplicates_demos(self):
        report=evidence();self.store.put_report(report);self.store.put_report(report)
        self.assertEqual(self.store.counts()['demos'],1)
    def test_evidence_cutoff_and_target_exclusion(self):
        older=evidence(1);future=evidence(2);target=evidence(3)
        before=time.time()-1800
        older['played_at']=before-100;future['played_at']=before+100
        target['played_at']=before-200;target['match_id']=MATCH
        for report in (older,future,target):self.store.put_report(report)
        result=self.store.reports('de_mirage',before=before,exclude_match=MATCH)
        self.assertEqual([r['match_id'] for r in result],[older['match_id']])
    def test_historical_job_is_held_out(self):
        before=time.time()-1800
        class HistoricalApi(FakeFaceit):
            def match(self,match_id):
                m=super().match(match_id);m.update(status='FINISHED',started_at=before);return m
            def stats(self,player_id,before=None):
                return {'items':[{'stats':{'Map':'de_mirage','Match Finished At':(before-100)*1000,'Kills':'17'}},
                                 {'stats':{'Map':'de_mirage','Match Finished At':(before+100)*1000,'Kills':'99'}}]}
        self.store.put_report(evidence(1))
        later=evidence(2);later['played_at']=before+100;self.store.put_report(later)
        jobs=Jobs(self.store,HistoricalApi(),lambda:{'nickname':'Sonu'})
        job=jobs.start(MATCH);jobs.pool.shutdown(wait=True);jobs.io.shutdown(wait=True)
        result=jobs.get(job['id'])
        self.assertTrue(result['historical']);self.assertEqual(result['as_of'],before)
        self.assertEqual(result['brief']['players'][0]['position']['rounds'],24)
        self.assertEqual(result['brief']['players'][0]['stats']['map']['kills'],17)
    def test_history_and_stats_use_correct_timestamp_units(self):
        api=Faceit(self.store,lambda:'test')
        paths=[]
        api.get=lambda path,ttl: paths.append(path) or {}
        player='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        api.stats(player,before=1794000000);api.history(player,before=1794000000)
        self.assertIn('to=1793999999999',paths[0]);self.assertIn('to=1793999999',paths[1])
    def test_demo_warmer_accepts_actual_lowercase_history_status(self):
        old=evidence(1);before=time.time()-1800
        class HistoryApi:
            def history(self,player_id,before=None):
                return {'items':[{'match_id':old['match_id'],'status':'finished','finished_at':old['played_at']}]}
            def match(self,match_id):
                return {'status':'FINISHED','finished_at':old['played_at'],'voting':{'map':{'pick':['de_mirage']}},'demo_url':['https://demos.faceit.net/test.dem.gz']}
        warmer=Warmer(self.store,HistoryApi(),lambda:{},Path.cwd(),Path(self.tmp.name))
        imports=[];warmer.download_and_import=lambda url,mid,at:imports.append(mid)
        warmer.warm_player({'player_id':'fixture','nickname':'Player'},'de_mirage',MATCH,('fixture','de_mirage',before),before)
        self.assertEqual(imports,[old['match_id']]);warmer.pool.shutdown()
    def test_positions_available_before_all_stats_finish(self):
        class SlowApi(FakeFaceit):
            def stats(self,player):time.sleep(.2);return super().stats(player)
        self.store.put_report(evidence())
        jobs=Jobs(self.store,SlowApi(),lambda:{'nickname':'Sonu'})
        job=jobs.start(MATCH)
        time.sleep(.08)
        first=jobs.get(job['id'])
        self.assertEqual(first['status'],'partial');self.assertEqual(first['brief']['coverage'],5)
        jobs.pool.shutdown(wait=True);jobs.io.shutdown(wait=True)
        final=jobs.get(job['id']);self.assertEqual(final['status'],'ready');self.assertGreater(final['brief']['players'][0]['stats']['map']['matches'],0)
    def test_unknown_user_must_pick_team(self):
        jobs=Jobs(self.store,FakeFaceit(),lambda:{})
        job=jobs.start(MATCH);jobs.pool.shutdown(wait=True);jobs.io.shutdown(wait=True)
        self.assertEqual(jobs.get(job['id'])['status'],'choose_team')

if __name__=='__main__':unittest.main()
