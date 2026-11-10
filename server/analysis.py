"""Evidence-based summaries. No inferred site assignments from scoreboard stats."""
from collections import Counter
from datetime import datetime, timezone
import math
import re

MAPS = ('de_mirage', 'de_dust2', 'de_inferno', 'de_ancient', 'de_anubis', 'de_nuke', 'de_train', 'de_overpass', 'de_vertigo', 'de_cache')
CLASSIFIER_VERSION = 1

def map_name(value):
    value = str(value or '').lower().strip().replace(' ', '').replace('dustii', 'dust2')
    if not value.startswith('de_'):
        value = 'de_' + value
    return value if value in MAPS else None

def zone_for(map_id, place):
    """Conservative nav-place classification. Unknown places stay unknown.

    MID means central position, not that a player is a permanent rotator.
    Core bombsites use explicit engine labels; support aliases are map-specific.
    """
    key = re.sub(r'[^a-z0-9]', '', str(place or '').lower())
    generic = {'bombsitea': 'A', 'bombsiteb': 'B'}
    if key in generic:
        return generic[key]
    aliases = {
        'de_mirage': {'aramp':'A','palaceinterior':'A','palace':'A','ticketbooth':'A','jungle':'A', 'stairs':'A', 'catwalk':'B','kitchen':'B','market':'B','backofb':'B','apartments':'B','middle':'MID','topofmid':'MID','connector':'MID','snipersnest':'MID'},
        'de_dust2': {'longa':'A','extendeda':'A','shortstairs':'A','catwalk':'A','backofb':'B','btunnels':'B','upperbtunnels':'B','middle':'MID','middledoors':'MID','lowerbtunnel':'MID'},
        'de_inferno': {'pit':'A','balcony':'A','apartments':'A','graveyard':'A','library':'A','banana':'B','construction':'B','middle':'MID','secondmid':'MID'},
        'de_ancient': {'donut':'A','temple':'A','cave':'B','ramp':'B','middle':'MID'},
    }
    return aliases.get(map_id, {}).get(key)

def core_site(place):
    return {'bombsitea':'A','bombsiteb':'B'}.get(re.sub(r'[^a-z0-9]', '', str(place or '').lower()))

def wilson(successes, total):
    if not total:
        return None
    z = 1.96
    p = successes / total
    d = 1 + z*z/total
    centre = (p + z*z/(2*total)) / d
    delta = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / d
    return [round(max(0, centre-delta), 4), round(min(1, centre+delta), 4)]

def finite_number(value):
    try:
        n = float(str(value).rstrip('%'))
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None

def recent_stats(items, selected_map=None):
    """Known field names only. A generic sniper statistic is never called AWP."""
    rows = []
    for item in items:
        row = item.get('stats', item)
        if selected_map and map_name(row.get('Map')) != selected_map:
            continue
        rows.append(row)
    def avg(key):
        values = [finite_number(r.get(key)) for r in rows]
        values = [v for v in values if v is not None]
        return round(sum(values)/len(values), 2) if values else None
    wins = [finite_number(r.get('Result')) for r in rows]
    wins = [v for v in wins if v in (0, 1)]
    return {'matches':len(rows), 'adr':avg('ADR'), 'kills':avg('Kills'),
            'kd':avg('K/D Ratio'), 'win_rate':round(100*sum(wins)/len(wins)) if wins else None,
            'sniper_kills':avg('Sniper Kills'), 'awp_kills':avg('AWP Kills')}

def position_profile(steam_id, reports, selected_map):
    observations = []
    demos = set()
    dates = []
    awp_rounds = 0
    for report in reports:
        if report['map'] != selected_map:
            continue
        for rnd in report['rounds']:
            if rnd.get('ct_buy') != 'full' or rnd.get('t_buy') != 'full':
                continue
            player = next((p for p in rnd.get('opening', []) if p['steam_id'] == steam_id and p.get('side') == 'CT'), None)
            if not player or player.get('zone') not in ('A','B','MID'):
                continue
            observations.append(player)
            demos.add(report['match_id'])
            dates.append(report['played_at'])
            awp_rounds += str(player.get('weapon','')).lower() in ('awp','weapon_awp')
    if not observations:
        return {'zone':None, 'rounds':0, 'matches':0, 'label':'No position evidence', 'confidence':'unavailable', 'positions':[]}
    zones = Counter(p['zone'] for p in observations)
    places = Counter(p.get('place') or p['zone'] for p in observations)
    zone, count = zones.most_common(1)[0]
    total = len(observations)
    share = count / total
    confidence = 'moderate' if total >= 20 and len(demos) >= 3 and share >= .65 else 'limited'
    label = ('Usually '+zone if share >= .65 else 'Varies across positions')
    return {'zone':zone if share >= .65 else None,'rounds':total,'matches':len(demos),'share':round(share*100),
            'label':label,'confidence':confidence,'awp_rounds':awp_rounds,'newest':max(dates),
            'positions':[{'place':p,'rounds':n} for p,n in places.most_common(3)]}

def site_summary(reports, roster, selected_map):
    """Only exact five-player lineups produce team site comparisons.

    Denominator is contact-defined attacks, not every round or only plants.
    A contact requires both participants in the named bombsite core.
    These observational outcomes are not causal player ratings.
    """
    expected = set(roster)
    out = {s:{'site':s,'attacks':0,'plants_allowed':0,'rounds_won':0,'retake_attempts':0,'retakes_won':0,'matches':set()} for s in ('A','B')}
    seen = set()
    shared_matches = set()
    if len(expected) != 5:
        return _finalize_sites(out), [], 0
    for report in reports:
        if report['map'] != selected_map:
            continue
        for rnd in report['rounds']:
            if set(rnd.get('ct_roster', [])) != expected:
                continue
            shared_matches.add(report['match_id'])
            if rnd.get('ct_buy') != 'full' or rnd.get('t_buy') != 'full':
                continue
            # One observation per round; ambiguous attacks on both sites excluded.
            sites = set(c['site'] for c in rnd.get('contacts',[]) if c.get('site') in ('A','B'))
            plant = rnd.get('plant_site')
            if plant in ('A','B'):
                sites.add(plant)
            if len(sites) != 1:
                continue
            site = sites.pop()
            key = (report['match_id'],rnd['number'])
            if key in seen:
                continue
            seen.add(key)
            result = out[site]
            result['attacks'] += 1
            result['plants_allowed'] += plant == site
            result['rounds_won'] += rnd.get('winner_side') == 'CT'
            result['matches'].add(report['match_id'])
            if plant == site and rnd.get('retake_attempted'):
                result['retake_attempts'] += 1
                result['retakes_won'] += rnd.get('winner_side') == 'CT'
    sites = _finalize_sites(out)
    findings = []
    a,b = sites
    enough = all(s['attacks'] >= 20 and s['matches'] >= 3 for s in sites)
    if enough:
        weaker = None
        if a['plant_interval'][0] > b['plant_interval'][1]:
            weaker = a
        elif b['plant_interval'][0] > a['plant_interval'][1]:
            weaker = b
        if weaker:
            findings.append({'type':'site','title':weaker['site']+' is worth testing first',
                'text':'This exact lineup allowed plants more often there in comparable full-buy contact rounds. Historical observation; verify their current setup.',
                'confidence':'moderate', 'evidence':str(weaker['plants_allowed'])+'/'+str(weaker['attacks'])+' plants allowed across '+str(weaker['matches'])+' matches.'})
    return sites, findings, len(shared_matches)

def _finalize_sites(out):
    results=[]
    for site in out.values():
        site = dict(site)
        site['matches']=len(site['matches'])
        n=site['attacks']
        site['plant_rate']=round(100*site['plants_allowed']/n) if n else None
        site['hold_rate']=round(100*(n-site['plants_allowed'])/n) if n else None
        site['win_rate']=round(100*site['rounds_won']/n) if n else None
        site['retake_rate']=round(100*site['retakes_won']/site['retake_attempts']) if site['retake_attempts'] else None
        site['plant_interval']=wilson(site['plants_allowed'],n)
        site['confidence']='moderate' if n >= 20 and site['matches'] >= 3 else ('limited' if n else 'unavailable')
        results.append(site)
    return results

def projected_site_summary(reports, prepared, selected_map):
    """Pool earlier lineups only when current players have repeatable site evidence.

    These are contextual historical outcomes, not a measured defence by the new
    five-player team, and are never assigned calibrated probabilities.
    """
    anchors={s:{p['steam_id'] for p in prepared if p['position'].get('zone')==s and p['position'].get('confidence')=='moderate'} for s in ('A','B')}
    out={s:{'site':s,'attacks':0,'plants_allowed':0,'rounds_won':0,'retake_attempts':0,'retakes_won':0,'matches':set()} for s in ('A','B')}
    seen=set()
    for report in reports:
        if report['map']!=selected_map:
            continue
        for rnd in report['rounds']:
            if rnd.get('ct_buy')!='full' or rnd.get('t_buy')!='full':
                continue
            attacked={c['site'] for c in rnd.get('contacts',[]) if c.get('site') in ('A','B')}
            if rnd.get('plant_site') in ('A','B'):
                attacked.add(rnd['plant_site'])
            if len(attacked)!=1:
                continue
            site=next(iter(attacked))
            assigned={p['steam_id'] for p in rnd.get('opening',[]) if p.get('zone')==site and p.get('side')=='CT'}
            if not (assigned & anchors[site]):
                continue
            key=(report['match_id'],rnd['number'],site)
            if key in seen:
                continue
            seen.add(key)
            result=out[site]
            result['attacks']+=1
            result['plants_allowed']+=rnd.get('plant_site')==site
            result['rounds_won']+=rnd.get('winner_side')=='CT'
            result['matches'].add(report['match_id'])
            if rnd.get('plant_site')==site and rnd.get('retake_attempted'):
                result['retake_attempts']+=1
                result['retakes_won']+=rnd.get('winner_side')=='CT'
    sites=_finalize_sites(out)
    for site in sites:
        site['basis']='prior_lineups'
        site['defenders']=[p['nickname'] for p in prepared if p['steam_id'] in anchors[site['site']]]
    findings=[]
    if all(s['attacks']>=20 and s['matches']>=3 for s in sites):
        a,b=sites
        weaker=a if a['plant_interval'][0]>b['plant_interval'][1] else (b if b['plant_interval'][0]>a['plant_interval'][1] else None)
        if weaker:
            findings.append({'type':'site_projected','title':weaker['site']+' may be worth an early test',
                'text':'Projected from prior lineups where these likely defenders played this site. Plant concessions were more frequent there. Different teammates and opponents can change the result; confirm the current setup.',
                'confidence':'limited projection',
                'evidence':str(weaker['plants_allowed'])+'/'+str(weaker['attacks'])+' plants allowed across '+str(weaker['matches'])+' prior matches. Not a measured defence by this lineup.'})
    return sites,findings

def build_brief(players, reports, selected_map, stats=None):
    stats = stats or {}
    roster=[str(p.get('game_player_id') or p.get('steam_id') or '') for p in players]
    prepared=[]
    for p,steam in zip(players,roster):
        profile=position_profile(steam,reports,selected_map) if selected_map and steam else {'zone':None,'rounds':0,'matches':0,'confidence':'unavailable','label':'No position evidence','positions':[]}
        prepared.append({'player_id':p.get('player_id',''),'steam_id':steam,'nickname':p.get('nickname','Unknown'),
                         'position':profile,'stats':stats.get(p.get('player_id'),{})})
    sites,findings,shared = site_summary(reports,roster,selected_map) if selected_map else ([],[],0)
    for site in sites:
        site['basis']='exact_lineup'
    if selected_map and not findings and not all(s['attacks']>=20 and s['matches']>=3 for s in sites):
        projected,projection_findings=projected_site_summary(reports,prepared,selected_map)
        if any(s['attacks'] for s in projected):
            sites=projected
            findings=projection_findings
    coverage=sum(p['position']['rounds'] > 0 for p in prepared)
    if not findings:
        findings=[{'type':'coverage','title':'Site advantage is not established',
            'text':('Individual position tendencies are available. The available site samples do not establish a reliable advantage.' if coverage else 'Recent completed demos are needed to identify usual positions and compare site defence.'),
            'confidence':'unavailable','evidence':str(coverage)+'/'+str(len(players))+' players with position evidence.'}]
    if selected_map:
        candidates=[p for p in prepared if p['position'].get('rounds',0)>=10 and p['position'].get('awp_rounds',0)/p['position']['rounds'] >= .3]
        if candidates:
            p=max(candidates,key=lambda p:p['position']['awp_rounds']/p['position']['rounds'])
            findings.append({'type':'awp','title':p['nickname']+' frequently holds AWP early on CT',
                'text':'Sampled active weapon, rather than generic sniper kills. Position choices may change in this match.',
                'confidence':p['position']['confidence'],'evidence':str(p['position']['awp_rounds'])+'/'+str(p['position']['rounds'])+' classified full-buy opening rounds.'})
    return {'map':selected_map,'players':prepared,'sites':sites,'findings':findings[:3],
            'coverage':coverage,'total_players':len(players),'shared_matches':shared,
            'method':'Early CT positions from completed demos; full buys on both sides only. Exact-lineup site history and projections from prior lineups are labelled separately. Prior-lineup results depend on teammates and opposition and do not establish individual ability. Contact-defined attacks exclude ambiguous two-site rounds. Confidence describes evidence coverage, not a calibrated probability.'}
