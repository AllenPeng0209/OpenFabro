"""Source-bound hints for interactive differential routing, never design edits."""
import hashlib
import json
from collections import defaultdict
from . import buses,impedance

def hints(spec):
    out={'schema':1,'pairs':[],'issues':[]}
    if not spec.get('impedance') and not any(isinstance(p,dict) and p.get('pair') for c in spec.get('components',[]) for p in (c.get('pin_properties') or {}).values()):return out
    pin_nets={p:n['name'] for n in spec.get('nets',[]) for p in n.get('pins',[])}
    try:compiled=buses.compile(spec)
    except (ValueError,KeyError,TypeError) as error:
        named={pin_nets.get(c['ref']+'.'+pin) for c in spec.get('components',[]) for pin,p in (c.get('pin_properties') or {}).items() if isinstance(p,dict) and p.get('pair')}
        out['issues'].append({'severity':'error','nets':sorted(n for n in named if n),'message':str(error)})
        return out
    bus_by={b['id']:b for b in compiled['buses']};order={n['name']:i for i,n in enumerate(spec['nets'])};profiles={}
    for issue in compiled['issues']:
        out['issues'].append({**issue,'nets':bus_by.get(issue['bus_id'],{}).get('nets',[])})
    def pair_for(names):
        names=sorted(set(names),key=lambda n:order.get(n,len(order)))
        if len(names)!=2 or any(n not in order for n in names):return None
        key=tuple(names)
        return profiles.setdefault(key,{'id':hashlib.sha256(json.dumps(names).encode()).hexdigest()[:16],'nets':names,'ends':[],'polarity':{},'_roles':defaultdict(set),'_targets':set()})
    for group in compiled['groups']:
        if group['kind']!='diff':continue
        pair=pair_for(group['nets'])
        if not pair:continue
        if group.get('impedance_ohms') is not None:pair['_targets'].add(group['impedance_ohms'])
        for identifier in group.get('bus_ids',[group['bus_id']]):
            rows=[p for p in bus_by[identifier]['members'] if p['properties'].get('pair')==group['pair'] and p['net'] in pair['nets']]
            pins=[p['pin'] for p in rows]
            if pins and not any(e['pins']==pins for e in pair['ends']):pair['ends'].append({'id':identifier,'pins':pins})
            for p in rows:
                if p['properties'].get('polarity'):pair['_roles'][p['net']].add(p['properties']['polarity'])
    for manual in spec.get('impedance') or []:
        if not isinstance(manual,dict):continue
        entry=impedance.profiled(manual)
        if entry.get('kind')!='diff':continue
        pair=pair_for(entry.get('nets',[]))
        if not pair:continue
        if entry.get('ohms') is not None:pair['_targets'].add(entry['ohms'])
    for pair in profiles.values():
        for component in spec['components']:
            if any(any(p.split('.',1)[0]==component['ref'] for p in e['pins']) for e in pair['ends']):continue
            pins=[p for n in pair['nets'] for p in next(v for v in spec['nets'] if v['name']==n)['pins'] if p.split('.',1)[0]==component['ref']]
            if {pin_nets.get(p) for p in pins}!=set(pair['nets']):continue
            pair['ends'].append({'id':component['ref'],'pins':pins})
            for pin in pins:
                role=component.get('pin_properties',{}).get(pin.split('.',1)[1],{}).get('polarity')
                if role:pair['_roles'][pin_nets[pin]].add(role)
    partners=defaultdict(set)
    for names in profiles:
        for a,b in [names,names[::-1]]:partners[a].add(b)
    ambiguous={n for n,others in partners.items() if len(others)>1}
    if ambiguous:out['issues'].append({'severity':'error','nets':sorted(ambiguous),'message':'A differential net has more than one declared partner. Resolve the pair declarations before paired routing.'})
    clearance=float(spec.get('rules',{}).get('clearance_mm',.2));width=float(spec.get('rules',{}).get('track_mm',.25));board=spec['board']
    for names,pair in profiles.items():
        if ambiguous.intersection(names):continue
        roles=pair.pop('_roles');targets=pair.pop('_targets')
        if any(len(v)>1 for v in roles.values()) or len(roles)==2 and len(set(next(iter(v)) for v in roles.values()))!=2:
            out['issues'].append({'severity':'error','nets':list(names),'message':'Differential polarity disagrees between the pair endpoints.'});continue
        if len(targets)>1 or any(i['severity']=='error' and set(i.get('nets',[])).intersection(names) for i in out['issues']):continue
        pair['polarity']={n:next(iter(v)) for n,v in roles.items()};pair['width_mm']=width;pair['gap_mm']=clearance;pair['nominal_impedance_ohms']=next(iter(targets),None)
        if targets:
            entry=next((impedance.profiled(e) for e in spec.get('impedance') or [] if isinstance(e,dict) and set(e.get('nets',[]))==set(names)),{'kind':'diff','nets':list(names),'ohms':pair['nominal_impedance_ohms']})
            rule=impedance.design_rule(entry,int(board.get('layers',2)),float(board.get('thickness_mm') or 1.6),clearance,board)
            pair['gap_mm']=max(clearance,rule.get('gap_mm') or clearance)
            if rule.get('practical'):pair['width_mm']=rule['width_mm']
            pair['nominal_model']={'source':'IPC-2141 outer-layer estimate','practical':rule.get('practical',False),'calculated_width_mm':rule.get('width_mm'),'calculated_gap_mm':rule.get('gap_mm'),'note':rule.get('note')}
        out['pairs'].append(pair)
    return out
