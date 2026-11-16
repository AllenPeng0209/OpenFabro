#3D navigation reference

Read-only public On Air R2 demo observed on2026-11-14 at1440×1000. Directly inspected screenshots:
flux-navigation-cube-before.png, flux-navigation-home.png, flux-navigation-flip.png and
flux-navigation-camera-options.png under test-results. The cube is part of the single3D canvas,
not individual DOM buttons. Its ring is about156px across, centred1346×167 in this viewport.

Home changes the captured bottom view to top/left/back isometric. The lower-right turn control then
shows top/right/front, retaining the top hemisphere. Face labels track the current camera. The
camera button is32px at1404×261. Its actual radial buttons select Blueprint, X-ray, Solid, Realistic
and perspective/orthographic; centres relative to the cube centre are approximately(-96,-58),
(-112,0),(-98,56),(-56,98),(0,112). The open/close camera label changes with its state.

The [official3D documentation](https://docs.flux.ai/reference/3d-view) describes material/projection
and camera controls. [Mobile guidance](https://docs.flux.ai/Introduction/use-flux-on-mobile) specifies
Show/Hide view cube and selecting a face. Our narrow desktop-browser viewport observation showed the
chat/project switch, but did not independently establish the touch-device cube toggle pixels.

Implement all26axis-combination view directions and genuine camera rotation, not a static cube.
GPU and software should share one world basis. Exact-pole views need a defined up vector and roll.
Frame model should preserve chosen direction. Save no circuit edits; preserve per-owner pose through
native replacement and guard old controls. Keep Markup and keyboard ownership intact.
