"""Synthetic preview data. Never inserted in the real evidence cache."""
import time
from .analysis import build_brief

def example_job():
    names=['Northstar','Kite','Marlow','Echo','Sable']
    players=[{'player_id':f'00000000-0000-4000-8000-{i:012d}','game_player_id':str(76561198000000001+i),'nickname':name} for i,name in enumerate(names)]
    roster=[p['game_player_id'] for p in players]
    reports=[]
    for match in range(4):
        rounds=[]
        for n in range(24):
            site='A' if n<12 else 'B'
            planted=n%12 < (1 if site=='A' else 10)
            rounds.append({'number':n+1,'ct_roster':roster,'ct_buy':'full','t_buy':'full','winner_side':'T' if planted else 'CT',
                'opening':[{'steam_id':p['game_player_id'],'name':p['nickname'],'side':'CT',
                            'place':['BombsiteA','Jungle','BombsiteB','Catwalk','SnipersNest'][i],
                            'zone':['A','A','B','B','MID'][i],'weapon':'awp' if i==4 else 'm4a1'} for i,p in enumerate(players)],
                'contacts':[{'site':site}],'plant_site':site if planted else None,'retake_attempted':planted})
        reports.append({'schema_version':1,'match_id':f'1-00000000-0000-4000-8000-{match:012d}','map':'de_mirage','played_at':time.time()-(match+1)*86400,
                        'source':{'kind':'synthetic_preview'},'rounds':rounds})
    stats={p['player_id']:{'map':{'matches':8,'adr':[82,77,62,73,89][i],'kd':[1.16,1.08,.88,1.02,1.24][i],'win_rate':50},
                             'overall':{'matches':30,'adr':79,'kd':1.1}} for i,p in enumerate(players)}
    return {'id':'preview','match_id':'SYNTHETIC PREVIEW','status':'ready','example':True,'map':'de_mirage','team_id':'your_team',
            'created_at':time.time(),'updated_at':time.time(),'elapsed_ms':0,'first_brief_ms':None,'opponent_name':'Example opponents',
            'brief':build_brief(players,reports,'de_mirage',stats),'errors':[],'teams':[]}
