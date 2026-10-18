import React, {useMemo} from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {Captions} from './Captions';
import {GraphicBody, GraphicView} from './Graphics';
import {isVisualType, sceneAt, SPLIT_AREA, VISUAL_AREA, VISUAL_IN} from './layout';
import {normalizePlan, type CompositionProps, type EditPlan, type Graphic} from './plan';
import {buildTimeline, frameToSource, isKept, type Timeline, type TimelineSegment} from './timing';

const isUrl = (s: string) => /^(https?:|blob:|data:)/.test(s);
export const resolveSrc = (src: string) => (isUrl(src) ? src : staticFile(src));

/** The speaker, cropped into its panel and zoomed. Source pixels are never altered beyond scale/crop. */
const VideoSegment: React.FC<{plan: EditPlan; seg: TimelineSegment; src: string}> = ({plan, seg, src}) => {
	const local = useCurrentFrame();
	const {fps, width} = plan.output;
	const t = seg.start + local / fps;
	const {panel, rect, zoom, origin} = sceneAt(plan, t);
	return (
		<AbsoluteFill style={{background: '#000'}}>
			<div style={{position: 'absolute', left: 0, top: panel.top, width, height: panel.height, overflow: 'hidden'}}>
				{/* Zoom about the face, so a punch-in moves toward the subject, not the frame center. */}
				<AbsoluteFill style={{transform: `scale(${zoom})`, transformOrigin: `${origin.x}px ${origin.y}px`}}>
					<OffthreadVideo
						src={src}
						startFrom={Math.round(seg.start * fps)}
						style={{position: 'absolute', left: rect.left, top: rect.top, width: rect.width, height: rect.height}}
					/>
				</AbsoluteFill>
			</div>
		</AbsoluteFill>
	);
};

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

const Overlays: React.FC<{plan: EditPlan; tl: Timeline}> = ({plan, tl}) => {
	const frame = useCurrentFrame();
	const t = frameToSource(tl, frame);
	// Words in cut time never show, and lines are grouped from what is actually played.
	const words = useMemo(() => plan.transcript.words.filter((w) => isKept(tl, (w.start + w.end) / 2)), [plan, tl]);
	if (t === null) return null;

	const {width, height, fps} = plan.output;
	const scene = sceneAt(plan, t);
	const {mode} = scene;
	const active = plan.graphics.filter((g) => t >= g.start && t < g.end);
	const boxed = mode === 'speaker' ? [] : active.filter((g) => isVisualType(g.type));
	const placed = active.filter((g) => !boxed.includes(g));
	const accent = plan.style.graphics.accent_color;
	const visualK = Math.min(1, Math.max(0, scene.enter / VISUAL_IN));

	return (
		<AbsoluteFill>
			{mode === 'split' ? (
				// The top panel is revealed as the speaker panel slides down; nothing spills below it.
				<div style={{position: 'absolute', left: 0, top: 0, width, height: scene.panel.top, overflow: 'hidden'}}>
					<Backdrop frame={frame} fps={fps} accent={accent} />
					<VisualBox graphics={boxed} t={t} plan={plan} mode="split" top={SPLIT_AREA.top * height} height={(SPLIT_AREA.bottom - SPLIT_AREA.top) * height} />
					<div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 6, background: accent}} />
				</div>
			) : null}
			{mode === 'visual' ? (
				<AbsoluteFill style={{opacity: visualK, transform: `scale(${1.06 - 0.06 * visualK})`}}>
					<Backdrop frame={frame} fps={fps} accent={accent} />
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
			<Captions words={words} style={plan.style.caption} t={t} height={height} y={scene.captionY} />
		</AbsoluteFill>
	);
};

export const HyperCut: React.FC<CompositionProps> = ({plan: rawPlan, videoSrc}) => {
	const plan = useMemo(() => normalizePlan(rawPlan), [rawPlan]);
	const tl = useMemo(() => buildTimeline(plan.segments, plan.source.duration, plan.output.fps), [plan]);
	const src = resolveSrc(videoSrc);
	return (
		<AbsoluteFill style={{background: '#000'}}>
			{tl.segments.map((seg) => (
				<Sequence key={seg.index} from={seg.outFrom} durationInFrames={seg.frames} layout="none">
					<VideoSegment plan={plan} seg={seg} src={src} />
				</Sequence>
			))}
			<Overlays plan={plan} tl={tl} />
		</AbsoluteFill>
	);
};

/** Size, fps and length come from the plan, so the same composition renders any plan. */
export const calculateMetadata = ({props}: {props: CompositionProps}) => {
	const plan = normalizePlan(props.plan);
	const tl = buildTimeline(plan.segments, plan.source.duration, plan.output.fps);
	return {
		durationInFrames: tl.durationInFrames,
		fps: plan.output.fps,
		width: plan.output.width,
		height: plan.output.height,
	};
};
