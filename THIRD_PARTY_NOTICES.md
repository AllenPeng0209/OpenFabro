# Third-party notices

OpenFabro is distributed under GPL-3.0-or-later. Third-party components retain their original
licenses and copyright notices. This file identifies the upstream foundation and assets bundled
with the application; it does not replace their license texts.

## Engineering foundation

OpenFabro is derived from [WholeBoard](https://github.com/DingoOz/WholeBoard), beginning with
revision `1471c54c2f55e3e2c1ae75e5f7ff23bfe77f84fe`. The upstream Git history, GPL license,
and applicable source notices are retained. OpenFabro includes subsequent work on the interactive
workbench, mechanical workflows, project tools, and production preparation.

## Bundled browser assets

| Component | License | Included notice |
| --- | --- | --- |
| Three.js | MIT | [THREE-LICENSE.txt](wholeboard/web/vendor/THREE-LICENSE.txt) |
| Marked | MIT | [MARKED-LICENSE.txt](wholeboard/web/vendor/MARKED-LICENSE.txt) |
| DOMPurify | Apache-2.0 OR MPL-2.0 | [DOMPURIFY-LICENSE.txt](wholeboard/web/vendor/DOMPURIFY-LICENSE.txt) |
| Roboto fonts | Apache-2.0 | [Font license](wholeboard/web/fonts/LICENSE.txt) |

Browser dependency versions are recorded in `package.json` and `package-lock.json`.
`npm run vendor` refreshes the bundled libraries and their notices from installed dependencies.

## External engineering tools

KiCad, TraceMaker, ngspice, FreeCAD, Open CASCADE, PlatformIO, and other installed dependencies
are separate projects with their own licenses. Their use by OpenFabro does not imply endorsement
or transfer of their trademarks. Supplier and AI provider names identify integrations or handoff
targets and do not imply a commercial partnership.

Third-party user-interface reference captures used during development are excluded from the
published source. The README screenshots show OpenFabro's own local interface.
