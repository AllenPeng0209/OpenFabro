"""Editable material intent and bounded visual presets; no inferred engineering properties."""
import copy,json,math,re

def preset(label,color,metalness=0.,roughness=.55,opacity=1.,transmission=0.,ior=1.5,pattern='none',repeat_mm=20.,clearcoat=0.):
    return dict(label=label,color=color,metalness=metalness,roughness=roughness,opacity=opacity,transmission=transmission,ior=ior,pattern=pattern,repeat_mm=repeat_mm,clearcoat=clearcoat,clearcoat_roughness=.2)

PRESETS={
 'plastic':preset('Plastic','#a6b5bf',roughness=.55),
 'aluminum':preset('Aluminum','#b8bec5',.95,.28),
 'steel':preset('Steel','#929da8',.95,.23),
 'chrome':preset('Chrome','#d8dce0',1.,.08),
 'brass':preset('Brass','#b99a55',.95,.25),
 'anodized_black':preset('Black anodized metal','#20262c',.8,.3),
 'gold':preset('Gold','#d5ad45',1.,.19),
 'copper':preset('Copper','#b76c48',.95,.27),
 'clear_acrylic':preset('Clear acrylic','#d1e4ec',roughness=.09,opacity=.3,transmission=.88,ior=1.49),
 'transparent_plastic':preset('Transparent plastic','#c6e0df',roughness=.13,opacity=.35,transmission=.8,ior=1.58),
 'plywood':preset('Plywood','#b48b58',roughness=.72,pattern='wood',repeat_mm=24),
 'mdf':preset('MDF','#b19065',roughness=.9,pattern='mdf',repeat_mm=12),
 'cork':preset('Cork','#a57745',roughness=.95,pattern='cork',repeat_mm=12),
 'glass':preset('Clear glass','#c9e2e8',roughness=.04,opacity=.25,transmission=.96,ior=1.52),
 'reflective_glass':preset('Reflective glass','#a3b3c0',.55,.04,.65,.25,1.52),
 'colored_glass':preset('Colored glass','#4e9fa2',roughness=.08,opacity=.45,transmission=.75,ior=1.52),
 'carbon_fiber':preset('Carbon fiber','#303437',.25,.35,pattern='carbon',repeat_mm=8,clearcoat=.5),
 'fiberglass':preset('Fiberglass','#c5c9ad',roughness=.55,pattern='fiberglass',repeat_mm=7,clearcoat=.2),
 'ceramic':preset('Ceramic','#e0dbd0',roughness=.2,clearcoat=.2),
 'stone':preset('Stone','#96938d',roughness=.9,pattern='stone',repeat_mm=20),
}
ALIASES={'metal':'aluminum','aluminium':'aluminum','clear_glass':'glass','black_anodized_metal':'anodized_black','acrylic':'clear_acrylic'}
NUMBERS={'metalness':(0,1),'roughness':(0,1),'opacity':(0,1),'transmission':(0,1),'ior':(1,2.333),'repeat_mm':(.1,1000),'clearcoat':(0,1),'clearcoat_roughness':(0,1)}

def resolve(value):
    if isinstance(value,str):value={'preset':value}
    if not isinstance(value,dict) or set(value)-({'preset','color','grade','notes'}|set(NUMBERS)):raise ValueError('Use a material preset with optional color, grade and bounded appearance values.')
    if not isinstance(value.get('preset'),str):raise ValueError('Choose a known material preset.')
    name=ALIASES.get(value.get('preset'),value.get('preset'))
    if name not in PRESETS:raise ValueError('Choose a known material preset.')
    result={'preset':name,**copy.deepcopy(PRESETS[name]),'property_basis':'Declared intent and approximate visual preset; no grade, strength, density or certification is inferred.'}
    if 'color' in value:
        if not isinstance(value['color'],str) or not re.fullmatch('#[0-9a-fA-F]{6}',value['color']):raise ValueError('Material color must be a six-digit hex color.')
        result['color']=value['color'].lower()
    for key,(lo,hi) in NUMBERS.items():
        if key in value:
            number=value[key]
            if type(number) not in (int,float) or not math.isfinite(number) or not lo<=number<=hi:raise ValueError('Material '+key+' is outside its supported range.')
            result[key]=number
    for key,limit in [('grade',120),('notes',1000)]:
        if key in value:
            if not isinstance(value[key],str) or len(value[key])>limit:raise ValueError('Use a bounded material '+key+'.')
            result[key]=value[key]
    return result

def library():return {'schema':1,'presets':[{'id':key,**value} for key,value in PRESETS.items()],'scope':'Visual presets and declared material intent. Engineering properties require explicit grade-specific data.'}

def rgb(material):return [int(material['color'][i:i+2],16)/255 for i in (1,3,5)]+[1.]

def apply(bodies,material,selected=None,faces=None):
    output=[]
    for index,body in enumerate(bodies):
        value={**body,'face_colors':[list(color) for color in body['face_colors']]};styles=list(body.get('face_materials') or [body.get('material')]*len(body['shape'].Faces))
        if selected is None or index in selected:
            chosen=range(len(styles)) if faces is None else faces
            if any(i>=len(styles) for i in chosen):raise ValueError('Selected material face is unavailable.')
            if faces is None:value['material']=copy.deepcopy(material)
            for i in chosen:styles[i]=copy.deepcopy(material);value['face_colors'][i]=rgb(material)
            value.pop('preview_meshes',None)
        if any(styles):value['face_materials']=styles
        if styles:value['color']='#'+''.join(f'{round(v*255):02x}' for v in value['face_colors'][0][:3])
        output.append(value)
    if selected and any(i>=len(bodies) for i in selected):raise ValueError('Selected material body is unavailable.')
    return output

def face_signature(face):
    box=face.optimalBoundingBox(False,False);center=face.CenterOfMass
    return {'surface':type(face.Surface).__name__,'center':[center.x,center.y,center.z],'area':face.Area,'bounds':[box.XMin,box.YMin,box.ZMin,box.XMax,box.YMax,box.ZMax]}

def appearances(bodies):
    return [{'name':body['name'],'material':body.get('material'),'faces':[{'geometry':face_signature(face),'material':style} for face,style in zip(body['shape'].Faces,body.get('face_materials') or [body.get('material')]*len(body['shape'].Faces))]} for body in bodies] if any(body.get('material') or body.get('face_materials') for body in bodies) else []

def restore(bodies,assignments):
    if not assignments:return bodies
    if len(bodies)!=len(assignments):raise ValueError('Material body correspondence changed.')
    output=[]
    for body,assignment in zip(bodies,assignments):
        if body['name']!=assignment['name']:raise ValueError('Material body identity changed.')
        styles=[];remaining=list(assignment['faces'])
        for face in body['shape'].Faces:
            actual=face_signature(face);matches=[row for row in remaining if row['geometry']['surface']==actual['surface'] and abs(row['geometry']['area']-actual['area'])<max(1e-5,abs(actual['area'])*1e-7) and all(abs(a-b)<1e-4 for key in ('center','bounds') for a,b in zip(row['geometry'][key],actual[key]))]
            if not matches or len({json.dumps(row['material'],sort_keys=True) for row in matches})!=1:raise ValueError('Material face correspondence is unavailable or ambiguous.')
            row=matches[0];remaining.remove(row);styles.append(row['material'])
        output.append({**body,**({'material':assignment['material']} if assignment.get('material') else {}),'face_materials':styles})
    return output
