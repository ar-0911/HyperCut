import path from 'node:path';
import {defineConfig} from 'vitest/config';

export default defineConfig({
	resolve: {alias: {'@render': path.resolve(__dirname, '../render/src'), '@': path.resolve(__dirname)}},
	test: {include: ['lib/**/*.test.ts']},
});
