Generated locally with literal coordinates by test-results/drawing-import-fixtures.py.
No production parser determines expected dimensions or areas.

rounded_plate.dxf/.svg: 40×24 mm, R2 external corners, two R2 holes at10/12 and30/12.
Area is944−4*pi mm². DXF uses LWPOLYLINE bulges, separate CIRCLE entities, cut/hole layers,
an open reference line and text annotation. SVG uses exact arcs, physical mm viewport,
even-odd fill and a10:1 viewBox. SVG Y-down maps to negative native Y.

inch_multi.dxf: 2×1 inch rectangle, R0.125 hole, separate1×1 inch island at x3.
blocks.dxf: repeated10×6 rectangle/R1 hole; first copy scaled2×1 then rotated90° at7/9,
so its ellipse cutout area is2*pi and its bounds are min1/9,size6×20. Second at40/9.

bezier.svg and bezier_spline.dxf: cubic controls0/0,0/10,10/10,10/0 plus closing line;
exact enclosed area60 mm², bounding size10×7.5. Nonzero/evenoddSVG has same-winding
nested rectangles whose filled areas are800/600 respectively. Transformed SVG has
translate/rotate/nonuniform scale, expected area100−2*pi. Open curves never define a solid.
