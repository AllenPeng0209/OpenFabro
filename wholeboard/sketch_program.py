"""Bounded declarative sketch geometry and constraints, never native Python input."""
import re

ID=re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')
GEOMETRY={'line':{'start','end'},'circle':{'center','radius'},'arc':{'center','radius','start_angle','end_angle'},'ellipse':{'center','major_radius','minor_radius','angle'},'bspline':{'poles','knots','degree','weights'}}
CONSTRAINTS={'coincident','horizontal','vertical','point_on_object','parallel','perpendicular','tangent','equal','symmetric','distance','distance_x','distance_y','radius','diameter','angle','block'}
DIMENSIONS={'distance','distance_x','distance_y','radius','diameter','angle'}


def resolve(raw,number,vector):
    entities=raw.get('geometry');constraints=raw.get('constraints',[])
    if not isinstance(entities,list) or not 1<=len(entities)<=64:raise ValueError('A sketch needs1..64 geometry entities.')
    if not isinstance(constraints,list) or len(constraints)>256:raise ValueError('A sketch accepts at most256 constraints.')
    plane=raw.get('plane',{})
    if not isinstance(plane,dict) or set(plane)-{'origin','normal'}:raise ValueError('Sketch plane uses origin and normal.')
    result={'plane':{'origin':vector(plane.get('origin',[0,0,0])),'normal':vector(plane.get('normal',[0,0,1]),direction=True)},'geometry':[],'constraints':[],'require_fully_constrained':raw.get('require_fully_constrained',False)}
    if type(result['require_fully_constrained']) is not bool:raise ValueError('Use a boolean fully constrained requirement.')
    def point(value):
        if not isinstance(value,list) or len(value)!=2:raise ValueError('Sketch coordinates have two dimensions.')
        return [number(n) for n in value]
    known={}
    for geometry in entities:
        if not isinstance(geometry,dict) or geometry.get('type') not in GEOMETRY:raise ValueError('Sketch geometry is line, circle, arc, ellipse or bspline.')
        identifier=geometry.get('id');kind=geometry['type']
        if not isinstance(identifier,str) or not ID.fullmatch(identifier) or identifier in known or identifier in ('origin','x_axis','y_axis'):raise ValueError('Use unique sketch geometry identifiers.')
        if set(geometry)-({'id','type','construction'}|GEOMETRY[kind]):raise ValueError('Unsupported sketch geometry fields.')
        value={'id':identifier,'type':kind,'construction':geometry.get('construction',False)}
        if type(value['construction']) is not bool:raise ValueError('Construction geometry uses a boolean flag.')
        for key in ('start','end','center'):
            if key in GEOMETRY[kind]:value[key]=point(geometry.get(key))
        for key in ('radius','major_radius','minor_radius'):
            if key in GEOMETRY[kind]:value[key]=number(geometry.get(key),True)
        for key in ('start_angle','end_angle','angle'):
            if key in GEOMETRY[kind]:value[key]=number(geometry.get(key,0))
        if kind=='ellipse' and value['major_radius']<value['minor_radius']:raise ValueError('Ellipse major radius must be at least its minor radius.')
        if kind=='bspline':
            poles=geometry.get('poles');knots=geometry.get('knots');degree=geometry.get('degree',3)
            if type(degree) is not int or not 1<=degree<=5 or not isinstance(poles,list) or not degree+1<=len(poles)<=64 or not isinstance(knots,list) or len(knots)!=len(poles)+degree+1:raise ValueError('A nonperiodic B-spline needs valid poles, degree1..5 and its expanded knot vector.')
            weights=geometry.get('weights',[1]*len(poles))
            if not isinstance(weights,list) or len(weights)!=len(poles):raise ValueError('B-spline weights match its poles.')
            value.update(poles=[point(p) for p in poles],degree=degree,knots=[number(n) for n in knots],weights=[number(n,True) for n in weights])
            if any(a>b for a,b in zip(value['knots'],value['knots'][1:])) or value['knots'][0]==value['knots'][-1]:raise ValueError('B-spline knots must be nondecreasing with nonzero range.')
        known[identifier]=kind;result['geometry'].append(value)
    ids=set()
    for constraint in constraints:
        if not isinstance(constraint,dict) or set(constraint)-{'id','type','refs','value','driving'} or constraint.get('type') not in CONSTRAINTS:raise ValueError('Use a supported native sketch constraint.')
        identifier=constraint.get('id');kind=constraint['type'];refs=constraint.get('refs')
        if not isinstance(identifier,str) or not ID.fullmatch(identifier) or identifier in ids:raise ValueError('Use unique sketch constraint identifiers.')
        if not isinstance(refs,list) or not 1<=len(refs)<=3:raise ValueError('A constraint needs1..3 geometry references.')
        normalized=[]
        for ref in refs:
            if not isinstance(ref,dict) or set(ref)-{'entity','point'}:raise ValueError('A sketch reference uses entity and optional point.')
            entity=ref.get('entity');position=ref.get('point')
            if entity not in known and entity not in ('origin','x_axis','y_axis'):raise ValueError('Constraint references an unknown sketch entity.')
            if position is not None and position not in ('start','end','center'):raise ValueError('Sketch point is start, end or center.')
            if position=='center' and known.get(entity) not in ('circle','arc','ellipse') or position in ('start','end') and known.get(entity) not in ('line','arc','bspline'):raise ValueError('That point is unavailable on the selected geometry.')
            normalized.append(dict(ref))
        value={'id':identifier,'type':kind,'refs':normalized,'driving':constraint.get('driving',True)}
        if type(value['driving']) is not bool or not value['driving'] and kind not in DIMENSIONS:raise ValueError('Only dimensions can be reference constraints.')
        if kind in DIMENSIONS:value['value']=number(constraint.get('value'),kind in ('distance','radius','diameter'))
        elif 'value' in constraint:raise ValueError('This geometric constraint has no dimension value.')
        if kind in ('block','radius','diameter') and len(refs)!=1 or kind in ('coincident','point_on_object','parallel','perpendicular','tangent','equal') and len(refs)!=2 or kind=='symmetric' and len(refs)!=3:raise ValueError('The sketch constraint reference count is invalid.')
        ids.add(identifier);result['constraints'].append(value)
    return result
