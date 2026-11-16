import { mkdir, copyFile } from 'node:fs/promises';
const destination = new URL('../wholeboard/web/vendor/', import.meta.url);
await mkdir(destination, { recursive: true });
const files = {
  'three/build/three.module.js': 'three.module.js',
  'three/build/three.core.js': 'three.core.js',
  'three/LICENSE': 'THREE-LICENSE.txt',
  'marked/lib/marked.esm.js': 'marked.mjs',
  'marked/LICENSE': 'MARKED-LICENSE.txt',
  'dompurify/dist/purify.es.mjs': 'purify.mjs',
  'dompurify/LICENSE': 'DOMPURIFY-LICENSE.txt',
};
for (const [source, target] of Object.entries(files)) {
  await copyFile(new URL(`../node_modules/${source}`, import.meta.url), new URL(target, destination));
}
process.stdout.write('Browser libraries and licences bundled for offline use.\n');
