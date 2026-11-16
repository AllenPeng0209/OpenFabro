"""Adaptive, span-aware STEP mass properties in a cancellable host-Python worker."""
import copy
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import traceback

def version():return importlib.metadata.version('cadquery-ocp-novtk')

def measure_step(path):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    reader=STEPControl_Reader()
    if reader.ReadFile(str(path))!=IFSelect_RetDone or reader.TransferRoots()<1:raise ValueError('Adaptive mass reader could not load the exported STEP.')
    shape=reader.OneShape()
    def bounds(item):
        box=Bnd_Box();BRepBndLib.AddOptimal_s(item,box,False,False);lower,upper=box.CornerMin(),box.CornerMax()
        return {'origin_mm':[lower.X(),lower.Y(),lower.Z()],'size_mm':[upper.X()-lower.X(),upper.Y()-lower.Y(),upper.Z()-lower.Z()]}
    def properties(item):
        volume=GProp_GProps();area=GProp_GProps()
        error=float(BRepGProp.VolumePropertiesGK_s(item,volume,1e-10,True,True,False,False,False))
        area_error=float(BRepGProp.SurfaceProperties_s(item,area,1e-10,False))
        values=[volume.Mass(),area.Mass(),error,area_error]
        if not all(math.isfinite(v) for v in values) or volume.Mass()<=0 or area.Mass()<=0 or not 0<=error<=1e-8 or not 0<=area_error<=1e-8:
            raise ValueError('Adaptive mass integration did not meet its error bound.')
        return {'volume_mm3':volume.Mass(),'area_mm2':area.Mass(),'volume_relative_error':error,'area_relative_error':area_error,**bounds(item)}
    total=properties(shape);solids=[];iterator=TopExp_Explorer(shape,TopAbs_SOLID)
    while iterator.More():
        if len(solids)>=256:raise ValueError('Adaptive mass input exceeds the solid budget.')
        solid=iterator.Current();entry=properties(solid);faces=[];face_iterator=TopExp_Explorer(solid,TopAbs_FACE)
        while face_iterator.More():
            face=face_iterator.Current();area=GProp_GProps();error=float(BRepGProp.SurfaceProperties_s(face,area,Eps=1e-10,SkipShared=False))
            if not math.isfinite(area.Mass()+error) or area.Mass()<=0 or not 0<=error<=1e-8:raise ValueError('Adaptive face integration did not converge.')
            faces.append({'area_mm2':area.Mass(),'area_relative_error':error,**bounds(face)});face_iterator.Next()
        entry['faces']=faces;solids.append(entry);iterator.Next()
    if not solids or abs(sum(s['volume_mm3'] for s in solids)-total['volume_mm3'])>max(1e-7,total['volume_mm3']*1e-8):raise ValueError('Adaptive component and assembly mass are inconsistent.')
    return {**total,'solids':solids,'STEP_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'ocp_version':version()}

def correct_report(report,path,result_id,scene=None):
    result=copy.deepcopy(report);mass=measure_step(path)
    if len(mass['solids'])!=report['solids'] or len(report['bodies'])!=len(mass['solids']):raise ValueError('Adaptive STEP solids do not match the native report.')
    remaining=set(range(len(mass['solids'])));face_areas=[]
    def close(body,solid):return all(abs(a-b)<=1e-5 for key in ('origin_mm','size_mm') for a,b in zip(body[key],solid[key]))
    def apply(target,properties):
        target['kernel_default_mass_properties']={k:target[k] for k in ('volume_mm3','area_mm2') if k in target}
        target.update({k:properties[k] for k in ('volume_mm3','area_mm2')})
        target['mass_property_basis']='occt-adaptive-span-integration'
    for body in result['bodies']:
        candidates=[i for i in sorted(remaining) if close(body,mass['solids'][i])]
        if not candidates:raise ValueError('Adaptive STEP body bounds differ from the native report.')
        if len(candidates)>1:
            first=mass['solids'][candidates[0]]
            if any(abs(mass['solids'][i][key]-first[key])>max(1e-7,abs(first[key])*1e-8) for i in candidates for key in ('volume_mm3','area_mm2')):raise ValueError('Adaptive component mass matching is ambiguous.')
        index=candidates[0];remaining.remove(index);apply(body,mass['solids'][index])
        native=next((b for b in (scene or {}).get('topology',{}).get('bodies',[]) if b['body_id']==body['body_id']),None)
        if native:
            for face in native['faces']:
                want=face.get('mass_bounds_mm');matches=[f for f in mass['solids'][index]['faces'] if want and all(abs(a-b)<=1e-5 for a,b in zip(want,f['origin_mm']+f['size_mm']))]
                if matches and all(abs(f['area_mm2']-matches[0]['area_mm2'])<=max(1e-7,matches[0]['area_mm2']*1e-8) for f in matches):
                    face_areas.append({'body_id':body['body_id'],'face_index':face['index'],'area_mm2':matches[0]['area_mm2'],'area_relative_error':matches[0]['area_relative_error']})
    apply(result,mass)
    if 'step_roundtrip' in result:apply(result['step_roundtrip'],mass)
    members=result.get('assembly',{}).get('members',[])
    for member in members:
        bodies=[b for b in result['bodies'] if b.get('component_id')==member['id']]
        if bodies:apply(member,{k:sum(b[k] for b in bodies) for k in ('volume_mm3','area_mm2')})
    for feature in result.get('features',[]):
        if feature['id']==result_id:apply(feature,mass)
        else:
            member=next((m for m in members if m['id']==feature['id']),None)
            if member:apply(feature,member)
            else:feature['mass_property_basis']='kernel-default-estimate'
    result['mass_properties']={'method':'occt-adaptive-span-integration','STEP_sha256':mass['STEP_sha256'],'ocp_version':mass['ocp_version'],
        'requested_relative_error':1e-10,'volume_relative_error':mass['volume_relative_error'],'area_relative_error':mass['area_relative_error'],
        'kernel_default_volume_mm3':report['volume_mm3'],'kernel_default_area_mm2':report['area_mm2'],
        'face_areas':face_areas,'scope':'Adaptive integration of exact exported STEP surfaces with B-spline spans. Intermediate features and face-area identity signatures retain kernel estimates; matched face_areas are measurements. Historical reports remain unchanged; no density is inferred.'}
    return result

if __name__=='__main__':
    job=json.loads(Path(os.environ['OPENFABRO_MASS_JOB']).read_text())
    try:
        report=json.loads(Path(job['report']).read_text());scene=json.loads(Path(job['scene']).read_text()) if job.get('scene') else None
        result=correct_report(report,job['step'],job['result_id'],scene);Path(job['output']).write_text(json.dumps(result,indent=2))
    except Exception as error:
        Path(job['output']).write_text(json.dumps({'ok':False,'error':str(error)}));traceback.print_exc();raise
