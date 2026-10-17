import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
	// The preview imports the composition straight from ../render/src (ADR 0801).
	experimental: {externalDir: true},
	webpack(config) {
		// render/ may have its own node_modules; look in ours first so React and Remotion are single copies.
		config.resolve.modules = [path.join(here, 'node_modules'), ...(config.resolve.modules ?? ['node_modules'])];
		config.resolve.alias['@render'] = path.join(here, '..', 'render', 'src');
		return config;
	},
};

export default nextConfig;
