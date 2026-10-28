// Bundles the renderer (ADR 0032): the page script HyperFrames runs (dist/hypercut-page.js, for the browser) and
// the render CLI (dist/render.mjs, for Node). Fonts are inlined, so the page needs no network.
//
//   node scripts/build.mjs           both
//   node scripts/build.mjs --page    the page script only (the editor's preview)

import {build} from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const EXTENSIONS = ['.ts', '.tsx', '.mjs', '.js', '.json'];

// src/ has files whose names differ only in case (brand.ts and Brand.tsx): resolve our own relative imports by
// exact name, the way webpack and Vite do.
const exactCase = {
	name: 'exact-case',
	setup(b) {
		b.onResolve({filter: /^\.\.?\//}, (args) => {
			if (!args.resolveDir.startsWith(root) || args.resolveDir.includes('node_modules')) return undefined;
			const base = path.resolve(args.resolveDir, args.path);
			const dir = path.dirname(base);
			if (!fs.existsSync(dir)) return undefined;
			const names = new Set(fs.readdirSync(dir));
			for (const ext of ['', ...EXTENSIONS]) if (names.has(path.basename(base) + ext) && fs.statSync(base + ext).isFile()) return {path: base + ext};
			return undefined;
		});
	},
};

const common = {bundle: true, resolveExtensions: EXTENSIONS, plugins: [exactCase], loader: {'.woff2': 'dataurl'}, jsx: 'automatic', logLevel: 'warning', legalComments: 'none'};

const page = build({
	...common,
	entryPoints: [path.join(root, 'src/hf/page.tsx')],
	outfile: path.join(root, 'dist/hypercut-page.js'),
	platform: 'browser',
	format: 'iife',
	target: 'chrome110',
	minify: true,
	define: {'process.env.NODE_ENV': '"production"'},
});

const cli = process.argv.includes('--page')
	? null
	: build({
			...common,
			entryPoints: [path.join(root, 'scripts/render.ts')],
			outfile: path.join(root, 'dist/render.mjs'),
			platform: 'node',
			format: 'esm',
			target: 'node22',
			define: {'process.env.NODE_ENV': '"production"'},
			// Packages with their own binaries or that read files next to themselves stay outside the bundle.
			external: ['hyperframes', 'esbuild'],
			banner: {js: "import {createRequire as __hcRequire} from 'node:module'; const require = __hcRequire(import.meta.url);"},
		});

await Promise.all([page, cli]);
