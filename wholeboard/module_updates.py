"""Immutable module releases and reviewable three-way instance updates."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import tempfile
import threading
from pathlib import Path
from collections import defaultdict
from urllib.parse import quote,unquote
from . import modules,project_library,sheets,sexpr

def core(asset):return copy.deepcopy({key:asset.get(key,'') if key=='description' else asset[key] for key in ('schema','name','description','ports','design')})
def version(asset):return asset.get('version',1)
def digest(asset):
    # JSON numbers have no integer/float distinction in the browser. Native
    # geometry's 5.0 must retain the same identity after a web editor saves 5.
    def numeric(value):
        if isinstance(value,float) and value.is_integer():return int(value)
        if isinstance(value,list):return [numeric(v) for v in value]
        if isinstance(value,dict):return {k:numeric(v) for k,v in value.items()}
        return value
    return modules.fingerprint(numeric(core(asset)))

def zone_value(row):
    tree=sexpr.parse(row['source']);origin=row.get('origin',[100,100])
    def clean(node):
        if not isinstance(node,list):return node
        kind=sexpr.tag(node)
        if kind in ('uuid','filled_polygon','fill_segments'):return None
        if kind=='net':return ['net',row['net']]
        if kind=='xy':return ['xy',*[round(float(node[i+1])-origin[i],6) for i in range(2)]]
        return [item for child in node if (item:=clean(child)) is not None]
    return clean(tree)

def copper_value(group):
    rows=[]
    for kind in ('tracks','arcs','vias'):
        for item in group.get(kind,[]):rows.append([kind,{k:copy.deepcopy(v) for k,v in item.items() if k not in ('id','net','net_code') and not (k=='locked' and v is True)}])
    for row in group.get('zones',[]):rows.append(['zone',zone_value(row)])
    return sorted(rows,key=lambda value:json.dumps(value,sort_keys=True))

def content_digest(asset):
    value=core(asset);design=value['design']
    editor=design.get('editor',{})
    if not any(editor.get('mirrors',{}).values()):editor.pop('mirrors',None)
    for c in design['components']:
        if c.get('placement') is not None:
            c['placement'].setdefault('side','top');c['placement'].setdefault('rotation',0)
    design['fixed_copper']=[{'net':g['net'],'items':copper_value(g)} for g in design.get('fixed_copper',[])]
    design['fixed_zones']=[{'net':z['net'],'definition':zone_value(z)} for z in design.get('fixed_zones',[])]
    def numeric(v):
        if isinstance(v,bool):return v
        if isinstance(v,(int,float)):return float(v)
        if isinstance(v,list):return [numeric(x) for x in v]
        if isinstance(v,dict):return {k:numeric(x) for k,x in v.items()}
        return v
    return modules.fingerprint(numeric(value))

def release(candidate,previous=None,note=''):
    if not project_library.text(note,2000):raise ValueError('Release notes need bounded printable text.')
    result=core(candidate)
    if previous is not None:
        if content_digest(previous)==content_digest(candidate):raise ValueError('No module changes to publish.')
        history=copy.deepcopy(previous.get('history',[]));history.append({'version':version(previous),'fingerprint':digest(previous),'legacy_fingerprint':modules.fingerprint(previous),'asset':core(previous),'note':previous.get('release_note',''),'origin':copy.deepcopy(previous.get('origin'))})
    else:history=[]
    result.update(version=version(previous)+1 if previous else 1,history=history,release_note=note)
    return result

def revision(asset,number):
    if isinstance(number,bool) or not isinstance(number,int):raise ValueError('Choose an integer module revision.')
    if number==version(asset):return copy.deepcopy(asset)
    row=next((row for row in asset.get('history',[]) if row['version']==number),None)
    if row is None:raise ValueError('The selected module revision is unavailable.')
    origin=row.get('origin') or asset.get('origin')
    return {**copy.deepcopy(row['asset']),'version':number,
            'history':[copy.deepcopy(r) for r in asset.get('history',[]) if r['version']<number],
            **({'origin':copy.deepcopy(origin)} if origin else {}),
            'compatible_fingerprints':copy.deepcopy(row.get('compatible_fingerprints',[])),
            'release_note':row.get('note','')}

def validate_history(asset):
    v=version(asset);history=asset.get('history',[])
    if isinstance(v,bool) or not isinstance(v,int) or v<1 or not isinstance(history,list) or len(history)>1000:raise ValueError('Module revisions need a positive version and bounded history.')
    seen=set()
    def aliases(value):
        values=value.get('compatible_fingerprints',[])
        if not isinstance(values,list) or len(values)>1000 or any(not isinstance(v,str) or not re.fullmatch(r'[0-9a-f]{64}',v) for v in values):raise ValueError('Module baseline aliases must be bounded fingerprints.')
    aliases(asset)
    for row in history:
        if not isinstance(row,dict) or isinstance(row.get('version'),bool) or not isinstance(row.get('version'),int) or not 1<=row['version']<v or row['version'] in seen:raise ValueError('Module revision numbers must be unique and older than the head.')
        seen.add(row['version']);snapshot=row.get('asset')
        aliases(row)
        if not isinstance(snapshot,dict) or 'history' in snapshot:raise ValueError('Module history cannot contain recursive revision lists.')
        modules.validate_asset('Snapshot',snapshot)
        if row.get('fingerprint')!=digest(snapshot):raise ValueError('A frozen module revision fingerprint does not match its content.')

def item_key(kind,net,index):return f'{kind}:{net}:{index}'

def find_base(asset,meta):
    requested=meta.get('baseline',{}).get('version',meta.get('version',1));fp=meta.get('baseline',{}).get('fingerprint',meta.get('fingerprint'))
    candidates=[{'version':version(asset),'asset':core(asset),'legacy_fingerprint':modules.fingerprint(asset),'compatible_fingerprints':asset.get('compatible_fingerprints',[])},*asset.get('history',[])]
    for row in candidates:
        legacy=core(row['asset']);legacy.pop('description',None)
        if row['version']==requested and (not fp or digest(row['asset'])==fp or modules.fingerprint(row['asset'])==fp or modules.fingerprint(legacy)==fp or row.get('legacy_fingerprint')==fp or fp in row.get('compatible_fingerprints',[])):return row['asset']
    raise ValueError('The frozen module baseline is missing. Import its original revision before updating.')

_MISSING=object()

def _copy(value):return value if value is _MISSING else copy.deepcopy(value)

class Merge:
    def __init__(self,resolutions):self.resolutions=resolutions or {};self.conflicts=[];self.changes=[];self.kept=[]
    def choose(self,base,local,upstream,path,*,forced=False):
        if not forced:
            if local==base:
                if upstream!=local:self.changes.append({'id':path,'before':self.show(local),'after':self.show(upstream)})
                return _copy(upstream)
            if upstream==base or local==upstream:
                if local!=upstream:self.kept.append(path)
                return _copy(local)
            if all(isinstance(v,dict) for v in (base,local,upstream)):
                result={}
                for key in sorted(set(base)|set(local)|set(upstream)):
                    value=self.choose(base.get(key,_MISSING),local.get(key,_MISSING),upstream.get(key,_MISSING),path+'/'+str(key))
                    if value is not _MISSING:result[key]=value
                return result
        choice=self.resolutions.get(path)
        if choice not in (None,'local','module'):raise ValueError('Choose local or module for an update conflict.')
        self.conflicts.append({'id':path,'base':self.show(base),'local':self.show(local),'module':self.show(upstream),'choice':choice})
        value=upstream if choice=='module' else local
        if choice=='local' and value!=upstream:self.kept.append(path)
        if choice and value!=local:self.changes.append({'id':path,'before':self.show(local),'after':self.show(value)})
        return _copy(value)
    @staticmethod
    def show(value):return {'removed':True} if value is _MISSING else copy.deepcopy(value)

def scope(spec,instance,meta):
    defs=sheets.definitions(spec);pages={instance};changed=True
    while changed:
        changed=False
        for key,value in defs.items():
            if value.get('parent','') in pages and key not in pages:pages.add(key);changed=True
    known=set(meta.get('refs',[]));refs={c['ref'] for c in spec['components'] if sheets.component_sheet(c) in pages or c.get('module_instance')==instance or c['ref'] in known and c.get('module_instance') in (None,instance)}
    return refs,pages

def _actual_pin(value,maps):
    if value.startswith('local:'):return value[6:]
    ref,pad=value.split('.',1);return maps['refs'][ref]+'.'+pad

def _logical_key(value,reverse):
    ref=re.split(r'[.#]',value,maxsplit=1)[0]
    return reverse[ref]+value[len(ref):] if ref in reverse else 'local:'+value

def fragment(spec,instance,maps,owned_refs,owned_pages,*,known_copper=None):
    editor=spec.get('editor',{});reverse={value:key for key,value in maps['refs'].items()};sheet_reverse={value:key for key,value in maps['sheets'].items()};node_reverse={value:key for key,value in maps.get('nodes',{}).items()};wire_reverse={value:key for key,value in maps.get('wires',{}).items()}
    components={reverse.get(c['ref'],'local:'+c['ref']):copy.deepcopy(c) for c in spec['components'] if c['ref'] in owned_refs}
    def anchor_owned(a):
        if a.startswith('node:'):return a[5:] in editor.get('wire_nodes',{}) and editor['wire_nodes'][a[5:]].get('sheet','') in owned_pages
        if a.startswith('sheet:'):return a[6:].split('.',1)[0] in owned_pages
        return re.split(r'[.#]',a,maxsplit=1)[0] in owned_refs
    result={'components':components,'pins':{},'net_attributes':{},'positions':{},'rotations':{},'mirrors':{},'sheets':{sheet_reverse.get(k,'local:'+k):copy.deepcopy(v) for k,v in sheets.definitions(spec).items() if k in owned_pages},
      'nodes':{node_reverse.get(k,'local:'+k):copy.deepcopy(v) for k,v in editor.get('wire_nodes',{}).items() if v.get('sheet','') in owned_pages},
      'wires':{wire_reverse.get(g.get('id'),'local:'+g.get('id','')):copy.deepcopy(g) for g in editor.get('connection_guides',[]) if anchor_owned(g['from']) or anchor_owned(g['to'])},'copper':{}}
    private=set();names=set(maps.get('nets',{}).values())
    for net in spec['nets']:
        pins=[p for p in net['pins'] if p.split('.')[0] in owned_refs]
        result['pins'].update({_logical_key(p,reverse):net['name'] for p in pins})
        if pins or net['name'] in names:
            result['net_attributes'][net['name']]={k:copy.deepcopy(v) for k,v in net.items() if k!='pins'}
            if not any(p.split('.')[0] not in owned_refs for p in net['pins']):private.add(net['name'])
    for field in ('positions','rotations','mirrors'):
        result[field]={_logical_key(key,reverse):copy.deepcopy(value) for key,value in editor.get(field,{}).items() if re.split(r'[.#]',key,maxsplit=1)[0] in owned_refs}
    ids=set(known_copper if known_copper is not None else [*maps.get('copper',{}).values(),*maps.get('zones',{}).values()])
    for group in spec.get('fixed_copper',[]):
        for kind in ('tracks','arcs','vias'):
            for item in group.get(kind,[]):
                if item.get('id') in ids or known_copper is None and group['net'] in private:result['copper'].setdefault(group['net'],{}).setdefault(kind,[]).append(copy.deepcopy(item))
    for zone in spec.get('fixed_zones',[]):
        if zone.get('id') in ids or known_copper is None and zone['net'] in private:result['copper'].setdefault(zone['net'],{}).setdefault('zones',[]).append(copy.deepcopy(zone))
    return result

def _dependency_asset(asset,project,mapping=None):
    """Place changed dependencies under content-specific IDs, preserving host libraries."""
    out=core(asset);maps={};added={kind:{} for kind in ('footprints','symbols','parts')};library=project.get('library',{})
    def rename(value,kind):
        if not isinstance(value,str) or not value.startswith('Project:'):return value
        key=value[8:]
        if key in maps.get(kind,{}):return 'Project:'+maps[kind][key]
        return value
    for kind in ('footprints','symbols','parts'):
        maps[kind]={}
        for key,value in out['design'].get('library',{}).get(kind,{}).items():
            value=copy.deepcopy(value)
            for field,target_kind in (('symbol','symbols'),('footprint','footprints')):
                if field in value:value[field]=rename(value[field],target_kind)
            preferred=(mapping or {}).get(kind,{}).get(key,key);target=preferred
            if target in library.get(kind,{}) and library[kind][target]!=value:
                target=key[:48]+'_'+modules.fingerprint(value)[:12]
            if target in library.get(kind,{}) and library[kind][target]!=value:raise ValueError('A content-addressed module dependency conflicts with this project.')
            maps[kind][key]=target;added[kind][target]=value
    for component in out['design']['components']:
        for field,kind in (('symbol','symbols'),('footprint','footprints')):
            value=component.get(field,'')
            if value.startswith('Project:') and value[8:] in maps[kind]:component[field]='Project:'+maps[kind][value[8:]]
    out['design']['library']=added
    return out,maps,added

def _realize(project,asset,instance,meta,maps,owned_refs,owned_pages,*,connections=None):
    synthetic=copy.deepcopy(project);synthetic['components']=[c for c in synthetic['components'] if c['ref'] not in owned_refs]
    synthetic['nets']=[{**n,'pins':[p for p in n['pins'] if p.split('.')[0] not in owned_refs]} for n in synthetic['nets']];synthetic['nets']=[n for n in synthetic['nets'] if n['pins']]
    synthetic['fixed_copper']=[];synthetic['fixed_zones']=[]
    editor=synthetic.setdefault('editor',{});editor['sheets']={k:v for k,v in sheets.definitions(project).items() if k not in owned_pages};editor['positions']={};editor['rotations']={};editor['mirrors']={};editor['wire_nodes']={};editor['connection_guides']=[];editor['module_instances']={}
    module_id=meta['module'];synthetic.setdefault('library',{}).setdefault('modules',{})[module_id]=copy.deepcopy(asset)
    for kind,values in asset['design'].get('library',{}).items():synthetic['library'].setdefault(kind,{}).update(copy.deepcopy(values))
    params=meta.get('baseline',{});identity=copy.deepcopy(maps);known=set(maps.get('refs',{}).values());identity['reserved_refs']=[r for r in owned_refs if r not in known];identity['reserved_sheets']=[s for s in owned_pages if s not in set(maps.get('sheets',{}).values())]
    offset=params.get('board_offset',meta.get('board_offset',[0,0]));root=project.get('editor',{}).get('sheets',{}).get(instance,{})
    result=modules.instantiate(synthetic,module_id,instance,offset=offset,position=params.get('position',root.get('position',[850,140])),parent=params.get('parent',root.get('parent','')),connections=connections or {},_identity=identity)
    newmeta=result['editor']['module_instances'][instance];newmaps=newmeta['source_maps'];refs=set(newmaps['refs'].values());pages=set(newmaps['sheets'].values())
    ids=[*newmaps['copper'].values(),*newmaps['zones'].values()]
    return fragment(result,instance,newmaps,refs,pages,known_copper=ids),newmaps,newmeta

def _legacy_maps(spec,instance,meta,asset):
    source=asset['design'];source_refs=[c['ref'] for c in source['components']];actual=meta.get('refs',[])
    if meta.get('converted'):refs={ref:ref for ref in source_refs}
    elif len(source_refs)==len(actual):refs=dict(zip(source_refs,actual))
    else:raise ValueError('This legacy instance has no unambiguous part mapping. Match its source references before updating.')
    pages={'':instance,**{sid:instance+'_'+sid for sid in sheets.definitions(source)}}
    nodes={key:key for key in source.get('editor',{}).get('wire_nodes',{}) if key in spec.get('editor',{}).get('wire_nodes',{})}
    if len(nodes)!=len(source.get('editor',{}).get('wire_nodes',{})):raise ValueError('This legacy instance needs explicit free-node matching before updating.')
    def anchor(a):
        if a.startswith('node:'):return 'node:'+nodes[a[5:]]
        if a.startswith('sheet:'):
            sid,label=a[6:].split('.',1);return 'sheet:'+pages[sid]+'.'+label
        ref=re.split(r'[.#]',a,maxsplit=1)[0];return refs[ref]+a[len(ref):]
    wires={}
    for i,g in enumerate(source.get('editor',{}).get('connection_guides',[])):
        candidates=[v for v in spec.get('editor',{}).get('connection_guides',[]) if v['from']==anchor(g['from']) and v['to']==anchor(g['to'])]
        if len(candidates)!=1:raise ValueError('This legacy instance needs explicit wire matching before updating.')
        wires[g.get('id',f'wire-{i}')]=candidates[0]['id']
    return {'refs':refs,'nets':copy.deepcopy(meta['nets']),'sheets':pages,'nodes':nodes,'wires':wires,'copper':{},'zones':{},'deps':{k:{key:key for key in source.get('library',{}).get(k,{})} for k in ('symbols','footprints','parts')}}

def prepare(project,instance,*,asset=None,resolutions=None,port_actions=None):
    current_meta=project.get('editor',{}).get('module_instances',{}).get(instance)
    if not current_meta:raise ValueError('Choose an existing module instance.')
    head=copy.deepcopy(asset or project['library']['modules'][current_meta['module']]);head=_carry_aliases(head,project['library']['modules'][current_meta['module']]);modules.validate_asset(current_meta['module'],head)
    old=find_base(head,current_meta);meta=copy.deepcopy(current_meta);owned_refs,owned_pages=scope(project,instance,meta)
    maps=copy.deepcopy(meta.get('baseline',{}).get('maps') or meta.get('source_maps') or _legacy_maps(project,instance,meta,old))
    # A recorded designator rename is identity-preserving; a net rebind is not.
    maps['refs'].update(meta.get('source_maps',{}).get('refs',{}))
    base_asset=core(old);base_asset['design'].setdefault('library',{})
    for kind in ('symbols','footprints','parts'):
        aliases=maps.get('deps',{}).get(kind,{})
        base_asset['design']['library'][kind]={aliases.get(key,key):copy.deepcopy(v) for key,v in base_asset['design'].get('library',{}).get(kind,{}).items()}
        for c in base_asset['design']['components']:
            field='symbol' if kind=='symbols' else 'footprint' if kind=='footprints' else None
            if field and c.get(field,'').startswith('Project:') and c[field][8:] in aliases:c[field]='Project:'+aliases[c[field][8:]]
    base,bmaps,_=_realize(project,base_asset,instance,meta,maps,owned_refs,owned_pages)
    decisions=Merge(resolutions);up_asset,dep_maps,added=_dependency_asset(head,project,maps.get('deps'));effective_asset=copy.deepcopy(up_asset)
    for kind in ('symbols','footprints','parts'):
        for source_id,old_id in maps.get('deps',{}).get(kind,{}).items():
            if source_id not in old['design'].get('library',{}).get(kind,{}) or source_id not in head['design'].get('library',{}).get(kind,{}):continue
            b=old['design']['library'][kind][source_id];l=project.get('library',{}).get(kind,{}).get(old_id,_MISSING);u=head['design']['library'][kind][source_id]
            chosen=decisions.choose(b,l,u,f'dependencies/{kind}/{source_id}')
            if chosen is not _MISSING and chosen==l and l!=u:
                target_id=dep_maps[kind][source_id]
                for c in effective_asset['design']['components']:
                    field='symbol' if kind=='symbols' else 'footprint' if kind=='footprints' else None
                    if field and c.get(field)=='Project:'+target_id:c[field]='Project:'+old_id
                effective_asset['design']['library'][kind][old_id]=copy.deepcopy(l)
    root=project['editor']['sheets'][instance];old_ports=old['ports'];new_ports=head['ports'];actions=port_actions or {};port_changes=[];renames={};disconnected=set();connections={}
    for label,port in old_ports.items():
        target=label if label in new_ports else next((key for key,p in new_ports.items() if p['net']==port['net'] and sum(v['net']==port['net'] for v in new_ports.values())==1),None)
        if target:
            renames[label]=target;connections[target]=root.get('ports',{}).get(label,{}).get('net',maps['nets'][port['net']]);continue
        actual=maps['nets'][port['net']];external=any(p.split('.')[0] not in owned_refs for n in project['nets'] if n['name']==actual for p in n['pins']) or any(any(g[key].startswith('sheet:'+instance+'.') and unquote(g[key].split('.',1)[1])==label for key in ('from','to')) for g in project.get('editor',{}).get('connection_guides',[]))
        if external:
            choice=actions.get(label);port_changes.append({'label':label,'net':actual,'choice':choice,'options':list(new_ports)})
            if choice=='disconnect':disconnected.add(label)
            elif choice in new_ports:renames[label]=choice;connections[choice]=actual
        else:disconnected.add(label)
    for label,port in new_ports.items():
        if label in connections:continue
        if label in root.get('ports',{}):connections[label]=root['ports'][label]['net']
    identity=copy.deepcopy(maps);identity['deps']=dep_maps
    for label in disconnected:
        net=old_ports[label]['net']
        if not any(p['net']==net for p in new_ports.values()):identity['nets'].pop(net,None)
    upstream,umaps,new_meta=_realize(project,up_asset,instance,meta,identity,owned_refs,owned_pages,connections=connections)
    effective,_,_=_realize(project,effective_asset,instance,meta,{**umaps,'deps':dep_maps},owned_refs,owned_pages,connections=connections)
    umaps={key:{**copy.deepcopy(maps.get(key,{})),**value} for key,value in umaps.items()}
    known_ids=[*maps.get('copper',{}).values(),*maps.get('zones',{}).values()]
    local=fragment(project,instance,bmaps,owned_refs,owned_pages)
    merged={};whole_kept=set();deleted=set()
    for section in ('components','positions','rotations','mirrors','sheets','nodes','wires','pins','net_attributes'):
        merged[section]={}
        for key in sorted(set(base[section])|set(local[section])|set(effective[section])):
            b,l,u=(v[section].get(key,_MISSING) for v in (base,local,effective))
            if section in ('pins','positions','rotations','mirrors') and re.split(r'[.#]',key,maxsplit=1)[0] in whole_kept:value=_copy(l)
            elif section=='pins' and key.split('.',1)[0] in deleted:continue
            else:
                dependent=False
                if section=='components' and b is not _MISSING and l is not _MISSING and u is _MISSING:
                    ref=l['ref'];dependent=any(any(re.split(r'[.#]',g[end],maxsplit=1)[0]==ref for end in ('from','to')) and (wire not in base['wires'] or g!=base['wires'][wire]) for wire,g in local['wires'].items()) or any(pin.startswith(key+'.') and value!=base['pins'].get(pin) for pin,value in local['pins'].items())
                value=decisions.choose(b,l,u,section+'/'+key,forced=dependent)
                if section=='components' and value is not _MISSING and u is _MISSING:whole_kept.add(key)
                if section=='components' and value is _MISSING:deleted.add(key)
            if value is not _MISSING:merged[section][key]=value
    out=copy.deepcopy(project);installed=out['library']['modules'][meta['module']]
    out['library']['modules'][meta['module']]=installed if version(installed)>version(head) and installed.get('origin',{}).get('catalog_id')==head.get('origin',{}).get('catalog_id') else head
    for kind,values in added.items():out['library'].setdefault(kind,{}).update(values)
    out['components']=[c for c in project['components'] if c['ref'] not in owned_refs]+list(merged['components'].values());alive={c['ref'] for c in out['components']};actual_owned={c['ref'] for c in merged['components'].values()}
    rows={n['name']:{**copy.deepcopy(n),'pins':[p for p in n['pins'] if p.split('.')[0] not in owned_refs]} for n in project['nets']}
    for name,row in merged['net_attributes'].items():
        if name not in rows:rows[name]={**row,'pins':[]}
        elif not rows[name]['pins']:rows[name].update(copy.deepcopy(row))
    for key,name in merged['pins'].items():
        actual=_actual_pin(key,umaps)
        if actual.split('.')[0] not in alive:continue
        if name not in rows:rows[name]={'name':name,'class':'signal','pins':[]}
        rows[name]['pins'].append(actual)
    out['nets']=[row for row in rows.values() if row['pins'] or any(n['net']==row['name'] for n in merged['nodes'].values())]
    editor=out.setdefault('editor',{})
    for section,field in (('positions','positions'),('rotations','rotations'),('mirrors','mirrors')):
        editor[field]={k:copy.deepcopy(v) for k,v in project.get('editor',{}).get(field,{}).items() if re.split(r'[.#]',k,maxsplit=1)[0] not in owned_refs}
        for key,value in merged[section].items():
            actual=key[6:] if key.startswith('local:') else umaps['refs'][re.split(r'[.#]',key,maxsplit=1)[0]]+key[len(re.split(r'[.#]',key,maxsplit=1)[0]):]
            if re.split(r'[.#]',actual,maxsplit=1)[0] in alive:editor[field][actual]=value
    editor['sheets']={key:copy.deepcopy(value) for key,value in sheets.definitions(project).items() if key not in owned_pages}
    for key,value in merged['sheets'].items():editor['sheets'][key[6:] if key.startswith('local:') else umaps['sheets'][key]]=value
    editor['wire_nodes']={key:copy.deepcopy(value) for key,value in project.get('editor',{}).get('wire_nodes',{}).items() if value.get('sheet','') not in owned_pages}
    editor['wire_nodes'].update({key[6:] if key.startswith('local:') else umaps['nodes'][key]:value for key,value in merged['nodes'].items()})
    old_owned_ids={g['id'] for g in local['wires'].values()};kept_wires=[copy.deepcopy(g) for g in project.get('editor',{}).get('connection_guides',[]) if g.get('id') not in old_owned_ids]
    all_wires=kept_wires+list(merged['wires'].values());removed_wires=[]
    for g in all_wires:
        discard=False
        for key in ('from','to'):
            prefix='sheet:'+instance+'.'
            if g[key].startswith(prefix):
                label=unquote(g[key][len(prefix):])
                if label in disconnected:discard=True
                elif label in renames:g[key]=prefix+quote(renames[label],safe="~()*!.'-")
            elif not g[key].startswith(('node:','sheet:')) and re.split(r'[.#]',g[key],maxsplit=1)[0] not in alive:discard=True
        if discard:removed_wires.append(g['id'])
    all_wires=[g for g in all_wires if g['id'] not in removed_wires];changed=True
    while changed:
        ids={g['id'] for g in all_wires};filtered=[g for g in all_wires if all(g[k]['wire'] in ids for k in ('from_join','to_join') if g.get(k))];changed=len(filtered)!=len(all_wires);all_wires=filtered
    editor['connection_guides']=all_wires
    # Preserve current routed copper for unchanged geometry; source changes are merged per net.
    copper={};removed_copper=defaultdict(int)
    for name in sorted(set(base['copper'])|set(local['copper'])|set(effective['copper'])):
        b,l,u=(v['copper'].get(name,{}) for v in (base,local,effective));bc,lc,uc=(copper_value(v) for v in (b,l,u))
        choice=decisions.choose(bc,lc,uc,'copper/'+name)
        copper[name]=copy.deepcopy(u if choice==uc and choice!=lc else l)
    old_pins={p:n['name'] for n in project['nets'] for p in n['pins']};new_pins={p:n['name'] for n in out['nets'] for p in n['pins']};new_components={c['ref']:c for c in out['components']};invalid=set()
    for c in project['components']:
        if c['ref'] not in owned_refs:continue
        next_c=new_components.get(c['ref']);physical=not c.get('terminal',{}).get('exclude_from_pcb')
        moved=next_c is None or c.get('footprint')!=next_c.get('footprint') or any(c.get('placement',{}).get(k,default)!=next_c.get('placement',{}).get(k,default) for k,default in (('x_mm',0),('y_mm',0),('rotation',0),('side','top'))) or c.get('terminal',{}).get('exclude_from_pcb')!=next_c.get('terminal',{}).get('exclude_from_pcb')
        for pin,name in old_pins.items():
            if pin.startswith(c['ref']+'.') and physical and (moved or new_pins.get(pin)!=name):invalid.add(name)
    owned_copper_ids={item.get('id') for g in local['copper'].values() for kind in ('tracks','arcs','vias') for item in g.get(kind,[])};owned_zone_ids={z.get('id') for g in local['copper'].values() for z in g.get('zones',[])}
    out['fixed_copper']=[]
    for group in project.get('fixed_copper',[]):
        g=copy.deepcopy(group)
        for kind in ('tracks','arcs','vias'):
            values=g.get(kind,[]);g[kind]=[item for item in values if item.get('id') not in owned_copper_ids and g['net'] not in invalid];removed_copper[kind]+=len(values)-len(g[kind])
        if any(g.get(kind) for kind in ('tracks','arcs','vias')):out['fixed_copper'].append(g)
    out['fixed_zones']=[copy.deepcopy(z) for z in project.get('fixed_zones',[]) if z.get('id') not in owned_zone_ids and z['net'] not in invalid]
    for name,group in copper.items():
        if name in invalid:continue
        if any(group.get(k) for k in ('tracks','arcs','vias')):out['fixed_copper'].append({'net':name,**{k:copy.deepcopy(group.get(k,[])) for k in ('tracks','arcs','vias')}})
        out['fixed_zones']+=copy.deepcopy(group.get('zones',[]))
    # Restore the exact existing representation when no copper semantics changed.
    if not invalid and all(copper_value(copper.get(name,{}))==copper_value(local['copper'].get(name,{})) for name in set(copper)|set(local['copper'])):
        out['fixed_copper']=copy.deepcopy(project.get('fixed_copper',[]));out['fixed_zones']=copy.deepcopy(project.get('fixed_zones',[]));removed_copper=defaultdict(int)
    for layer,name in list(out['board'].get('planes',{}).items()):
        if name in invalid:del out['board']['planes'][layer]
    if out['board'].get('ground_pour') in invalid:out['board']['ground_pour']=None
    pending_ports=[row for row in port_changes if row['choice']!='disconnect' and row['choice'] not in new_ports]
    unresolved=[row for row in decisions.conflicts if row['choice'] is None]
    new_meta.update(module=meta['module'],version=version(head),fingerprint=digest(head),source_maps=umaps)
    new_meta['baseline']={'version':version(head),'fingerprint':digest(head),'maps':copy.deepcopy(umaps),'board_offset':meta.get('baseline',{}).get('board_offset',meta.get('board_offset',[0,0])),'position':meta.get('baseline',{}).get('position',root.get('position',[850,140])),'parent':meta.get('baseline',{}).get('parent',root.get('parent',''))}
    new_meta['refs']=[c['ref'] for c in out['components'] if c['ref'] in actual_owned and c.get('module_instance') in (None,instance)];new_meta['modified']=bool(decisions.kept or any(row['choice']=='local' for row in decisions.conflicts));new_meta['local_overrides']=decisions.kept
    editor.setdefault('module_instances',{})[instance]=new_meta
    def copper_records(spec):
        records={}
        for group in spec.get('fixed_copper',[]):
            for kind in ('tracks','arcs','vias'):
                for item in group.get(kind,[]):records[(kind,item.get('id') or modules.fingerprint(item))]=(group['net'],{k:v for k,v in item.items() if k not in ('id','net','net_code')})
        for z in spec.get('fixed_zones',[]):records[('zones',z.get('id') or modules.fingerprint(z))]=(z['net'],zone_value(z))
        return records
    prior,following=copper_records(project),copper_records(out);removed_copper=defaultdict(int);updated_copper=defaultdict(int);added_copper=defaultdict(int)
    for key,value in prior.items():
        if key not in following:removed_copper[key[0]]+=1
        elif value!=following[key]:updated_copper[key[0]]+=1
    for key in following:
        if key not in prior:added_copper[key[0]]+=1
    return {'spec':None if unresolved or pending_ports else out,'conflicts':decisions.conflicts,'port_changes':port_changes,'changes':decisions.changes,'local_overrides':copy.deepcopy(decisions.kept),'summary':{'instance':instance,'from_version':meta.get('version',1),'to_version':version(head),'kept_local':len(decisions.kept),'invalidated_nets':sorted(invalid),'removed_copper':dict(removed_copper),'updated_copper':dict(updated_copper),'added_copper':dict(added_copper),'removed_wires':removed_wires},'draft':out}

def project_draft(project,arguments,*,manager,actor):
    from fastapi import HTTPException
    from . import module_catalog,workbench_native,schematic_view,design
    from .workbench import validate_draft
    from .module_capture import native_copper
    from .kicad import board,geometry,schematic,cli
    instances=arguments.get('instances',[])
    if not isinstance(instances,list) or not instances or len(instances)>200 or any(not isinstance(i,str) for i in instances) or len(set(instances))!=len(instances):raise ValueError('Choose a bounded list of unique module instances.')
    for field in ('sources','resolutions','port_actions'):
        values=arguments.get(field,{})
        if not isinstance(values,dict) or any(key not in instances or not isinstance(value,dict) for key,value in values.items()):raise ValueError('Module update choices must map selected instances to objects.')
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        with project.lock:
            saved=project.state.get('workbench',{}).get('version',0)
            if arguments.get('base_version')!=saved:raise HTTPException(409,'The design changed before module update review.')
            if getattr(project,'engine_busy',False) or project.worker and project.worker.is_alive():raise HTTPException(409,'Wait for the active run before reviewing module updates.')
            spec=copy.deepcopy(project.state.get('spec') or {})
        native=workbench_native.final_pcb(project) or Path(workbench_native.generate(project)['pcb']);spec['fixed_copper'],spec['fixed_zones']=native_copper(geometry.read(native))
        plans=[];pending=False;remote=[]
        for instance in instances:
            meta=spec.get('editor',{}).get('module_instances',{}).get(instance)
            if not meta:raise ValueError('The selected module instance no longer exists.')
            request=arguments.get('sources',{}).get(instance,{})
            head=spec['library']['modules'][meta['module']]
            if request.get('catalog_id'):
                head=module_catalog.resolve(manager,actor,request['catalog_id'],version=request.get('version'));remote.append(request)
            elif request.get('version') is not None:head=revision(head,request['version'])
            plan=prepare(spec,instance,asset=head,resolutions=arguments.get('resolutions',{}).get(instance),port_actions=arguments.get('port_actions',{}).get(instance))
            pending|=plan['spec'] is None;spec=plan.pop('draft');plan.pop('spec');plans.append(plan)
        result={'spec':None if pending else spec,'plans':plans,'base_version':saved}
        if not pending:
            validate_draft(spec)
            with tempfile.TemporaryDirectory(prefix='wholeboard-module-update-') as directory:
                folder=Path(directory);sch=schematic.build(spec,folder);proof=schematic.netlist_parity(spec,cli.schematic_nets(Path(sch['sch'])))
                if not proof['ok']:raise ValueError('The merged module connections do not match the native KiCad netlist.')
                pcb=Path(board.build(spec,folder)['pcb'])
                if spec.get('fixed_zones'):cli.drc(pcb,refill=True,save=True)
                result['geometry']=geometry.read(pcb);result['native_notes']=sch.get('notes',[])
            result['native_parity']=proof;result['validation']=design.validate(spec).as_dict();result['schematic']=schematic_view.scene(spec)
        for request in remote:module_catalog.resolve(manager,actor,request['catalog_id'],version=request.get('version'))
        with project.lock:
            if project.state.get('workbench',{}).get('version',0)!=saved:raise HTTPException(409,'The design changed during module update review.')
        return result

def install(project,module_id,asset):
    if not project_library.identifier(module_id):raise ValueError('Choose a valid module library ID.')
    out=copy.deepcopy(project);modules.validate_asset(module_id,asset);head=copy.deepcopy(asset);current=out.get('library',{}).get('modules',{}).get(module_id)
    if current:
        candidates=[head,*[row['asset'] for row in head.get('history',[])]];match=next((value for value in candidates if content_digest(value)==content_digest(current)),None)
        if match is None:raise ValueError('A different module uses this library ID. Choose another ID.')
        fingerprints=[digest(current),modules.fingerprint(current),*current.get('compatible_fingerprints',[])]
        if match is head:head['compatible_fingerprints']=list(dict.fromkeys([*head.get('compatible_fingerprints',[]),*fingerprints]))
        else:
            row=next(row for row in head['history'] if row['asset'] is match);row['compatible_fingerprints']=list(dict.fromkeys([*row.get('compatible_fingerprints',[]),*fingerprints]))
        if version(current)>version(head) and current.get('origin',{}).get('catalog_id')==head.get('origin',{}).get('catalog_id'):head=current
    out.setdefault('library',{}).setdefault('modules',{})[module_id]=head;return out

def _carry_aliases(head,installed):
    sources=[{'version':version(installed),'asset':core(installed),'compatible_fingerprints':installed.get('compatible_fingerprints',[]),'legacy_fingerprint':modules.fingerprint(installed)},*installed.get('history',[])]
    targets=[{'version':version(head),'asset':core(head),'container':head},*[{**row,'container':row} for row in head.get('history',[])]]
    for target in targets:
        for source in sources:
            if target['version']==source['version'] and content_digest(target['asset'])==content_digest(source['asset']):
                row=target['container'];row['compatible_fingerprints']=list(dict.fromkeys([*row.get('compatible_fingerprints',[]),digest(source['asset']),*source.get('compatible_fingerprints',[]),*([source['legacy_fingerprint']] if source.get('legacy_fingerprint') else [])]))
    return head
