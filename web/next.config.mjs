import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
	// The preview imports the composition straight from ../render/src (ADR 0801).
	experimental: {externalDir: true},
	webpack(config) {
		// render/ has its own node_modules; look in ours first so React is a single copy.
		config.resolve.modules = [path.join(here, 'node_modules'), ...(config.resolve.modules ?? ['node_modules'])];
		config.resolve.alias['@render'] = path.join(here, '..', 'render', 'src');
		// Caption fonts are imported as files by the composition (render/src/fonts.ts).
		config.module.rules.push({test: /\.woff2$/, type: 'asset/resource', generator: {filename: 'static/media/[name].[hash][ext]'}});
		return config;
	},
};

export default nextConfig;
