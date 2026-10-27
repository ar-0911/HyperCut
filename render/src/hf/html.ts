// The HyperFrames composition a reel is (ADR 0032): one page, the same for the editor's preview and the render.
// The page holds the plan, the sound as HyperFrames <audio> clips, and the script that draws each frame
// (page.tsx, bundled to hypercut-page.js). Built in Node by the render script and in the browser by the editor.

import {audioClips, collect, type AudioClip} from '../collect';
import type {FrameDir, Mode} from '../frame';
import {calculateMetadata, HyperCut} from '../HyperCut';
import {setStaticBase} from '../frame';
import type {CompositionProps} from '../plan';
import React from 'react';

/** What the page script reads from window.__HYPERCUT__. */
export type PageConfig = {
	mode: Exclude<Mode, 'collect'>;
	props: CompositionProps;
	fps: number;
	width: number;
	height: number;
	durationInFrames: number;
	staticBase: string;
	frames?: Record<string, FrameDir>;
};

export const COMPOSITION_ID = 'hypercut';

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
/** JSON that is safe inside a <script> element. */
const scriptJson = (v: unknown) => JSON.stringify(v).replace(/</g, '\\u003c').replace(/[\u2028\u2029]/g, (c) => `\\u${c.charCodeAt(0).toString(16)}`);

/** One sound clip as a HyperFrames <audio> element. */
export function audioTag(c: AudioClip, url: (src: string) => string = (s) => s): string {
	const automation = c.volume.length > 1 ? ` data-automation='${esc(JSON.stringify({version: 1, lanes: [{target: 'volume', points: c.volume}]}))}'` : '';
	const gain = c.volume.length === 1 ? c.volume[0].v : 1;
	const rate = Math.abs(c.rate - 1) > 1e-6 ? ` data-playback-rate="${c.rate}"` : '';
	return (
		`<audio id="${c.id}" class="clip" src="${esc(url(c.src))}" data-start="${c.start}" data-duration="${c.duration}"` +
		` data-media-start="${c.mediaStart}" data-volume="${gain}"${rate}${automation} preload="auto"></audio>`
	);
}

/** The reel's sound: every frame drawn once, without a page (see collect.tsx). */
export function soundOf(props: CompositionProps, staticBase: string, durations: Record<string, number> = {}): AudioClip[] {
	const meta = calculateMetadata({props});
	setStaticBase(staticBase);
	const usage = collect(() => React.createElement(HyperCut, props), meta);
	return audioClips(usage.sounds, meta.fps, durations);
}

export function compositionHtml({
	config,
	audio,
	scripts,
	head = '',
	audioUrl,
}: {
	config: PageConfig;
	audio: AudioClip[];
	/** Script URLs, in order (the HyperFrames runtime in a preview, then the page script). */
	scripts: string[];
	head?: string;
	audioUrl?: (src: string) => string;
}): string {
	const {width, height, fps, durationInFrames} = config;
	const transparent = Boolean(config.props.overlaysOnly);
	return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body { margin: 0; padding: 0; background: ${transparent ? 'transparent' : '#000'}; }
#root { position: relative; width: ${width}px; height: ${height}px; overflow: hidden; }
#hc-app { position: absolute; left: 0; top: 0; width: ${width}px; height: ${height}px; }
</style>
${head}
</head>
<body>
<div id="root" data-composition-id="${COMPOSITION_ID}" data-start="0" data-duration="${durationInFrames / fps}" data-width="${width}" data-height="${height}" data-fps="${fps}">
<div id="hc-app"></div>
${audio.map((c) => audioTag(c, audioUrl)).join('\n')}
</div>
<script>window.__HYPERCUT__ = ${scriptJson(config)};</script>
${scripts.map((s) => `<script src="${esc(s)}"></script>`).join('\n')}
</body>
</html>
`;
}
