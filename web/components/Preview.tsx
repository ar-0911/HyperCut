'use client';

// The editor's preview (ADR 0032): the reel's HyperFrames page, played by HyperFrames' own player, the same page
// the render draws. Edits reach the page as messages, so the picture updates in place; when the sound changes (a
// cut moved, music added) the page is rebuilt and the player goes back to where it was.

import {forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState} from 'react';
import type {CompositionProps} from '@render/plan';
import {compositionHtml, soundOf} from '@render/hf/html';
import {calculateMetadata} from '@render/HyperCut';

/** What the timeline, the on-screen list and the shortcuts use to follow and drive the preview. */
export type PreviewRef = {
	getCurrentFrame: () => number;
	seekTo: (frame: number) => void;
	toggle: () => void;
	isPlaying: () => boolean;
	addEventListener: (type: 'frameupdate' | 'seeked', fn: (e: {detail: {frame: number}}) => void) => void;
	removeEventListener: (type: 'frameupdate' | 'seeked', fn: (e: {detail: {frame: number}}) => void) => void;
};

type PlayerElement = HTMLElement & {
	play: () => void;
	pause: () => void;
	seek: (t: number) => void;
	currentTime: number;
	duration: number;
	paused: boolean;
};

/** The player and page scripts, copied into public/hf by scripts/hf-assets.mjs. */
const ASSETS = '/hf';
let playerScript: Promise<void> | null = null;
function loadPlayer(): Promise<void> {
	if (typeof window === 'undefined') return Promise.resolve();
	if (customElements.get('hyperframes-player')) return Promise.resolve();
	playerScript ??= new Promise<void>((resolve, reject) => {
		const s = document.createElement('script');
		s.src = `${ASSETS}/hyperframes-player.js`;
		s.onload = () => resolve();
		s.onerror = () => reject(new Error('could not load the HyperFrames player'));
		document.head.appendChild(s);
	});
	return playerScript;
}

const Preview = forwardRef<PreviewRef, {props: CompositionProps; style?: React.CSSProperties}>(function Preview({props, style}, ref) {
	const el = useRef<PlayerElement | null>(null);
	const [ready, setReady] = useState(false);
	const listeners = useRef(new Map<string, Set<(e: {detail: {frame: number}}) => void>>());
	const meta = useMemo(() => calculateMetadata({props}), [props]);
	const fps = meta.fps;

	// The sound only changes with the cuts, music and timing; rebuilding the page is kept for those changes.
	const audio = useMemo(() => {
		try {
			return soundOf(props, '');
		} catch (e) {
			console.warn('preview sound failed', e);
			return [];
		}
	}, [props]);
	const pageKey = JSON.stringify([audio, meta.durationInFrames, meta.width, meta.height, fps, Boolean(props.overlaysOnly)]);
	const latestProps = useRef(props);
	latestProps.current = props;
	const html = useMemo(() => {
		const origin = typeof window === 'undefined' ? '' : window.location.origin;
		return compositionHtml({
			config: {mode: 'preview', props: latestProps.current, ...meta, staticBase: ''},
			audio,
			scripts: [`${origin}${ASSETS}/hypercut-page.js`],
		});
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [pageKey]);

	useEffect(() => {
		loadPlayer().then(() => setReady(true), (e) => console.error(e));
	}, []);

	const emit = (type: string) => {
		const p = el.current;
		if (!p) return;
		const detail = {frame: Math.round((p.currentTime || 0) * fps)};
		for (const fn of listeners.current.get(type) ?? []) fn({detail});
	};

	// A new page: go back to where the player was once it has loaded.
	const resume = useRef(0);
	useEffect(() => {
		const p = el.current;
		if (!ready || !p) return;
		resume.current = p.currentTime || resume.current;
		const frameOf = () => p.shadowRoot?.querySelector('iframe') ?? null;
		const oldDoc = frameOf()?.contentDocument ?? null;
		p.setAttribute('srcdoc', html);
		let tries = 0;
		const timer = setInterval(() => {
			const doc = frameOf()?.contentDocument ?? null;
			const loaded = doc !== null && doc !== oldDoc && doc.readyState === 'complete' && p.duration > 0;
			if (loaded || ++tries > 200) {
				clearInterval(timer);
				// Edits made while the page loaded.
				frameOf()?.contentWindow?.postMessage({type: 'hypercut:props', props: latestProps.current}, '*');
				if (resume.current > 0) p.seek(Math.min(resume.current, p.duration - 1 / fps));
				emit('seeked');
			}
		}, 50);
		return () => clearInterval(timer);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [ready, html]);

	// Every other edit: send it to the page.
	useEffect(() => {
		const frame = el.current?.shadowRoot?.querySelector('iframe')?.contentWindow;
		frame?.postMessage({type: 'hypercut:props', props}, '*');
	}, [props]);

	useEffect(() => {
		const p = el.current;
		if (!ready || !p) return;
		const onTime = () => emit('frameupdate');
		p.addEventListener('timeupdate', onTime);
		return () => p.removeEventListener('timeupdate', onTime);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [ready, fps]);

	useImperativeHandle(
		ref,
		() => ({
			getCurrentFrame: () => Math.round((el.current?.currentTime ?? 0) * fps),
			seekTo: (frame) => {
				el.current?.seek(Math.max(0, frame) / fps);
				emit('seeked');
			},
			toggle: () => {
				const p = el.current;
				if (!p) return;
				if (p.paused) p.play();
				else p.pause();
			},
			isPlaying: () => Boolean(el.current && !el.current.paused),
			addEventListener: (type, fn) => {
				const set = listeners.current.get(type) ?? new Set();
				set.add(fn);
				listeners.current.set(type, set);
			},
			removeEventListener: (type, fn) => {
				listeners.current.get(type)?.delete(fn);
			},
		}),
		// eslint-disable-next-line react-hooks/exhaustive-deps
		[fps],
	);

	if (!ready) return <div className="preview-loading" style={{aspectRatio: `${meta.width} / ${meta.height}`, ...style}} />;
	return (
		// @ts-expect-error: a custom element
		<hyperframes-player
			ref={el}
			controls=""
			// The runtime from our own server, never HyperFrames' CDN: the preview works offline.
			runtime-src={`${ASSETS}/hyperframe.runtime.js`}
			width={meta.width}
			height={meta.height}
			style={{display: 'block', width: '100%', aspectRatio: `${meta.width} / ${meta.height}`, ...style}}
		/>
	);
});

export default Preview;
