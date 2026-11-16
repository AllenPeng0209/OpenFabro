"""Trusted native Sketcher construction, constraint solving and editable dimensions."""
import ast,math,json,os,traceback
import FreeCAD as App
import Part,Sketcher

V=App.Vector
TYPES={'coincident':'Coincident','horizontal':'Horizontal','vertical':'Vertical','point_on_object':'PointOnObject','parallel':'Parallel','perpendicular':'Perpendicular','tangent':'Tangent','equal':'Equal','symmetric':'Symmetric','distance':'Distance','distance_x':'DistanceX','distance_y':'DistanceY','radius':'Radius','diameter':'Diameter','angle':'Angle','block':'Block'}


def parameters(document,source):
    obj=document.addObject('App::FeaturePython','DesignParameters');obj.Label='Design parameters'
    for name,value in source.get('parameters',{}).items():
        unit=value.get('unit','mm') if isinstance(value,dict) else 'mm';number=value['value'] if isinstance(value,dict) else value
        obj.addProperty({'mm':'App::PropertyLength','deg':'App::PropertyAngle','number':'App::PropertyFloat'}[unit],'p_'+name,'Design parameters');setattr(obj,'p_'+name,number)
    return obj


def expression(value,parameter_object):
    if not isinstance(value,str):return None
    def emit(node):
        if isinstance(node,ast.Expression):return emit(node.body)
        if isinstance(node,ast.Name):return parameter_object.Name+'.p_'+node.id
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):return repr(node.value)
        if isinstance(node,ast.UnaryOp):return ('-' if isinstance(node.op,ast.USub) else '+')+'('+emit(node.operand)+')'
        if isinstance(node,ast.BinOp):return '('+emit(node.left)+{ast.Add:'+',ast.Sub:'-',ast.Mult:'*',ast.Div:'/'}[type(node.op)]+emit(node.right)+')'
        raise ValueError('Unsupported native dimension expression.')
    return emit(ast.parse(value,mode='eval'))


def geometry(item):
    point=lambda p:V(p[0],p[1],0);kind=item['type']
    if kind=='line':return Part.LineSegment(point(item['start']),point(item['end']))
    if kind=='circle':return Part.Circle(point(item['center']),V(0,0,1),item['radius'])
    if kind=='arc':
        a,b=[math.radians(item[k]) for k in ('start_angle','end_angle')]
        if b<=a:b+=math.tau
        return Part.ArcOfCircle(Part.Circle(point(item['center']),V(0,0,1),item['radius']),a,b)
    if kind=='ellipse':
        center=point(item['center']);angle=math.radians(item['angle']);x=V(math.cos(angle),math.sin(angle),0)*item['major_radius'];y=V(-math.sin(angle),math.cos(angle),0)*item['minor_radius'];return Part.Ellipse(center+x,center+y,center)
    curve=Part.BSplineCurve();knots=[];mults=[]
    for knot in item['knots']:
        if knots and knot==knots[-1]:mults[-1]+=1
        else:knots.append(knot);mults.append(1)
    curve.buildFromPolesMultsKnots([point(p) for p in item['poles']],mults,knots,False,item['degree'],item['weights']);return curve


def build(document,item,source,parameter_object):
    sketch=document.addObject('Sketcher::SketchObject',item['id']);sketch.Label=item.get('label',item['id']);plane=item['plane'];sketch.Placement=App.Placement(V(*plane['origin']),App.Rotation(V(0,0,1),V(*plane['normal'])))
    indices={}
    for value in item['geometry']:indices[value['id']]=sketch.addGeometry(geometry(value),value['construction'])
    source_constraints={c['id']:c for c in source.get('constraints',[])};constraint_ids=[]
    for value in item['constraints']:
        args=[]
        for ref in value['refs']:
            entity=ref['entity']
            if entity=='origin':args.extend([-1,1]);continue
            args.append({'x_axis':-1,'y_axis':-2}.get(entity,indices.get(entity)))
            if ref.get('point'):args.append({'start':1,'end':2,'center':3}[ref['point']])
        if 'value' in value:args.append(math.radians(value['value']) if value['type']=='angle' else value['value'])
        try:
            index=sketch.addConstraint(Sketcher.Constraint(TYPES[value['type']],*args));sketch.renameConstraint(index,value['id']);constraint_ids.append(index)
            if not value['driving']:sketch.setDriving(index,False)
            elif 'value' in value:
                formula=expression(source_constraints[value['id']].get('value'),parameter_object)
                if formula:sketch.setExpression('Constraints.'+value['id'],formula)
        except Exception as error:raise ValueError('Sketch constraint '+value['id']+' failed: '+str(error)) from error
    document.recompute();code=sketch.solve();conflicting=list(sketch.ConflictingConstraints);redundant=list(sketch.RedundantConstraints);malformed=list(sketch.MalformedConstraints)
    if code!=0 or conflicting or redundant or malformed:
        names={index+1:value['id'] for value,index in zip(item['constraints'],constraint_ids)}
        raise ValueError('Sketch constraint solve failed: '+str({'code':code,'conflicting':[names.get(i,str(i)) for i in conflicting],'redundant':[names.get(i,str(i)) for i in redundant],'malformed':[names.get(i,str(i)) for i in malformed]}))
    if item['require_fully_constrained'] and sketch.DoF!=0:raise ValueError('Sketch remains underconstrained: '+str(sketch.DoF)+' degrees of freedom.')
    rows=[];point_count=0
    for value in item['geometry']:
        index=indices[value['id']];native=sketch.Geometry[index];kind=value['type'];row={'id':value['id'],'type':kind,'native_index':index,'construction':value['construction']}
        if kind=='line':row.update(start=[native.StartPoint.x,native.StartPoint.y],end=[native.EndPoint.x,native.EndPoint.y])
        elif kind in ('circle','arc','ellipse'):row.update(center=[native.Center.x,native.Center.y])
        if kind in ('circle','arc'):row['radius']=native.Radius
        if kind=='ellipse':row.update(major_radius=native.MajorRadius,minor_radius=native.MinorRadius)
        if kind=='bspline':row['poles']=[[p.x,p.y] for p in native.getPoles()]
        points=native.toShape().discretize(Deflection=.05);point_count+=len(points)
        if point_count>100000:raise ValueError('Sketch preview exceeds the native curve point budget.')
        row['points']=[[p.x,p.y] for p in points];rows.append(row)
    constraints=[]
    for value,index in zip(item['constraints'],constraint_ids):
        native=sketch.Constraints[index];row={**value,'native_index':index,'error':sketch.calculateConstraintError(index)}
        if 'value' in row:row['solved_value']=math.degrees(native.Value) if value['type']=='angle' else native.Value
        constraints.append(row)
    shape=Part.makeFace(sketch.Shape.Wires,'Part::FaceMakerCheese') if sketch.Shape.Wires and all(wire.isClosed() for wire in sketch.Shape.Wires) else sketch.Shape.copy()
    return sketch,shape,{'dof':sketch.DoF,'fully_constrained':bool(sketch.FullyConstrained),'solver_code':code,'conflicting':conflicting,'redundant':redundant,'malformed':malformed,'geometry':rows,'constraints':constraints,'plane':plane,'closed_wires':sum(w.isClosed() for w in sketch.Shape.Wires),'native_type':sketch.TypeId}


if os.environ.get('OPENFABRO_SKETCH_JOB'):
    from pathlib import Path
    job=json.loads(Path(os.environ['OPENFABRO_SKETCH_JOB']).read_text());doc=App.newDocument('OpenFabroSketchPreview')
    try:
        obj,shape,proof=build(doc,job['feature'],job['source_feature'],parameters(doc,job['source']));result={'ok':True,'sketch':proof}
    except Exception as error:result={'ok':False,'error':str(error),'trace':traceback.format_exc()}
    finally:App.closeDocument(doc.Name)
    Path(job['result']).write_text(json.dumps(result))
