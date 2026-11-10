"""Extract compact evidence from completed CS2 demos with demoparser2.

    python -m server.demo_import match.dem --match-id 1-... --played-at ISO_DATE

The native parser is optional for running the app, required for new demo evidence.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import time
from .analysis import CLASSIFIER_VERSION, core_site, map_name, zone_for

def clean(value):
    if isinstance(value,dict):
        return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list):
        return [clean(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):
        return None
    if hasattr(value,'item'):
        return clean(value.item())
    return value

def records(frame):
    return clean(frame.to_dict('records'))

def identity(row,prefix=''):
    value=row.get(prefix+'steamid')
    if value is None:
        return ''
    if isinstance(value,float) and (not math.isfinite(value) or abs(value)>2**53):
        return ''  # A rounded 64-bit ID must never be attached to another player.
    return str(int(value)) if isinstance(value,(float,int)) else str(value)

def side(value):
    if value in (3,'CT','Counter-Terrorist','CounterTerrorist'):
        return 'CT'
    if value in (2,'T','TERRORIST','Terrorist'):
        return 'T'
    return None

def buy_type(values):
    """Explicit conservative threshold; not FACEIT's proprietary buy label."""
    if len(values)!=5 or any(v is None for v in values):
        return 'unknown'
    total=sum(values)
    return 'full' if total>=20000 else ('eco' if total<10000 else 'force')

def normalize_replay(map_id,match_id,played_at,freezes,ends,snapshots,damage,plants,tick_rate=64):
    """Pure transformation used by both the parser and regression fixtures."""
    rounds=[]
    freezes=sorted(freezes,key=lambda x:x['tick'])
    ends=sorted(ends,key=lambda x:x['tick'])
    for index,freeze in enumerate(freezes):
        start=int(freeze['tick'])
        next_start=int(freezes[index+1]['tick']) if index+1<len(freezes) else float('inf')
        end=next((e for e in ends if start<e['tick']<next_start),None)
        if not end:
            continue
        end_tick=end['tick']
        rows=[s for s in snapshots if start<=s['tick']<=end_tick]
        if not rows:
            continue
        by_tick={}
        for row in rows:
            by_tick.setdefault(row['tick'],[]).append(row)
        first_tick=min(by_tick)
        initial=by_tick[first_tick]
        ct_roster=sorted({identity(r) for r in initial if side(r.get('team_num'))=='CT' and identity(r)})
        t_roster=sorted({identity(r) for r in initial if side(r.get('team_num'))=='T' and identity(r)})
        if len(ct_roster)!=5 or len(t_roster)!=5:
            continue
        exchanges=[e for e in damage if start<e['tick']<=end_tick and side(e.get('attacker_team_num')) and side(e.get('user_team_num')) and side(e.get('attacker_team_num'))!=side(e.get('user_team_num'))]
        first_contact=min([e['tick'] for e in exchanges],default=end_tick)
        early=[r for r in rows if start+6*tick_rate<=r['tick']<=min(start+22*tick_rate,first_contact) and r.get('is_alive')]
        opening=[]
        for steam in ct_roster:
            observed=[r for r in early if identity(r)==steam]
            known=[r for r in observed if zone_for(map_id,r.get('last_place_name'))]
            if not known:
                continue
            place=Counter(r.get('last_place_name') for r in known).most_common(1)[0][0]
            sample=next(r for r in known if r.get('last_place_name')==place)
            opening.append({'steam_id':steam,'name':sample.get('name',''),'side':'CT','place':place,
                            'zone':zone_for(map_id,place),'weapon':Counter(str(r.get('active_weapon_name') or '') for r in known).most_common(1)[0][0]})
        contact_sites={}
        for e in exchanges:
            a=core_site(e.get('attacker_last_place_name'))
            b=core_site(e.get('user_last_place_name'))
            # Strict core-core contact avoids assigning an attack from vague proximity.
            if a and a==b:
                contact_sites.setdefault(a,{'site':a,'tick':e['tick']})
        planted=[p for p in plants if start<p['tick']<=end_tick]
        plant_site=None
        if planted:
            p=planted[0]
            plant_site=core_site(p.get('user_last_place_name'))
            if not plant_site and p.get('site') in ('A','B'):
                plant_site=p['site']
        def equips(team):
            return [r.get('current_equip_value') for r in initial if side(r.get('team_num'))==team]
        # A retake attempt needs CT damage contact at the planted core after planting.
        retake=bool(plant_site and any(e['tick']>planted[0]['tick'] and
                    (core_site(e.get('user_last_place_name'))==plant_site or core_site(e.get('attacker_last_place_name'))==plant_site)
                    for e in exchanges))
        rounds.append({'number':index+1,'ct_roster':ct_roster,'ct_buy':buy_type(equips('CT')),'t_buy':buy_type(equips('T')),
            'winner_side':side(end.get('winner')),'opening':opening,'contacts':list(contact_sites.values()),
            'plant_site':plant_site,'retake_attempted':retake})
    if not rounds:
        raise ValueError('No complete 5v5 rounds could be extracted. The replay may be incomplete or use an unsupported event format.')
    return {'schema_version':1,'match_id':match_id,'map':map_id,'played_at':played_at,
            'source':{'kind':'completed_demo','parser':'demoparser2','classifier_version':CLASSIFIER_VERSION},'rounds':rounds}

def parse_demo(path,match_id,played_at):
    try:
        from demoparser2 import DemoParser
    except ImportError:
        raise RuntimeError('Demo analysis needs demoparser2. Run Install-demo-support.cmd on Windows or Install-demo-support.command on Mac.')
    parser=DemoParser(str(path))
    header=parser.parse_header()
    selected=map_name(header.get('map_name'))
    if not selected:
        raise ValueError('This demo map is not supported: '+str(header.get('map_name')))
    freezes=records(parser.parse_event('round_freeze_end'))
    ends=records(parser.parse_event('round_end'))
    if not freezes or not ends:
        raise ValueError('Replay round events are missing. No position claims were added.')
    tick_rate=float(header.get('tick_rate') or header.get('tickrate') or 64)
    props=['team_num','is_alive','last_place_name','active_weapon_name','current_equip_value']
    # Sample buy-end and six early-round observations, avoiding full tick expansion.
    ticks=sorted({int(f['tick']+offset*tick_rate) for f in freezes for offset in (0,6,10,14,18,22)})
    snapshots=records(parser.parse_ticks(props,ticks=ticks))
    damage=records(parser.parse_event('player_hurt',player=['last_place_name','team_num']))
    plants=records(parser.parse_event('bomb_planted',player=['last_place_name']))
    report=normalize_replay(selected,match_id,played_at,freezes,ends,snapshots,damage,plants,tick_rate)
    report['source']['parser_version']=__import__('importlib.metadata',fromlist=['version']).version('demoparser2')
    return report

def validate_report(report):
    if not isinstance(report,dict) or report.get('schema_version')!=1 or not map_name(report.get('map')):
        raise ValueError('Unsupported evidence file.')
    from .faceit import match_id_from
    match_id_from(report.get('match_id'))
    date=report.get('played_at')
    if not isinstance(date,(int,float)) or not math.isfinite(date) or date>time.time()+300 or date<time.time()-30*86400:
        raise ValueError('Evidence must be from a completed match within the last 30 days.')
    if report.get('source',{}).get('kind')!='completed_demo':
        raise ValueError('Only completed-demo evidence can enter the live cache.')
    rounds=report.get('rounds')
    if not isinstance(rounds,list) or not 1<=len(rounds)<=150:
        raise ValueError('Invalid evidence round count.')
    numbers=set()
    for rnd in rounds:
        if not isinstance(rnd,dict) or not isinstance(rnd.get('number'),int):
            raise ValueError('Invalid evidence round.')
        if rnd['number'] in numbers:
            raise ValueError('Duplicate evidence round.')
        numbers.add(rnd['number'])
        if len(set(rnd.get('ct_roster',[])))!=5 or any(not re_steam(x) for x in rnd['ct_roster']):
            raise ValueError('A demo round needs five distinct Steam IDs.')
        if rnd.get('winner_side') not in ('CT','T',None):
            raise ValueError('Invalid winner side.')
        if rnd.get('plant_site') not in ('A','B',None):
            raise ValueError('Invalid bombsite.')
        if rnd.get('ct_buy') not in ('full','force','eco','unknown') or rnd.get('t_buy') not in ('full','force','eco','unknown'):
            raise ValueError('Invalid buy classification.')
        if not isinstance(rnd.get('opening',[]),list) or len(rnd.get('opening',[]))>5:
            raise ValueError('Invalid positions.')
        for p in rnd.get('opening',[]):
            if p.get('steam_id') not in rnd['ct_roster'] or p.get('zone')!=zone_for(report['map'],p.get('place')):
                raise ValueError('Position evidence does not match the conservative map classifier.')
        if not isinstance(rnd.get('contacts',[]),list) or len(rnd.get('contacts',[]))>2 or any(c.get('site') not in ('A','B') for c in rnd.get('contacts',[])):
            raise ValueError('Invalid site contacts.')
    return report

def re_steam(value):
    import re
    return isinstance(value,str) and bool(re.fullmatch(r'7656119[0-9]{10}',value))

def main():
    if sys.platform != 'win32':
        try:
            os.nice(10)
        except OSError:
            pass
    parser=argparse.ArgumentParser()
    parser.add_argument('demo')
    parser.add_argument('--match-id',required=True)
    parser.add_argument('--played-at',required=True,help='ISO date/time or Unix seconds from the completed match metadata')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        played=float(args.played_at)
    except ValueError:
        played=datetime.fromisoformat(args.played_at.replace('Z','+00:00')).timestamp()
    report=validate_report(parse_demo(Path(args.demo),args.match_id,played))
    Path(args.output).write_text(json.dumps(report,allow_nan=False),encoding='utf-8')
    print('Extracted '+str(len(report['rounds']))+' rounds on '+report['map']+'.')

if __name__=='__main__':
    main()
