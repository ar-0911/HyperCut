// The script of the HyperFrames page (ADR 0032), bundled to hypercut-page.js. Each time HyperFrames seeks (every
// frame of a render, every tick or scrub of the editor's player) the reel's React tree is drawn for that frame,
// and the frame is held until its pictures, fonts and 3D scene are ready.

import React from 'react';
import {flushSync} from 'react-dom';
import {createRoot} from 'react-dom/client';
import {FrameRoot, settled, setStaticBase, type Runtime} from '../frame';
import {HyperCut} from '../HyperCut';
import type {CompositionProps} from '../plan';
import type {PageConfig} from './html';

declare global {
	interface Window {
		__HYPERCUT__?: PageConfig;
		__player?: {isPlaying?: () => boolean};
		__hypercutFrame?: number;
	}
}

type SeekDetail = {time: number; waitUntil?: (p: Promise<unknown>) => void};

function start(config: PageConfig) {
	const el = document.getElementById('hc-app');
	if (!el) throw new Error('hypercut page: no #hc-app');
	setStaticBase(config.staticBase);
	const runtime: Runtime = {
		mode: config.mode,
		fps: config.fps,
		width: config.width,
		height: config.height,
		durationInFrames: config.durationInFrames,
		frames: config.frames,
		staticBase: config.staticBase,
		playing: () => Boolean(window.__player?.isPlaying?.()),
	};
	let props: CompositionProps = config.props;
	let frame = 0;
	const root = createRoot(el);
	const draw = () => {
		window.__hypercutFrame = frame;
		flushSync(() =>
			root.render(
				<FrameRoot runtime={runtime} frame={frame}>
					<HyperCut {...props} />
				</FrameRoot>,
			),
		);
	};
	const pictures = () =>
		Promise.all([...el.querySelectorAll('img')].map((img) => (img.complete && img.naturalWidth > 0 ? null : img.decode().catch(() => null))));
	// Fonts can start loading while a frame is drawn, and pictures appear once fonts lay text out: settle twice.
	const ready = async () => {
		await settled();
		await pictures();
		await document.fonts.ready;
		await settled();
		await pictures();
	};
	window.addEventListener('hf-seek', (e) => {
		const detail = (e as CustomEvent<SeekDetail>).detail;
		frame = Math.max(0, Math.min(config.durationInFrames - 1, Math.round(detail.time * config.fps)));
		draw();
		detail.waitUntil?.(ready());
	});
	// The editor sends edits without reloading the page (the sound is rebuilt with a reload when it changes).
	window.addEventListener('message', (e) => {
		const data = e.data as {type?: string; props?: CompositionProps} | null;
		if (data?.type === 'hypercut:props' && data.props) {
			props = data.props;
			draw();
		}
	});
	draw();
}

if (window.__HYPERCUT__) start(window.__HYPERCUT__);
