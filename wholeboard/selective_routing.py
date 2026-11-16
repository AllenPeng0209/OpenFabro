"""Native named-net routing, protection and exact reviewable proposals."""
from __future__ import annotations

import copy
import json
import math
import hashlib
import re
import threading
import time
import uuid
import tempfile
from pathlib import Path

from . import config,router,sexpr
from .kicad import geometry


def _names(values,label):
    if not isinstance(values,list) or len(values)>32 or any(not isinstance(v,str) or not v or not v.isprintable() or len(v)>300 for v in values) or len(set(values))!=len(values):raise ValueError(label+' must be a bounded list of distinct printable native net names.')
    return values


def literal_pattern(value):
    # No wildcard or CSV delimiter survives; ECMAScript matches the exact UTF-8 bytes.
    return '^'+''.join(f'\\x{byte:02x}' for byte in value.encode())+'$'


def route_native(source,target,*,nets,repair_nets=None,seconds=5,work=1000000,cancel=None,diff_pairs=False):
    nets=_names(nets,'nets');repair_nets=_names([] if repair_nets is None else repair_nets,'repair_nets')
    if type(diff_pairs) is not bool:raise ValueError('Differential routing mode must be boolean.')
    if not nets:raise ValueError('Choose at least one net to route.')
    if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not .1<=seconds<=120:raise ValueError('Routing time must be between0.1 and120seconds.')
    if type(work) is not int or not 1000<=work<=100000000:raise ValueError('Use a bounded native routing work budget.')
    cancel=cancel or threading.Event()
    if cancel.is_set():raise InterruptedError()
    source=Path(source);target=Path(target)
    outputs=[target]+[target.with_suffix(ext) for ext in ('.route.json','.stuck.json','.route.log','.kicad_pro','.kicad_dru')]
    if any(path.exists() or path.is_symlink() for path in outputs):raise ValueError('The native routing output and sidecars must be new private files.')
    from .kicad import connectivity
    before=geometry.read(source);_copper(before);connectivity.validate_pad_models(before);names={p['net'] for p in before['pads'] if p.get('net')}
    if any(n not in names for n in nets+repair_nets):raise ValueError('Choose existing native nets with pads.')
    cfg=config.load();binary=router.find('tracemaker',cfg)
    if not binary:raise ValueError('Install TraceMaker in Engineering tools before routing.')
    for option in ('--only-net','--repair','--work'):
        if not router._has_option('tracemaker',['route','--help'],option,cfg):raise ValueError('The installed TraceMaker lacks selective routing/repair support. Update Engineering tools.')
    target.parent.mkdir(parents=True,exist_ok=True);input_path=Path(tempfile.mkdtemp(prefix='routing-input-',dir=target.parent))/'input.kicad_pcb';tree=sexpr.parse(source.read_text());flags={};net_by_id={p['id']:p['net'] for kind in ('tracks','arcs','vias') for p in before[kind]};reserved=set(net_by_id)
    def fresh_id():
        while True:
            value=str(uuid.uuid4())
            if value not in reserved:reserved.add(value);return value
    for node in tree[1:]:
        if sexpr.tag(node) not in ('segment','arc','via'):continue
        identifier=geometry._identity(node);flag=sexpr.find(node,'locked');private=fresh_id();flags[private]=(identifier,copy.deepcopy(flag));native_id=sexpr.find(node,'uuid')
        # TraceMaker's generated UUID counter restarts in each process. Namespace
        # input copper privately, restore its public IDs, and give new copper fresh
        # IDs so a later routing pass cannot impersonate an earlier generated item.
        if native_id is None:node.append(sexpr.S(sexpr.Sym('uuid'),private))
        else:native_id[1]=private
        protected=geometry._locked(node);allow=net_by_id.get(identifier) in repair_nets and not protected
        if flag is not None:node.remove(flag)
        if not allow:node.append(sexpr.S(sexpr.Sym('locked'),sexpr.Sym('yes')))
    input_path.write_text(sexpr.dumps(tree));router._copy_project(source,input_path);router._copy_project(source,target)
    summary=target.with_suffix('.route.json');stuck=target.with_suffix('.stuck.json');log_path=target.with_suffix('.route.log')
    args=['route',str(input_path),'-o',str(target),'--work',str(work),'--time',str(seconds),'--threads','1','--variants','1','--no-gpu','--no-rescue','--no-optimize','--no-refill-repair','--repair','on' if repair_nets else 'off','--repair-work',str(min(work*3,3000000)),'--repair-conns','16','--json',str(summary),'--stuck-report',str(stuck)]
    for name in dict.fromkeys(nets+repair_nets):args.append('--only-net='+literal_pattern(name))
    if diff_pairs:args.extend(['--diff-pairs','--protect-coupled','--pair-share','0'])
    try:
        with log_path.open('w') as stream:
            def log(line):stream.write(line+'\n');stream.flush()
            code=router._stream(router._cmd(binary,args,cfg),log,cancel,timeout=seconds+30)
        if cancel.is_set():raise InterruptedError()
        # TraceMaker documents3 as a valid partial board;1/crashes/timeouts remain failures.
        if code not in (0,3) or not target.is_file() or not summary.is_file():raise RuntimeError('Native selected routing did not finish: '+router._ended(code,seconds+30)+'\n'+log_path.read_text()[-1500:])
        output=sexpr.parse(target.read_text());restored=set()
        for node in output[1:]:
            if sexpr.tag(node) not in ('segment','arc','via'):continue
            identifier=geometry._identity(node);native_id=sexpr.find(node,'uuid')
            if identifier not in flags:
                replacement=fresh_id()
                if native_id is None:node.append(sexpr.S(sexpr.Sym('uuid'),replacement))
                else:native_id[1]=replacement
                continue
            if identifier in restored:raise ValueError('The native engine duplicated an existing copper identity. No routing was applied.')
            restored.add(identifier);original,flag=flags[identifier];native_id[1]=original
            current=sexpr.find(node,'locked')
            if current is not None:node.remove(current)
            if flag is not None:node.append(copy.deepcopy(flag))
        target.write_text(sexpr.dumps(output))
        paired=re.findall(r'^differential pairs: \d+ wanted, (\d+) coupled pair routes',log_path.read_text(),re.MULTILINE)
        return {'pcb':str(target),'summary':json.loads(summary.read_text()),'stuck':json.loads(stuck.read_text()) if stuck.is_file() else None,'log':str(log_path),'command':args,'returncode':code,'coupled_routes':int(paired[-1]) if paired else None}
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _copper(geo):
    result={}
    for kind in ('tracks','arcs','vias'):
        for item in geo.get(kind,[]):
            if not item.get('id') or item['id'] in result:raise ValueError('Resolve missing or duplicate native copper identities before routing.')
            result[item['id']]={**item,'kind':kind}
    return result


def _changes(before,after):
    a,b=_copper(before),_copper(after);added=[b[k] for k in b.keys()-a.keys()];removed=[a[k] for k in a.keys()-b.keys()];modified=[{'id':k,'before':a[k],'after':b[k]} for k in a.keys()&b.keys() if a[k]!=b[k]]
    return {'added_count':len(added),'removed_count':len(removed),'modified_count':len(modified),'added':added,'removed':removed,'modified':modified}


def _open(islands,net):return max(0,sum(bool(g['pads']) for g in islands.get(net,[]))-1)


def _native_open_counts(report_path,geo):
    by_id={}
    for kind in ('pads','tracks','arcs','vias','zone_definitions'):
        for item in geo.get(kind,[]):
            if item.get('id') and item.get('net'):by_id[item['id']]=item['net']
    counts={};unknown=0
    for issue in json.loads(Path(report_path).read_text()).get('unconnected_items',[]):
        names={by_id[item['uuid']] for item in issue.get('items',[]) if item.get('uuid') in by_id}
        if len(names)==1:
            name=next(iter(names));counts[name]=counts.get(name,0)+1
        else:unknown+=1
    return {'by_net':counts,'unattributed':unknown}


def _lost(before,after):
    lost=[]
    for net,groups in before.items():
        labels={pad:i for i,group in enumerate(after.get(net,[])) for pad in group['pads']}
        for group in groups:
            if len(group['pads'])>1 and (any(p not in labels for p in group['pads']) or len({labels.get(p) for p in group['pads']})>1):lost.append({'net':net,'previously_joined_pads':group['pads']})
    return lost


def validate_copper_candidate(before,after,nets,repair_nets):
    from .kicad import connectivity
    changes=_changes(before,after);findings=[];scope=set(nets+repair_nets)
    for item in changes['removed']+[v['before'] for v in changes['modified']]:
        if item.get('locked') or item['net'] not in repair_nets:findings.append({'type':'protected copper','id':item['id'],'net':item['net'],'message':'Existing protected or unapproved copper changed.'})
    for change in changes['modified']:
        if change['before']['net']!=change['after']['net']:findings.append({'type':'net reassignment','id':change['id'],'message':'An existing copper identity cannot move to a different electrical net.'})
    for item in changes['added']+[v['after'] for v in changes['modified']]:
        if item['net'] not in scope:findings.append({'type':'selection scope','id':item['id'],'net':item['net'],'message':'New or modified copper belongs to an unrequested net.'})
    islands_before=connectivity.electrical_islands(before);islands_after=connectivity.electrical_islands(after);lost=_lost(islands_before,islands_after)
    if lost:findings.append({'type':'lost connections','groups':lost})
    attached=lambda groups:{identifier for rows in groups.values() for row in rows if row['pads'] for identifier in row['copper']}
    prior_attached=attached(islands_before);connected=attached(islands_after);after_ids=set(_copper(after));changed_ids={item['id'] for item in changes['added']}|{v['id'] for v in changes['modified']}
    floating=((prior_attached&after_ids)|changed_ids)-connected
    if floating:findings.append({'type':'floating copper','ids':sorted(floating),'message':'New, changed or previously attached copper became isolated from every physical pad.'})
    return {'changes':changes,'findings':findings,'before_islands':islands_before,'after_islands':islands_after,'lost_connections':lost}


def _canonical(value):
    from decimal import Decimal,InvalidOperation
    if isinstance(value,list):return tuple(_canonical(v) for v in value)
    if isinstance(value,sexpr.Sym):
        try:return Decimal(str(value))
        except InvalidOperation:return ('symbol',str(value))
    return ('string',value)


def _zone_rules(geo):
    return sorted((_canonical(sexpr.parse(z['source'])) for z in geo.get('zone_sources',[])),key=repr)


def _private_root(project):
    root=project.root/'.routing-proposals'
    if root.is_symlink() or not root.resolve().is_relative_to(project.root.resolve()):raise ValueError('Routing previews must remain in this project.')
    root.mkdir(exist_ok=True);return root


def _manifest_path(project,identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('Use a routing proposal from this project.')
    folder=_private_root(project)/identifier
    if folder.is_symlink():raise ValueError('Routing proposal folders cannot be links.')
    return folder/'manifest.json'


def project_info(project):
    from . import design_identity,route_tuning,routing_pairs,workbench_native
    from .kicad import connectivity
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        with project.lock:
            source=copy.deepcopy(project.state.get('spec') or {});version=project.state.get('workbench',{}).get('version',0);native=project.state.get('workbench_native') or {};pcb=workbench_native.final_pcb(project)
            if pcb is None:
                if not design_identity.matches(native,source) or not native.get('pcb'):return {'pending':True,'source_version':version,'nets':[],'pairs':[]}
                pcb=Path(native['pcb'])
            if not pcb.is_file() or not pcb.resolve().is_relative_to(project.root.resolve()):raise ValueError('Current native PCB is unavailable.')
            digest=hashlib.sha256(pcb.read_bytes()).hexdigest();inputs=workbench_native._plot_inputs(pcb)[1];guard={'source_identity':design_identity.fields(source),'source_pcb_sha256':digest,'source_render_inputs_sha256':inputs}
        geo=geometry.read(pcb);route_tuning.assert_source(project,guard);islands=connectivity.electrical_islands(geo);copper=_copper(geo);rows=[]
        for net in source['nets']:
            items=[p for p in copper.values() if p['net']==net['name']];pads=[p for p in geo['pads'] if p['net']==net['name'] and p.get('kind')!='np_thru_hole'];protected=sum(p.get('locked',False) for p in items)
            rows.append({'name':net['name'],'pads':len(pads),'open_connections':_open(islands,net['name']),'protected_copper':protected,'unprotected_copper':len(items)-protected})
        return {'source_version':version,'native_source':guard,'nets':rows,'pairs':routing_pairs.hints(source)['pairs'],'pending':False,'connectivity_basis':'physical-pad-model'}


def _load(project,identity):
    from fastapi import HTTPException
    if not isinstance(identity,dict) or set(identity)-{'id','sha256','confirm_changes','confirm_partial'}:raise HTTPException(422,'Use the exact reviewed routing proposal.')
    for key in ('confirm_changes','confirm_partial'):
        if key in identity and type(identity[key]) is not bool:raise HTTPException(422,'Routing acceptance flags must be boolean.')
    try:path=_manifest_path(project,identity.get('id'))
    except ValueError as error:raise HTTPException(422,str(error)) from None
    if not path.is_file() or path.is_symlink() or path.stat().st_size>16000000:raise HTTPException(409,'The routing proposal is unavailable. Review routing again.')
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=identity.get('sha256'):raise HTTPException(409,'The routing proposal differs from the reviewed snapshot.')
    manifest=json.loads(data)
    if manifest.get('schema')!=2 or manifest.get('project_id')!=project.id or manifest.get('id')!=identity['id'] or time.time()-manifest.get('created_at',0)>1800:raise HTTPException(409,'The routing proposal expired, uses older validation, or belongs to another project. Review routing again.')
    return manifest


def validate_proposal(project,identity,spec=None):
    """Caller holds native and project locks through the subsequent accepted save."""
    from fastapi import HTTPException
    from . import design_identity,route_tuning
    manifest=_load(project,identity);result=manifest['result'];version=project.state.get('workbench',{}).get('version',0)
    if result['base_version']!=version:raise HTTPException(409,'The design changed after routing review.')
    route_tuning.assert_source(project,result['native_source'])
    if not result['safe_to_apply']:raise HTTPException(409,'The routing proposal has unresolved native or preservation findings.')
    if result['summary']['requires_changes_approval'] and identity.get('confirm_changes') is not True:raise HTTPException(409,'Accept the listed existing-copper/source changes before applying this exact proposal.')
    if not result['summary']['selected_complete'] and identity.get('confirm_partial') is not True:raise HTTPException(409,'The selected routing is partial. Review the open connections before accepting partial work.')
    if spec is not None and not design_identity.equal(spec,result['spec']):raise HTTPException(409,'The submitted design differs from the reviewed routing proposal.')
    return result


def project_prepare(project,args,cancel=None):
    from fastapi import HTTPException
    from . import design,design_identity,route_tuning,workbench_native
    from .module_capture import native_copper
    from .workbench import validate_draft
    from .kicad import board,cli,schematic,connectivity
    if not isinstance(args,dict) or set(args)-{'nets','repair_nets','seconds','work','base_version','preview_only','coupled'}:raise ValueError('Use named nets and supported native routing options.')
    if 'preview_only' in args and type(args['preview_only']) is not bool:raise ValueError('preview_only must be boolean.')
    if 'coupled' in args and type(args['coupled']) is not bool:raise ValueError('coupled must be boolean.')
    nets=_names(args.get('nets'),'nets');repairs=_names(args.get('repair_nets',[]),'repair_nets');cancel=cancel or threading.Event()
    with workbench_native._locks.setdefault(project.id,threading.RLock()):
        with project.lock:
            version=project.state.get('workbench',{}).get('version',0)
            if type(args.get('base_version',version)) is not int or args.get('base_version',version)!=version:raise HTTPException(409,'The design changed before routing.')
            if project.engine_busy or project.worker and project.worker.is_alive() and project.worker is not threading.current_thread():raise HTTPException(409,'Wait for the active design run before routing.')
            original=copy.deepcopy(project.state.get('spec') or {})
        from . import routing_pairs
        pairs=[p['nets'] for p in routing_pairs.hints(original)['pairs'] if set(p['nets'])&set(nets+repairs)];coupled=args.get('coupled',bool(pairs))
        if coupled:
            if len(pairs)!=1:raise ValueError('Choose one declared differential pair per coupled routing request.')
            pair=pairs[0]
            if not set(pair)<=set(nets):raise ValueError('Select both declared pair members, or explicitly choose independent routing.')
            match=re.fullmatch(r'(.*)([PN+\-])([0-9_]*)',pair[0])
            complement=match[1]+{'P':'N','N':'P','+':'-','-':'+'}[match[2]]+match[3] if match else None
            if complement!=pair[1]:raise ValueError('This pair naming is unsupported by native coupled routing. Use paired manual routing or explicitly request independent routing.')
        if cancel.is_set():raise InterruptedError()
        captured=workbench_native.layout_geometry(project);before=captured['geometry'];input_pcb=workbench_native.final_pcb(project) or Path(captured['native']['pcb'])
        if captured['source_version']!=version or {k:captured[k] for k in design_identity.fields(original)}!=design_identity.fields(original):raise HTTPException(409,'The displayed routing source changed.')
        guard={'source_identity':design_identity.fields(original),'source_pcb_sha256':captured['pcb_sha256'],'source_render_inputs_sha256':captured['render_inputs_sha256']};route_tuning.assert_source(project,guard);_copper(before);connectivity.validate_pad_models(before)
        identifier=uuid.uuid4().hex;folder=_private_root(project)/identifier;folder.mkdir();job=route_native(input_pcb,folder/'routed.kicad_pcb',nets=nets,repair_nets=repairs,seconds=args.get('seconds',5),work=args.get('work',1000000),cancel=cancel,diff_pairs=coupled)
        routed=geometry.read(Path(job['pcb']));source=copy.deepcopy(original);ox,oy=before.get('bbox',[100,100])[:2];adopted=[]
        for f in before['footprints']:
            component=next((c for c in source['components'] if c['ref']==f['ref']),None)
            if not component:continue
            prior=component.get('placement',{});placement={'x_mm':round(f['x']-ox,6),'y_mm':round(f['y']-oy,6),'rotation':f.get('rot',0),'side':'bottom' if f.get('side')=='B.Cu' else 'top'}
            if any(abs(float(prior.get(k,0))-v)>1e-5 for k,v in placement.items() if k!='side') or prior.get('side','top')!=placement['side']:component['placement']={**prior,**placement};adopted.append({'ref':f['ref'],'before':prior,'after':component['placement']})
        draft=copy.deepcopy(source);draft['fixed_copper'],draft['fixed_zones']=native_copper(routed);validate_draft(draft)
        baseline_path=folder/'baseline.drc.json';baseline=cli.drc(input_pcb,refill=False,save=False,report_path=baseline_path);native=schematic.build(draft,folder/'source-preview');parity=schematic.netlist_parity(draft,cli.schematic_nets(Path(native['sch'])))
        if not parity['ok']:raise ValueError('The routing source changed native pin membership.')
        output=Path(board.build(draft,folder/'source-preview')['pcb']);drc_path=folder/'source.drc.json';drc=cli.drc(output,refill=bool(draft.get('fixed_zones')),save=bool(draft.get('fixed_zones')),report_path=drc_path);after=geometry.read(output);findings=[]
        for name in ('pads','footprints','outline'):
            if after[name]!=before[name]:findings.append({'type':'preservation','object':name,'message':'Routing changed existing native '+name+'.'})
        if _zone_rules(before)!=_zone_rules(after):findings.append({'type':'preservation','object':'zone rules','message':'Routing changed an existing zone definition.'})
        if any(z.get('locked') for z in before.get('zone_definitions',[])):
            locked={z['id'] for z in before['zone_definitions'] if z.get('locked')}
            old=sorted((z['zone_id'],z['layer'],json.dumps(z['pts'])) for z in before['zones'] if z['zone_id'] in locked);new=sorted((z['zone_id'],z['layer'],json.dumps(z['pts'])) for z in after['zones'] if z['zone_id'] in locked)
            if old!=new:findings.append({'type':'protected fill','message':'A protected native fill changed or could not be shown unchanged.'})
        validation=validate_copper_candidate(before,after,nets,repairs);changes=validation['changes'];findings.extend(validation['findings']);islands_before=validation['before_islands'];islands_after=validation['after_islands'];lost=validation['lost_connections']
        if coupled and changes['added_count'] and not job.get('coupled_routes'):findings.append({'type':'coupling','message':'The native engine did not confirm a completed coupled route; independent fallback cannot satisfy this pair request.'})
        delta=route_tuning._violation_keys(drc_path)-route_tuning._violation_keys(baseline_path);new_violations=[json.loads(k) for k,count in delta.items() for _ in range(count)]
        if new_violations:findings.append({'type':'native DRC','new_count':len(new_violations),'details':new_violations[:100]})
        native_before=_native_open_counts(baseline_path,before);native_after=_native_open_counts(drc_path,after)
        selected_open={n:max(_open(islands_after,n),native_after['by_net'].get(n,0)) for n in nets};before_open={n:max(_open(islands_before,n),native_before['by_net'].get(n,0)) for n in nets};changed=bool(changes['added_count']+changes['removed_count']+changes['modified_count'] or adopted)
        summary={'requested_nets':nets,'repair_nets':repairs,'coupled_pairs':pairs if coupled else [],'native_coupled_routes':job.get('coupled_routes'),'before_selected_open':before_open,'after_selected_open':selected_open,'selected_complete':not native_after['unattributed'] and all(v==0 for v in selected_open.values()),'before_global_open':baseline['unconnected'],'after_global_open':drc['unconnected'],'modeled_after_global_open':sum(_open(islands_after,n) for n in islands_after),'native_opens_by_net':native_after['by_net'],'unattributed_native_opens':native_after['unattributed'],'changes':changes,'lost_connections':lost,'source_placement_sync':adopted,'requires_changes_approval':bool(changes['removed_count'] or changes['modified_count'] or adopted),'changed':changed}
        if not changed:draft=copy.deepcopy(original)
        route_tuning.assert_source(project,guard)
        if cancel.is_set():raise InterruptedError()
        result={'id':identifier,'base_version':version,'native_source':guard,'spec':draft,'geometry':after,'summary':summary,'native_parity':parity,'baseline_drc':baseline,'drc':drc,'safe_to_apply':not findings,'findings':findings,'native_routing':{'returncode':job['returncode'],'summary':job['summary'],'stuck':job['stuck']},'validation':design.validate(draft).as_dict()}
        manifest={'schema':2,'project_id':project.id,'id':identifier,'created_at':time.time(),'result':result};raw=json.dumps(manifest,ensure_ascii=False,sort_keys=True).encode();path=folder/'manifest.json'
        with path.open('xb') as stream:stream.write(raw)
        return {**result,'proposal_sha256':hashlib.sha256(raw).hexdigest()}
