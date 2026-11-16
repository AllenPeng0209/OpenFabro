"""Reviewable interface metadata from real symbol names, never net-name guesses."""
from __future__ import annotations

import copy
import math
import re
from collections import defaultdict


def catalog():
    rows=[]
    for name in ('USB A','USB B','USB C','HDMI','PCIe x1','PCIe x2','PCIe x4','PCIe x8','PCIe x16','MIPI CSI','MIPI DSI','DDR3','DDR4'):
        family='USB' if name.startswith('USB') else 'PCIe' if name.startswith('PCIe') else name
        rows.append({'part_type':name,'bus_type':family,
                     'differential_ohms':90 if family=='USB' else 85 if family=='PCIe' else 100,
                     'single_ohms':50,'clock_ohms':100,
                     'basis':'Editable starting targets; verify the device/board design guide. No tolerance or timing limit is inferred.',
                     'scope':'D-PHY differential lanes' if name.startswith('MIPI') else 'Named data/strobe/clock lanes' if name.startswith('DDR') else 'Named differential lanes'})
    return rows


def profile(value):
    if not isinstance(value,str) or len(value)>100:raise ValueError('Choose a bounded Part Type.')
    key=re.sub(r'[\s_-]+','',value).casefold()
    for row in catalog():
        if re.sub(r'\s+','',row['part_type']).casefold()==key:return row
    raise ValueError('Choose a supported interface Part Type.')


def _pair(group,role,polarity,target):
    return {'bus_group':group,'pair':group+'_'+role,'pair_role':role,'polarity':polarity,'impedance_ohms':target}


def _lane(text,stems):
    """Both TX0P and TXP0 occur in actual vendor libraries."""
    for stem,role in stems:
        for order,pattern in enumerate((rf'{stem}(\d*)([PN+\-])',rf'{stem}([PN+\-])(\d*)')):
            found=re.fullmatch(pattern,text)
            if found:
                a,b=found.groups();index,polarity=(a,b) if order==0 else (b,a)
                return role,int(index or 0),'P' if polarity in ('P','+') else 'N'
    return None


def _recognize(name,p):
    negative=bool(re.fullmatch(r'~\{[^{}]+\}',name))
    text=re.sub(r'[\s_{}~]','',name).upper();family=p['bus_type'];diff=p['differential_ohms']
    if family=='USB':
        m=re.fullmatch(r'(?:USB(\d*))?(?:D(\+|-|P|N|M)|DATA(\+|-)|([PN]))(\d*)',text)
        if m:
            port,polarity,data,short,end=m.groups();port=port or end;group='USB2'+('_'+port if port else '')
            out=_pair(group,'DATA','P' if (polarity or data or short) in ('+','P') else 'N',diff);return{**out,'bus_type':'USB 2.0'}
        signal=re.sub(r'^(?:USB3|SUPERSPEED|SS|DP)','',text)
        lane=_lane(signal,[('TX','TX'),('RX','RX')])
        if lane:
            role,index,polarity=lane;return{**_pair('USB3',role+str(index),polarity,diff),'bus_type':'USB 3.2'}
    elif family=='HDMI':
        signal=re.sub(r'^(?:TMDS|HDMI|IN|OUT)','',text)
        lane=_lane(signal,[('DATA','D'),('D','D')])
        if lane:
            role,index,polarity=lane
            if index>3:raise ValueError('HDMI lane number exceeds this named-lane profile.')
            return{**_pair('HDMI',role+str(index),polarity,diff),'bus_type':'HDMI'}
        lane=_lane(signal,[('CLOCK','CLK'),('CLK','CLK'),('CK','CLK')])
        if lane:return{**_pair('HDMI','CLK',lane[2],diff),'bus_type':'HDMI'}
    elif family.startswith('MIPI'):
        group='CSI' if family.endswith('CSI') else 'DSI';signal=re.sub(r'^(?:MIPI|CSI|DSI)','',text)
        lane=_lane(signal,[('DATA','D'),('DP','D'),('D','D'),('CLOCK','CLK'),('CLK','CLK'),('CK','CLK')])
        if lane:
            role,index,polarity=lane
            if role=='D' and index>4:raise ValueError('MIPI lane number exceeds this D-PHY profile.')
            return{**_pair(group,role+str(index) if role=='D' else 'CLK',polarity,diff),'bus_type':family}
    elif family=='PCIe':
        signal=re.sub(r'^PCIE','',text);lane=_lane(signal,[('PET','TX'),('PER','RX'),('TX','TX'),('RX','RX')])
        if lane:
            role,index,polarity=lane
            if index>=int(p['part_type'].split('x')[-1]):raise ValueError('PCIe lane is outside the selected link width.')
            return{**_pair('PCIe',role+str(index),polarity,diff),'bus_type':'PCIe'}
        lane=_lane(signal,[('REFCLOCK','CLK'),('REFCLK','CLK'),('CLOCK','CLK'),('CLK','CLK'),('CK','CLK')])
        if lane:return{**_pair('PCIe_CLOCK','REFCLK',lane[2],p['clock_ohms']),'bus_type':'PCIe'}
    elif family in ('DDR3','DDR4'):
        signal=re.sub(r'^DDR[34]','',text)
        alias=re.fullmatch(r'([LU])(DQS|DM)',signal)
        if alias:signal=alias[2]+('0' if alias[1]=='L' else '1')
        lane=_lane(signal,[('DQS','DQS'),('CLOCK','CK'),('CLK','CK'),('CK','CK')])
        if not lane:
            m=re.fullmatch(r'(DQS|CK)(\d*)([TC])?',signal)
            if m:lane=(m[1],int(m[2] or 0),'N' if negative or m[3]=='C' else 'P')
        if lane:
            role,index,polarity=lane;return{**_pair(family+'_'+role,role+str(index),polarity,diff),'pair':family+'_'+role+str(index),'bus_type':family}
        m=re.fullmatch(r'(DQ|DM|DBI)(\d+)',signal)
        if m:
            role,index=m[1],int(m[2]);byte=index//8 if role=='DQ' else index
            return{'bus_group':family+'_DATA'+str(byte),'bus_type':family,'pair_role':role+str(index),'impedance_ohms':p['single_ohms']}
        if re.fullmatch(r'(?:A|BA|BG)\d+|(?:ACT|RAS|CAS|WE|CS|CKE|ODT|RESET)\d*#?',signal):
            return{'bus_group':family+'_CA','bus_type':family,'pair_role':signal,'impedance_ohms':p['single_ohms']}
    return None


def prepare(spec,args,pin_names):
    p=profile(args.get('part_type'));targets=args.get('targets',{})
    if not isinstance(targets,dict) or set(targets)-{'differential_ohms','single_ohms','clock_ohms','tolerance_pct'}:raise ValueError('Choose explicit interface impedance targets and optional tolerance.')
    for key,value in targets.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1000000 or value==0 and key!='tolerance_pct' or key=='tolerance_pct' and value>100:raise ValueError('Interface targets need positive finite numbers and a nonnegative tolerance in displayed units.')
        p[key]=value
    policy=args.get('conflict_policy')
    if policy not in (None,'keep','replace'):raise ValueError('Resolve existing properties with keep or replace.')
    out=copy.deepcopy(spec);c=next((v for v in out['components'] if v['ref']==args.get('ref')),None)
    if c is None:raise ValueError('Choose an existing component for interface setup.')
    c['part_type']=p['part_type'];rows=[];unmatched=[];issues=[];conflicts=[]
    for pin,name in pin_names.items():
        try:values=_recognize(name,p)
        except ValueError as error:issues.append({'pins':[c['ref']+'.'+pin],'message':str(error)});continue
        if not values:unmatched.append({'pin':c['ref']+'.'+pin,'name':name});continue
        if 'tolerance_pct' in p:values['impedance_tolerance_pct']=p['tolerance_pct']
        rows.append({'pin':pin,'name':name,'proposed':values,'before':copy.deepcopy(c.get('pin_properties',{}).get(pin,{}))})
    if not rows:issues.append({'pins':[],'message':'No supported interface signal names matched. Use terminal bus properties for a custom mapping.'})
    nets={pin:net['name'] for net in spec.get('nets',[]) for pin in net.get('pins',[])};pairs=defaultdict(list)
    for row in rows:
        if row['proposed'].get('pair'):pairs[row['proposed']['pair']].append(row)
    for pair,members in pairs.items():
        if {row['proposed']['polarity'] for row in members}!={'P','N'}:issues.append({'pins':[c['ref']+'.'+v['pin'] for v in members],'message':pair+': missing P or N terminal.'})
        by_polarity={polarity:{nets.get(c['ref']+'.'+v['pin']) for v in members if v['proposed']['polarity']==polarity}-{None} for polarity in ('P','N')}
        if by_polarity['P']&by_polarity['N']:issues.append({'pins':[c['ref']+'.'+v['pin'] for v in members],'message':pair+': P and N terminals share an electrical net; correct the connection first.'})
        for polarity in ('P','N'):
            side=[v for v in members if v['proposed']['polarity']==polarity]
            if len(side)>1:
                connected={nets.get(c['ref']+'.'+v['pin']) for v in side}
                if None in connected or len(connected)!=1:issues.append({'pins':[c['ref']+'.'+v['pin'] for v in side],'message':pair+': duplicate roles need the same proven electrical net.'})
        if policy=='keep':
            # Keep a unique existing target/identity coherently on both legs.
            for key in ('bus_group','bus_type','pair','pair_role','impedance_ohms','impedance_tolerance_pct'):
                old={v['before'][key] for v in members if v['before'].get(key) not in (None,'')}
                if len(old)>1:issues.append({'pins':[c['ref']+'.'+v['pin'] for v in members],'message':pair+': existing '+key+' values disagree; replace them or edit the terminals.'})
                elif old:
                    value=next(iter(old))
                    for v in members:v['kept']=dict(v.get('kept',{}),**{key:value})
    for row in rows:
        for key,value in row['proposed'].items():
            if row['before'].get(key) not in (None,'',value):conflicts.append({'pin':c['ref']+'.'+row['pin'],'field':key,'existing':row['before'][key],'proposed':value})
        values={**row['before'],**row['proposed']}
        if policy=='keep':values.update({k:v for k,v in row['before'].items() if v not in (None,'')});values.update(row.get('kept',{}))
        row['after']=values;c.setdefault('pin_properties',{})[row['pin']]=values
    old_type=c.get('bus_type')
    if old_type and old_type!=p['bus_type']:conflicts.append({'pin':c['ref'],'field':'bus_type','existing':old_type,'proposed':p['bus_type']})
    if policy!='keep' or not old_type:c['bus_type']=p['bus_type']
    for pair,members in pairs.items():
        if policy=='keep' and any(v['after'].get('polarity')!=v['proposed']['polarity'] for v in members):issues.append({'pins':[c['ref']+'.'+v['pin'] for v in members],'message':pair+': existing polarity contradicts the native signal names.'})
    report={'profile':p,'part_type':p['part_type'],'matched_pins':len(rows),'unmatched':unmatched,'changes':rows,'conflicts':conflicts,'issues':issues,'conflict_policy':policy,'ready':bool(rows) and not issues and (not conflicts or policy is not None)}
    return {'spec':out,'interface_setup':report}
