// Görsel denetçi için hızlı kare çekimi: tek bundle, çok renderStill (CLI'de her still yeniden bundle ediyordu).
// node scripts/qa_stills.mjs <jobs.json>
//   jobs.json: [{"props": "<props.json>", "comp": "AutoShowreel", "shots": [{"frame": 120, "out": "<jpg>"}]}]
import fs from 'node:fs';
import path from 'node:path';
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';

const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const serveUrl = await bundle({entryPoint: path.resolve('src/auto/index.ts'), publicDir: path.resolve('public')});
for (const job of jobs) {
  const inputProps = JSON.parse(fs.readFileSync(job.props, 'utf8'));
  const composition = await selectComposition({serveUrl, id: job.comp, inputProps});
  for (const s of job.shots) {
    await renderStill({composition, serveUrl, output: s.out, frame: Math.min(s.frame, composition.durationInFrames - 1), inputProps,
      imageFormat: 'jpeg', jpegQuality: 82, scale: job.scale ?? (job.comp === 'AutoReel' ? 0.4 : 0.5), overwrite: true,
      chromiumOptions: {gl: 'angle'}}); // 3D (WebGL) şablonları için
    process.stdout.write(`still ${path.basename(s.out)}\n`);
  }
}
