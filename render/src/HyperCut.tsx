import React, {useMemo} from 'react';
import {AbsoluteFill, Freeze, Img, OffthreadVideo, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {AroundLayer} from './Around';
import {Captions} from './Captions';
import {StageLayer, stageFootageFilter} from './Stage';
import {BackgroundFill, backgroundFilter, BehindLayer, replacesBackground} from './Depth';
import {GraphicBody, GraphicView} from './Graphics';
import {aroundAt, depthAt, isAroundType, isStageType, isVisualType, PULL_BACK, sceneAt, SPLIT, SPLIT_AREA, VISUAL_AREA, VISUAL_IN} from './layout';
import {normalizePlan, type CompositionProps, type EditPlan, type Graphic} from './plan';
import {buildTimeline, frameToSource, isKept, mediaRuns, type Timeline, type TimelineSegment} from './timing';

const isUrl = (s: string) => /^(https?:|blob:|data:)/.test(s);
export const resolveSrc = (src: string) => (isUrl(src) ? src : staticFile(src));
/** An imported file: fetched from assetBase in the preview, a static file next to the video in the render. */
export const mediaSrc = (name: string, assetBase?: string) => (assetBase ? `${assetBase}${encodeURIComponent(name)}` : resolveSrc(name));

const num = (v: unknown, fallback: number) => (typeof v === 'number' && Number.isFinite(v) ? v : fallback);

/**
 * An imported picture or clip filling its box (the split panel or the whole frame). Pictures drift in
 * slowly; clips play from `trim_start`, muted (the speaker keeps the audio), and hold their last frame
 * if the block outlasts the clip.
 */
const MediaFill: React.FC<{graphic: Graphic; tl: Timeline; t: number; frame: number; assetBase?: string}> = ({graphic, tl, t, frame, assetBase}) => {
	const {props} = graphic;
	const src = mediaSrc(String(props.src ?? ''), assetBase);
	const fit = props.fit === 'contain' ? 'contain' : 'cover';
	const fill: React.CSSProperties = {position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: fit};
	if (props.kind !== 'video') {
		const k = Math.min(1, Math.max(0, (t - graphic.start) / Math.max(0.1, graphic.end - graphic.start)));
		return <Img src={src} style={{...fill, transform: `scale(${1.02 + 0.06 * k})`}} />;
	}
	const run = mediaRuns(tl, graphic).find((r) => frame >= r.from && frame < r.from + r.frames);
	if (!run) return null;
	const fps = tl.fps;
	const start = Math.round((num(props.trim_start, 0) + run.offset) * fps);
	const clipFrames = props.duration === undefined ? Infinity : Math.floor(num(props.duration, 0) * fps) - start - 1;
	const playFrames = Math.max(1, Math.min(run.frames, clipFrames));
	return (
		<>
			<Sequence from={run.from} durationInFrames={playFrames} layout="none">
				<OffthreadVideo src={src} muted startFrom={start} style={fill} />
			</Sequence>
			{playFrames < run.frames ? (
				<Sequence from={run.from + playFrames} durationInFrames={run.frames - playFrames} layout="none">
					<Freeze frame={0}>
						<OffthreadVideo src={src} muted startFrom={start + playFrames - 1} style={fill} />
					</Freeze>
				</Sequence>
			) : null}
		</>
	);
};

/** Extra punch-in on every other piece in the "zoom" transition style, so jump cuts read as intentional. */
export const ALT_PUNCH = 1.08;
/** Frames of sound eased in and out at every cut, so cuts never click. */
export const AUDIO_EASE = 3;

/**
 * The speaker, cropped into its panel and zoomed. Source pixels are never altered beyond scale/crop.
 * `tail` extra frames keep playing past the segment's end, fading out over the next one (smooth cuts).
 *
 * With green-screen effects (ADR 0901) the segment is drawn twice: `part="full"` is the footage with its
 * background treated (blurred, dimmed) or covered by a replacement, and carries the sound; `part="cutout"`
 * is the same frames of the speaker cut-out video, drawn on top once anything is behind the speaker.
 */
const VideoSegment: React.FC<{
	plan: EditPlan;
	tl: Timeline;
	seg: TimelineSegment;
	src: string;
	tail: number;
	last: boolean;
	part?: 'full' | 'cutout';
	matteSrc?: string;
	assetBase?: string;
}> = ({plan, tl, seg, src, tail, last, part = 'full', matteSrc, assetBase}) => {
	const local = useCurrentFrame();
	const {fps, width} = plan.output;
	const tr = plan.style.transitions;
	const t = seg.start + (local / fps) * tl.speed;
	const {mode, panel, rect, zoom, origin} = sceneAt(plan, t);
	const depth = depthAt(plan, t, mode, Boolean(matteSrc));
	const punch = tr.style === 'zoom' && seg.index % 2 === 1 ? ALT_PUNCH : 1;
	const opacity = local < seg.frames ? 1 : 1 - (local - seg.frames + 1) / (tail + 1);
	const fadeOutFrames = last ? Math.round(tr.fade_out * fps) : 0;
	// Sound eases in and out over a few frames at each cut (the kept pause around cuts makes that silent
	// anyway, but it removes clicks); the last segment fades out with the picture.
	const volume = (f: number) => {
		const head = seg.index === 0 ? 1 : (f + 1) / AUDIO_EASE;
		const out = (seg.frames - f) / (last ? Math.max(1, fadeOutFrames) : AUDIO_EASE);
		return Math.max(0, Math.min(1, head, out));
	};
	const placed: React.CSSProperties = {position: 'absolute', left: rect.left, top: rect.top, width: rect.width, height: rect.height};
	if (part === 'cutout') {
		if (!depth?.cutout || !matteSrc) return null;
		const lifted = replacesBackground(depth.background.kind) || depth.pull > 0;
		// Stage graphics pull the speaker back about the bottom of the frame under the face, and cards move
		// them aside (ADR 0611).
		const pullScale = 1 - PULL_BACK * depth.pull;
		return (
			<AbsoluteFill style={{opacity}}>
				<div style={{position: 'absolute', left: 0, top: panel.top, width, height: panel.height, overflow: 'hidden'}}>
					<AbsoluteFill style={{transform: pullScale < 1 ? `translateX(${depth.shift}px) scale(${pullScale})` : undefined, transformOrigin: `${origin.x}px ${panel.height}px`}}>
						{/* A pulled-back speaker holds still: punch-ins fade out with the pull. */}
						<AbsoluteFill style={{transform: `scale(${1 + (zoom * punch - 1) * (1 - depth.pull)})`, transformOrigin: `${origin.x}px ${origin.y}px`}}>
							<OffthreadVideo
								src={matteSrc}
								transparent
								muted
								startFrom={Math.round(seg.start * fps)}
								playbackRate={tl.speed}
								// A soft shadow so a speaker over a new background doesn't look pasted on.
								style={{...placed, filter: lifted ? 'drop-shadow(0 18px 36px rgba(0,0,0,0.45))' : undefined}}
							/>
						</AbsoluteFill>
					</AbsoluteFill>
				</div>
			</AbsoluteFill>
		);
	}
	const kind = depth?.background.kind ?? 'original';
	return (
		<AbsoluteFill style={{background: local < seg.frames ? '#000' : 'transparent', opacity}}>
			<div style={{position: 'absolute', left: 0, top: panel.top, width, height: panel.height, overflow: 'hidden', background: '#000'}}>
				{/* Zoom about the face, so a punch-in moves toward the subject, not the frame center. */}
				<AbsoluteFill style={{transform: `scale(${zoom * punch})`, transformOrigin: `${origin.x}px ${origin.y}px`}}>
					<OffthreadVideo
						src={src}
						startFrom={Math.round(seg.start * fps)}
						playbackRate={tl.speed}
						volume={volume}
						style={{...placed, filter: backgroundFilter(kind) ?? (depth ? stageFootageFilter(depth.stage) : undefined)}}
					/>
				</AbsoluteFill>
				{depth && replacesBackground(kind) ? (
					<BackgroundFill
						bg={depth.background}
						accent={plan.style.graphics.accent_color}
						seconds={t}
						mediaSrc={(name) => mediaSrc(name, assetBase)}
						backdrop={<Backdrop frame={Math.round(t * fps)} fps={fps} accent={depth.background.color || plan.style.graphics.accent_color} />}
					/>
				) : null}
			</div>
		</AbsoluteFill>
	);
};

/** Graphics behind the speaker (green-screen effects), between the footage and the cut-out speaker. */
const Behind: React.FC<{plan: EditPlan; tl: Timeline; assetBase?: string}> = ({plan, tl, assetBase}) => {
	const frame = useCurrentFrame();
	const t = frameToSource(tl, frame);
	if (t === null) return null;
	const scene = sceneAt(plan, t);
	const depth = depthAt(plan, t, scene.mode, true);
	if (!depth?.behind.length && !depth?.around.length && !depth?.stage.length) return null;
	return (
		<>
			{depth.stage.length ? <StageLayer graphics={depth.stage} t={t} plan={plan} face={scene.face} pull={depth.pull} shift={depth.shift} /> : null}
			{depth.behind.length ? (
				<BehindLayer
					graphics={depth.behind}
					t={t}
					plan={plan}
					face={scene.face}
					renderMedia={(g) => <MediaFill graphic={g} tl={tl} t={t} frame={frame} assetBase={assetBase} />}
				/>
			) : null}
			<AroundLayer graphics={depth.around} t={t} plan={plan} face={scene.face} pass="behind" />
		</>
	);
};

/** Black over everything at the very start and end (fade in / fade out of the reel). */
const Fades: React.FC<{plan: EditPlan; total: number}> = ({plan, total}) => {
	const frame = useCurrentFrame();
	const {fps} = plan.output;
	const {fade_in, fade_out} = plan.style.transitions;
	const inK = fade_in > 0 ? 1 - Math.min(1, frame / (fade_in * fps)) : 0;
	const outK = fade_out > 0 ? Math.min(1, Math.max(0, (frame - (total - fade_out * fps)) / (fade_out * fps))) : 0;
	const k = Math.max(inK, outK);
	return k > 0 ? <AbsoluteFill style={{background: '#000', opacity: k}} /> : null;
};

/** Frames a smooth cut lets segment i run on past its end, limited by the source and the next segment. */
export function tailFrames(plan: EditPlan, tl: Timeline, i: number): number {
	const tr = plan.style.transitions;
	const seg = tl.segments[i];
	const next = tl.segments[i + 1];
	if (tr.style !== 'smooth' || !next) return 0;
	const want = Math.round(tr.length * plan.output.fps);
	const room = Math.floor(((plan.source.duration - seg.end) * plan.output.fps) / tl.speed) - 1;
	// A split (one source piece continuing into the next) needs no transition.
	if (Math.abs(next.start - seg.end) < 1e-3) return 0;
	return Math.max(0, Math.min(want, room, next.frames - 1));
}

/** Dark gradient with a slow accent glow drifting across it; a pure function of the frame. */
const Backdrop: React.FC<{frame: number; fps: number; accent: string}> = ({frame, fps, accent}) => {
	const s = frame / fps;
	const x = 50 + 28 * Math.sin(s * 0.45);
	const y = 40 + 22 * Math.cos(s * 0.33);
	const x2 = 50 - 30 * Math.cos(s * 0.27);
	const y2 = 75 + 15 * Math.sin(s * 0.38);
	return (
		<AbsoluteFill
			style={{
				background: [
					`radial-gradient(circle at ${x}% ${y}%, color-mix(in srgb, ${accent} 34%, transparent) 0%, transparent 46%)`,
					`radial-gradient(circle at ${x2}% ${y2}%, color-mix(in srgb, ${accent} 16%, transparent) 0%, transparent 40%)`,
					'linear-gradient(160deg, #14141F 0%, #0B0B12 55%, #050507 100%)',
				].join(', '),
			}}
		/>
	);
};

/** Visual graphics stacked and centered in a box (output pixels); each fills what it can of it. */
const VisualBox: React.FC<{
	graphics: Graphic[];
	t: number;
	plan: EditPlan;
	top: number;
	height: number;
	mode: 'split' | 'visual';
}> = ({graphics, t, plan, top, height, mode}) => (
	<div style={{position: 'absolute', left: 0, right: 0, top, height, overflow: 'hidden'}}>
		{graphics.map((g) => (
			<AbsoluteFill key={g.id} style={{alignItems: 'center', justifyContent: 'center'}}>
				<GraphicBody graphic={g} t={t} style={plan.style.graphics} width={plan.output.width} height={plan.output.height} boxWidth={plan.output.width * 0.92} boxHeight={height} mode={mode} />
			</AbsoluteFill>
		))}
	</div>
);

const Overlays: React.FC<{plan: EditPlan; tl: Timeline; assetBase?: string; hasMatte: boolean}> = ({plan, tl, assetBase, hasMatte}) => {
	const frame = useCurrentFrame();
	const t = frameToSource(tl, frame);
	// Words in cut time never show, and lines are grouped from what is actually played.
	const words = useMemo(() => plan.transcript.words.filter((w) => isKept(tl, (w.start + w.end) / 2)), [plan, tl]);
	if (t === null) return null;

	const {width, height, fps} = plan.output;
	const scene = sceneAt(plan, t);
	const {mode} = scene;
	// Graphics drawn behind the speaker are not ours; the rest of the behind layer (no cut-out, or a split
	// or visual stretch) is placed in front, off the face, like any other graphic.
	const behind = depthAt(plan, t, mode, hasMatte)?.behind ?? [];
	// Stage graphics are only drawn behind a cut-out speaker (Behind); without one they are left out.
	const active = plan.graphics.filter((g) => t >= g.start && t < g.end && !behind.includes(g) && !isAroundType(g.type) && !isStageType(g.type));
	// Effects around the speaker: their near half here, in front of the cut-out; without one, all of them
	// in front (kept off the face either way). Only in speaker stretches, and only when depth is on.
	const around = mode === 'speaker' && plan.style.depth.enabled ? aroundAt(plan, t) : [];
	const visuals = mode === 'speaker' ? [] : active.filter((g) => isVisualType(g.type) && g.layer !== 'behind');
	const media = visuals.filter((g) => g.type === 'media');
	const boxed = visuals.filter((g) => g.type !== 'media');
	const placed = active.filter((g) => !visuals.includes(g));
	const mediaLayer = media.map((g) => <MediaFill key={g.id} graphic={g} tl={tl} t={t} frame={frame} assetBase={assetBase} />);
	const accent = plan.style.graphics.accent_color;
	const visualK = Math.min(1, Math.max(0, scene.enter / VISUAL_IN));

	return (
		<AbsoluteFill>
			{mode === 'split' ? (
				// The top panel is revealed as the speaker panel slides down; nothing spills below it.
				<div style={{position: 'absolute', left: 0, top: 0, width, height: scene.panel.top, overflow: 'hidden'}}>
					<Backdrop frame={frame} fps={fps} accent={accent} />
					{/* Imported media fills the panel at its final size, so the reveal uncovers it rather than squashing it. */}
					<div style={{position: 'absolute', left: 0, top: 0, width, height: SPLIT * height, overflow: 'hidden'}}>{mediaLayer}</div>
					<VisualBox graphics={boxed} t={t} plan={plan} mode="split" top={SPLIT_AREA.top * height} height={(SPLIT_AREA.bottom - SPLIT_AREA.top) * height} />
					<div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 6, background: accent}} />
				</div>
			) : null}
			{mode === 'visual' ? (
				<AbsoluteFill style={{opacity: visualK, transform: `scale(${1.06 - 0.06 * visualK})`}}>
					<Backdrop frame={frame} fps={fps} accent={accent} />
					{mediaLayer}
					<VisualBox graphics={boxed} t={t} plan={plan} mode="visual" top={VISUAL_AREA.top * height} height={(VISUAL_AREA.bottom - VISUAL_AREA.top) * height} />
				</AbsoluteFill>
			) : null}
			{placed.map((g) => (
				<GraphicView
					key={`${g.id}`}
					graphic={g}
					t={t}
					style={plan.style.graphics}
					captionPos={plan.style.caption.position}
					faceY={scene.faceY}
					mode={mode}
					width={width}
					height={height}
				/>
			))}
			{around.length ? <AroundLayer graphics={around} t={t} plan={plan} face={scene.face} pass={hasMatte ? 'front' : 'all'} /> : null}
			<Captions words={words} style={plan.style.caption} t={t} height={height} y={scene.captionY} />
		</AbsoluteFill>
	);
};

export const HyperCut: React.FC<CompositionProps> = ({plan: rawPlan, videoSrc, assetBase, matteSrc: rawMatte}) => {
	const plan = useMemo(() => normalizePlan(rawPlan), [rawPlan]);
	const tl = useMemo(() => buildTimeline(plan.segments, plan.source.duration, plan.output.fps, plan.style.pacing.speed), [plan]);
	const src = resolveSrc(videoSrc);
	// The cut-out is only fetched when the plan asks for green-screen effects.
	const matteSrc = rawMatte && plan.style.depth.enabled ? resolveSrc(rawMatte) : undefined;
	const n = tl.segments.length;
	return (
		<AbsoluteFill style={{background: '#000'}}>
			{/* Drawn last to first, so a segment's fading tail lies over the start of the next one. */}
			{[...tl.segments].reverse().map((seg) => {
				const tail = tailFrames(plan, tl, seg.index);
				return (
					<Sequence key={seg.index} from={seg.outFrom} durationInFrames={seg.frames + tail} layout="none">
						<VideoSegment plan={plan} tl={tl} seg={seg} src={src} tail={tail} last={seg.index === n - 1} matteSrc={matteSrc} assetBase={assetBase} />
					</Sequence>
				);
			})}
			{matteSrc ? (
				<>
					<Behind plan={plan} tl={tl} assetBase={assetBase} />
					{[...tl.segments].reverse().map((seg) => {
						const tail = tailFrames(plan, tl, seg.index);
						return (
							<Sequence key={`cut${seg.index}`} from={seg.outFrom} durationInFrames={seg.frames + tail} layout="none">
								<VideoSegment plan={plan} tl={tl} seg={seg} src={src} tail={tail} last={seg.index === n - 1} part="cutout" matteSrc={matteSrc} />
							</Sequence>
						);
					})}
				</>
			) : null}
			<Overlays plan={plan} tl={tl} assetBase={assetBase} hasMatte={Boolean(matteSrc)} />
			<Fades plan={plan} total={tl.durationInFrames} />
		</AbsoluteFill>
	);
};

/** Size, fps and length come from the plan, so the same composition renders any plan. */
export const calculateMetadata = ({props}: {props: CompositionProps}) => {
	const plan = normalizePlan(props.plan);
	const tl = buildTimeline(plan.segments, plan.source.duration, plan.output.fps, plan.style.pacing.speed);
	return {
		durationInFrames: tl.durationInFrames,
		fps: plan.output.fps,
		width: plan.output.width,
		height: plan.output.height,
	};
};
