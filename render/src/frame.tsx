// The frame runtime (ADR 0032): the small set of timeline primitives HyperCut's components are written against
// (the current frame, sequences, freezes, interpolation, springs, video, audio, pictures), without Remotion.
//
// One React tree draws one frame. The HyperFrames page (hf/page.tsx) mounts it and draws the frame each time
// HyperFrames seeks; the dry run (collect.tsx) draws every frame once to learn which video frames and sounds the
// reel needs. How a video is drawn depends on where the tree runs:
//
//   render   an <img> of the exact frame, extracted beforehand by scripts/render.ts (no seeking a <video>)
//   preview  a muted <video> kept in step with the editor's player
//   collect  nothing: the frame and the sound it plays are recorded instead
//
// Sound never comes from the tree: the dry run turns what was recorded into HyperFrames <audio> clips.

import React, {createContext, useContext, useLayoutEffect, useRef} from 'react';

export type Mode = 'render' | 'preview' | 'collect';

/** Where the frames of one video file were extracted to: `${dir}/${index}.${ext}`, index = round(seconds * fps). */
export type FrameDir = {dir: string; fps: number; ext: 'jpg' | 'png'};

/** One video frame or one frame of sound a drawn frame asked for (collect mode). */
export type MediaUse = {
	src: string;
	/** Output frame (absolute) this was drawn on. */
	frame: number;
	/** Seconds into the source file. */
	seconds: number;
	/** Seconds per output frame the source advances (playback rate / fps). */
	step: number;
	/** 0 when silent; frozen media and muted video are recorded as silent. */
	volume: number;
	/** The file's frames are needed (a video); false for sound only. */
	picture: boolean;
	transparent?: boolean;
	loop?: boolean;
};

export type Runtime = {
	mode: Mode;
	fps: number;
	width: number;
	height: number;
	durationInFrames: number;
	/** Prefix for staticFile() names (the folder the render serves, or the API in the editor). */
	staticBase?: string;
	/** render: where each source's frames are. */
	frames?: Record<string, FrameDir>;
	/** collect: what each drawn frame uses. */
	record?: (use: MediaUse) => void;
	/** preview: whether the player is playing, so videos play instead of being seeked. */
	playing?: () => boolean;
};

type Timeline = {
	/** The frame the children see. */
	frame: number;
	/** Absolute output frame being drawn. */
	absolute: number;
	frozen: boolean;
};

const RuntimeContext = createContext<Runtime>({mode: 'preview', fps: 30, width: 1080, height: 1920, durationInFrames: 1});
const TimelineContext = createContext<Timeline>({frame: 0, absolute: 0, frozen: false});

/** Draws `children` as frame `frame` of the reel. */
export const FrameRoot: React.FC<{runtime: Runtime; frame: number; children: React.ReactNode}> = ({runtime, frame, children}) => (
	<RuntimeContext.Provider value={runtime}>
		<TimelineContext.Provider value={{frame, absolute: frame, frozen: false}}>{children}</TimelineContext.Provider>
	</RuntimeContext.Provider>
);

export const useCurrentFrame = (): number => useContext(TimelineContext).frame;
export const useRuntime = (): Runtime => useContext(RuntimeContext);
export const useVideoConfig = () => {
	const {fps, width, height, durationInFrames} = useContext(RuntimeContext);
	return {fps, width, height, durationInFrames};
};

/** Children see frames counted from `from`, and only while 0 <= frame < durationInFrames. */
export const Sequence: React.FC<{from?: number; durationInFrames?: number; layout?: 'none' | 'absolute-fill'; children?: React.ReactNode}> = ({
	from = 0,
	durationInFrames = Infinity,
	layout = 'absolute-fill',
	children,
}) => {
	const parent = useContext(TimelineContext);
	const frame = parent.frame - from;
	if (frame < 0 || frame >= durationInFrames) return null;
	const inner = <TimelineContext.Provider value={{...parent, frame}}>{children}</TimelineContext.Provider>;
	return layout === 'none' ? inner : <AbsoluteFill>{inner}</AbsoluteFill>;
};

/** Children are held at `frame`: animation stops, video shows that one frame, sound stops. */
export const Freeze: React.FC<{frame: number; children?: React.ReactNode}> = ({frame, children}) => {
	const parent = useContext(TimelineContext);
	return <TimelineContext.Provider value={{...parent, frame, frozen: true}}>{children}</TimelineContext.Provider>;
};

export const AbsoluteFill = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({style, ...rest}, ref) => (
	<div
		ref={ref}
		{...rest}
		style={{position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, width: '100%', height: '100%', display: 'flex', flexDirection: 'column', ...style}}
	/>
));
AbsoluteFill.displayName = 'AbsoluteFill';

let staticBase = '';
/** A file the reel serves next to the video. */
export const staticFile = (name: string): string => `${staticBase}${name.split('/').map(encodeURIComponent).join('/')}`;
export const setStaticBase = (base: string) => {
	staticBase = base;
};

/** A picture. Drawing waits until it is decoded (hf/page.tsx). */
export const Img: React.FC<React.ImgHTMLAttributes<HTMLImageElement>> = (props) => {
	const {mode} = useContext(RuntimeContext);
	if (mode === 'collect') return null;
	// eslint-disable-next-line jsx-a11y/alt-text
	return <img {...props} decoding="sync" />;
};

// ---- pending work a frame waits for (fonts, 3D) ----

const pending = new Set<Promise<unknown>>();

/** Hold the frame until `promise` settles. */
export function waitFor<T>(promise: Promise<T>): Promise<T> {
	const p = promise.finally(() => pending.delete(p));
	pending.add(p);
	return p;
}

/** Everything a drawn frame is still waiting for. */
export const settled = (): Promise<unknown> => Promise.allSettled([...pending]);

const handles = new Map<number, () => void>();
let nextHandle = 0;
/** Hold drawing until continueRender(handle) (fonts loading). */
export function delayRender(_label?: string): number {
	const id = nextHandle++;
	waitFor(new Promise<void>((resolve) => handles.set(id, resolve)));
	return id;
}
export function continueRender(handle: number): void {
	handles.get(handle)?.();
	handles.delete(handle);
}

// ---- interpolation ----

type Extrapolate = 'extend' | 'clamp' | 'identity' | 'wrap';
export type InterpolateOptions = {extrapolateLeft?: Extrapolate; extrapolateRight?: Extrapolate; easing?: (t: number) => number};

/** Map `input` from `inputRange` onto `outputRange` piecewise linearly (both ranges the same length, input rising). */
export function interpolate(input: number, inputRange: readonly number[], outputRange: readonly number[], options: InterpolateOptions = {}): number {
	if (inputRange.length !== outputRange.length || inputRange.length < 2) throw new Error('interpolate: ranges must have the same length, at least 2');
	for (let i = 1; i < inputRange.length; i++) if (!(inputRange[i] > inputRange[i - 1])) throw new Error('interpolate: inputRange must be strictly increasing');
	const {extrapolateLeft = 'extend', extrapolateRight = 'extend', easing = (t: number) => t} = options;
	let i = 1;
	while (i < inputRange.length - 1 && input > inputRange[i]) i++;
	const [a, b] = [inputRange[i - 1], inputRange[i]];
	const [c, d] = [outputRange[i - 1], outputRange[i]];
	let x = input;
	if (x < a) {
		if (extrapolateLeft === 'clamp') return c;
		if (extrapolateLeft === 'identity') return x;
		if (extrapolateLeft === 'wrap') x = a + ((((x - a) % (b - a)) + (b - a)) % (b - a));
	} else if (x > b) {
		if (extrapolateRight === 'clamp') return d;
		if (extrapolateRight === 'identity') return x;
		if (extrapolateRight === 'wrap') x = a + ((x - a) % (b - a));
	}
	const k = (x - a) / (b - a);
	return c + (d - c) * easing(k);
}

// ---- springs ----

export type SpringConfig = {mass?: number; damping?: number; stiffness?: number; overshootClamping?: boolean};

/** A damped spring from 0 to 1 released at rest, `seconds` after release (closed form). */
function springAt(seconds: number, {mass = 1, damping = 10, stiffness = 100}: SpringConfig): number {
	if (seconds <= 0) return 0;
	const w0 = Math.sqrt(stiffness / mass);
	const zeta = damping / (2 * Math.sqrt(stiffness * mass));
	if (zeta < 1) {
		const wd = w0 * Math.sqrt(1 - zeta * zeta);
		return 1 - Math.exp(-zeta * w0 * seconds) * (Math.cos(wd * seconds) + ((zeta * w0) / wd) * Math.sin(wd * seconds));
	}
	if (zeta === 1) return 1 - Math.exp(-w0 * seconds) * (1 + w0 * seconds);
	const s = Math.sqrt(zeta * zeta - 1);
	const r1 = -w0 * (zeta - s);
	const r2 = -w0 * (zeta + s);
	return 1 - (r2 * Math.exp(r1 * seconds) - r1 * Math.exp(r2 * seconds)) / (r2 - r1);
}

const REST = 0.005;
const settleCache = new Map<string, number>();
/** Seconds until the spring stays within REST of its end. */
function settleSeconds(config: SpringConfig): number {
	const key = JSON.stringify(config);
	const hit = settleCache.get(key);
	if (hit !== undefined) return hit;
	const dt = 1 / 120;
	let last = 0;
	for (let t = dt; t < 120; t += dt) if (Math.abs(1 - springAt(t, config)) > REST) last = t;
	const out = last + dt;
	settleCache.set(key, out);
	return out;
}

/** Spring from `from` to `to` at `frame`; with `durationInFrames` the spring is retimed to settle by then. */
export function spring({
	frame,
	fps,
	config = {},
	from = 0,
	to = 1,
	durationInFrames,
	delay = 0,
}: {
	frame: number;
	fps: number;
	config?: SpringConfig;
	from?: number;
	to?: number;
	durationInFrames?: number;
	delay?: number;
}): number {
	let seconds = (frame - delay) / fps;
	if (durationInFrames !== undefined && durationInFrames > 0) seconds *= settleSeconds(config) / (durationInFrames / fps);
	let k = springAt(seconds, config);
	if (config.overshootClamping) k = Math.min(1, k);
	return from + (to - from) * k;
}

// ---- video and sound ----

type VolumeProp = number | ((frame: number) => number);
const volumeAt = (volume: VolumeProp | undefined, frame: number) => Math.max(0, typeof volume === 'function' ? volume(frame) : (volume ?? 1));

/** The URL of frame `seconds` of `src`, extracted by the render script. */
export function frameUrl(dirs: Record<string, FrameDir> | undefined, src: string, seconds: number): string | null {
	const d = dirs?.[src];
	if (!d) return null;
	return `${d.dir}/${Math.max(0, Math.round(seconds * d.fps))}.${d.ext}`;
}

export type VideoProps = {
	src: string;
	/** Frames into the file at this video's first frame. */
	startFrom?: number;
	playbackRate?: number;
	muted?: boolean;
	volume?: VolumeProp;
	/** Keep the alpha channel (the speaker cut-out). */
	transparent?: boolean;
	style?: React.CSSProperties;
	className?: string;
};

/** A video, frame-exact: the frame at (startFrom + frame * playbackRate) / fps seconds into the file. */
export const OffthreadVideo: React.FC<VideoProps> = ({src, startFrom = 0, playbackRate = 1, muted, volume, transparent, style, className}) => {
	const rt = useContext(RuntimeContext);
	const tl = useContext(TimelineContext);
	const seconds = (startFrom + tl.frame * playbackRate) / rt.fps;
	if (rt.mode === 'collect') {
		rt.record?.({
			src,
			frame: tl.absolute,
			seconds,
			step: tl.frozen ? 0 : playbackRate / rt.fps,
			volume: muted || tl.frozen ? 0 : volumeAt(volume, tl.frame),
			picture: true,
			transparent,
		});
		return null;
	}
	if (rt.mode === 'render') {
		const url = frameUrl(rt.frames, src, seconds);
		// eslint-disable-next-line jsx-a11y/alt-text
		return url ? <img src={url} decoding="sync" style={style} className={className} /> : null;
	}
	return <PreviewVideo src={src} seconds={seconds} rate={playbackRate} frozen={tl.frozen} style={style} className={className} />;
};

/** Same as OffthreadVideo (the name the components use for clips). */
export const Video = OffthreadVideo;

const PreviewVideo: React.FC<{src: string; seconds: number; rate: number; frozen: boolean; style?: React.CSSProperties; className?: string}> = ({src, seconds, rate, frozen, style, className}) => {
	const rt = useContext(RuntimeContext);
	const ref = useRef<HTMLVideoElement>(null);
	useLayoutEffect(() => {
		const v = ref.current;
		if (!v) return;
		const play = !frozen && Boolean(rt.playing?.());
		const drift = Math.abs(v.currentTime - seconds);
		if (play) {
			v.playbackRate = rate;
			if (drift > 0.25) v.currentTime = seconds;
			if (v.paused) v.play().catch(() => undefined);
		} else {
			if (!v.paused) v.pause();
			if (drift > 0.5 / rt.fps) v.currentTime = seconds;
		}
	});
	return <video ref={ref} src={src} muted playsInline preload="auto" style={style} className={className} />;
};

/** Sound (the brand music). Recorded in collect mode; the page plays it as a HyperFrames <audio> clip. */
export const Audio: React.FC<{
	src: string;
	startFrom?: number;
	playbackRate?: number;
	volume?: VolumeProp;
	muted?: boolean;
	loop?: boolean;
	loopVolumeCurveBehavior?: 'repeat' | 'extend';
}> = ({src, startFrom = 0, playbackRate = 1, volume, muted, loop}) => {
	const rt = useContext(RuntimeContext);
	const tl = useContext(TimelineContext);
	if (rt.mode === 'collect') {
		rt.record?.({
			src,
			frame: tl.absolute,
			seconds: (startFrom + tl.frame * playbackRate) / rt.fps,
			step: tl.frozen ? 0 : playbackRate / rt.fps,
			volume: muted || tl.frozen ? 0 : volumeAt(volume, tl.frame),
			picture: false,
			loop,
		});
	}
	return null;
};
