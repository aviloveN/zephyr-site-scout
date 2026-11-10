import time
from server.example import example_job

ROSTER=[str(76561198000000001+i) for i in range(5)]
MATCH='1-11111111-2222-4333-8444-555555555555'

def evidence(index=1,a_plants=1,b_plants=10):
    rounds=[]
    for number in range(24):
        site='A' if number<12 else 'B'
        planted=number%12 < (a_plants if site=='A' else b_plants)
        rounds.append({'number':number+1,'ct_roster':ROSTER,'ct_buy':'full','t_buy':'full','winner_side':'T' if planted else 'CT',
            'opening':[{'steam_id':steam,'name':'Player '+str(i),'side':'CT','place':['BombsiteA','Jungle','BombsiteB','Catwalk','SnipersNest'][i],
                        'zone':['A','A','B','B','MID'][i],'weapon':'awp' if i==4 else 'm4a1'} for i,steam in enumerate(ROSTER)],
            'contacts':[{'site':site}],'plant_site':site if planted else None,'retake_attempted':planted})
    return {'schema_version':1,'match_id':f'1-00000000-0000-4000-8000-{index:012d}','map':'de_mirage','played_at':time.time()-index*3600,
            'source':{'kind':'completed_demo'},'rounds':rounds}

class FakeFaceit:
    def key_getter(self):return 'fixture-key'
    def match(self,match_id):
        return {'match_id':match_id,'game':'cs2','status':'READY','voting':{'map':{'pick':['de_mirage']}},
            'teams':{'faction1':{'name':'Your team','roster':[{'player_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','nickname':'Sonu','game_player_id':'76561198999999999'}]},
                     'faction2':{'name':'Fixture opponents','roster':[{'player_id':f'00000000-0000-4000-8000-{i:012d}','game_player_id':steam,'nickname':'Player '+str(i)} for i,steam in enumerate(ROSTER)]}}}
    def stats(self,player_id):
        return {'items':[{'stats':{'Map':'de_mirage','ADR':'82.3','K/D Ratio':'1.2','Kills':'20','Result':'1'}}]}
