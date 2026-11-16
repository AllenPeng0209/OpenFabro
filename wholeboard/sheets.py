"""Project-owned schematic page hierarchy and electrical boundary ports."""
from __future__ import annotations
import math
import re


def component_sheet(component):
    value=component.get('sheet') if 'sheet' in component else component.get('block')
    return re.sub(r'[^A-Za-z0-9_-]+','_',str(value)).strip('_') if value else ''


def definitions(spec):
    editor=spec.get('editor') or {};declared=editor.get('sheets',{})
    if declared is None:declared={}
    if not isinstance(declared,dict):raise ValueError('Sheet definitions must be an object.')
    result={key:dict(value) if isinstance(value,dict) else value for key,value in declared.items()}
    for component in spec.get('components',[]):
        key=component_sheet(component)
        if key and key not in result:result[key]={'title':key,'parent':''}
    from . import terminals
    for key,ports in terminals.declarations(spec).items():
        if not key:continue
        value=result[key];value['ports']=dict(value.get('ports',{}))
        for name,port in ports.items():
            if name in value['ports'] and value['ports'][name].get('net')!=port['net']:raise ValueError('A terminal designator is already used by another sheet port.')
            value['ports'][name]={**value['ports'].get(name,{}),**port}
    return result


def order(spec):
    defs=definitions(spec);remaining=set(defs);ordered=[]
    while remaining:
        ready=[key for key in defs if key in remaining and not defs[key].get('parent','') in remaining]
        if not ready:raise ValueError('Schematic sheets cannot form a parent cycle.')
        for key in ready:ordered.append(key);remaining.remove(key)
    return ordered


def validate(spec):
    from .terminals import DIRECTIONS,SIDES
    defs=definitions(spec)
    if len(defs)>200:raise ValueError('Choose at most 200 schematic sheets.')
    declared=(spec.get('editor') or {}).get('sheets') or {}
    finite=lambda value:isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and abs(value)<=1_000_000
    for key,value in defs.items():
        if not isinstance(value,dict):raise ValueError('Each schematic sheet must contain properties.')
        if key in declared and (not isinstance(key,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',key)):
            raise ValueError('A sheet ID starts with a letter and uses up to 64 letters, digits, dashes or underscores.')
        title=value.get('title',key)
        if not isinstance(title,str) or not title.strip() or len(title)>120 or not title.isprintable():raise ValueError('A sheet title needs printable text, up to 120 characters.')
        parent=value.get('parent','')
        if not isinstance(parent,str) or parent and parent not in defs:raise ValueError('The parent sheet does not exist.')
        for field in ('position','size'):
            point=value.get(field)
            if point is not None and (not isinstance(point,list) or len(point)!=2 or not all(finite(v) for v in point)):raise ValueError('Sheet positions and sizes need finite pairs.')
        if value.get('size') and any(v<60 or v>10000 for v in value['size']):raise ValueError('Sheet dimensions must be between 60 and 10000 schematic units.')
        ports=value.get('ports',{})
        if not isinstance(ports,dict) or len(ports)>1000:raise ValueError('Sheet ports must be a bounded object.')
        nets={net['name'] for net in spec.get('nets',[])}
        numbers=set()
        for name,port in ports.items():
            if not isinstance(name,str) or not name or len(name)>100 or not isinstance(port,dict) or port.get('net') not in nets:raise ValueError('Each sheet port needs a name and an existing electrical net.')
            if port.get('direction','passive') not in DIRECTIONS or port.get('side','left') not in SIDES:raise ValueError('Choose a supported port direction and pin orientation.')
            if 'number' in port:
                number=port['number']
                if not isinstance(number,str) or not number or len(number)>32 or not number.isprintable() or number in numbers:raise ValueError('Sheet port pin numbers must be unique printable strings.')
                numbers.add(number)
            if not finite(port.get('order',0)):raise ValueError('Sheet port order must be a bounded finite number.')
            for field in ('group','section'):
                text=port.get(field,'')
                if not isinstance(text,str) or len(text)>80 or text and not text.isprintable():raise ValueError('Sheet port groups and sections need bounded printable text.')
    order(spec)


def boundaries(spec):
    """Nets crossing each child-parent edge, including descendants with no local parts."""
    defs=definitions(spec);ordered=order(spec);subtrees={key:{key} for key in defs}
    for key in reversed(ordered):
        parent=defs[key].get('parent','')
        if parent:subtrees[parent]|=subtrees[key]
    locations={component['ref']:component_sheet(component) for component in spec.get('components',[])}
    occurrences={net['name']:{locations.get(pin.split('.',1)[0],'') for pin in net.get('pins',[])} for net in spec.get('nets',[])}
    # A declared terminal is also an electrical endpoint on its parent's page.
    # This carries an ancestor's interface through otherwise isolated descendants.
    for key,definition in defs.items():
        for port in definition.get('ports',{}).values():occurrences.setdefault(port['net'],set()).add(definition.get('parent',''))
    ports={key:{} for key in defs}
    for key in defs:
        declared=defs[key].get('ports',{});explicit_nets={port['net'] for port in declared.values()}
        for net,where in occurrences.items():
            if net not in explicit_nets and where&subtrees[key] and where-subtrees[key]:ports[key][net]={'net':net}
        ports[key].update(declared)
    return ports
