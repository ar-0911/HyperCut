// Copies what the preview loads into public/hf (ADR 0032): HyperFrames' player and page runtime, and the reel's
// page script built from ../render (the same script the render draws frames with).

import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const web = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const render = path.resolve(web, '..', 'render');
const hf = path.join(render, 'node_modules', 'hyperframes', 'dist');
if (!fs.existsSync(hf)) throw new Error(`HyperFrames is not installed in ${render} (run npm ci there)`);
execFileSync(process.execPath, [path.join(render, 'scripts', 'build.mjs'), '--page'], {stdio: 'inherit'});
const out = path.join(web, 'public', 'hf');
fs.mkdirSync(out, {recursive: true});
fs.copyFileSync(path.join(hf, 'hyperframes-player.global.js'), path.join(out, 'hyperframes-player.js'));
fs.copyFileSync(path.join(hf, 'hyperframe.runtime.iife.js'), path.join(out, 'hyperframe.runtime.js'));
fs.copyFileSync(path.join(render, 'dist', 'hypercut-page.js'), path.join(out, 'hypercut-page.js'));
console.log(`preview scripts in ${path.relative(web, out)}`);
