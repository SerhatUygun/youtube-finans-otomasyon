// Tek bundle ile çok kare render (görsel doğrulama).
// Kullanım: node stills.mjs <compId> <propsJson> <outDir> <frame...>   (cwd: remotion/)
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';
import fs from 'node:fs';
import path from 'node:path';
const root = process.cwd();
const [id, propsFile, outDir, ...frames] = process.argv.slice(2);
const inputProps = JSON.parse(fs.readFileSync(propsFile, 'utf8'));
const serveUrl = await bundle({entryPoint: path.join(root, 'src/auto/index.ts'), publicDir: path.join(root, 'public')});
const composition = await selectComposition({serveUrl, id, inputProps});
fs.mkdirSync(outDir, {recursive: true});
for (const f of frames) {
  const out = path.join(outDir, `f${String(f).padStart(5, '0')}.png`);
  await renderStill({serveUrl, composition, frame: Number(f), output: out, overwrite: true, inputProps});
  console.log(out);
}
