import React, {useMemo} from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {Captions} from './Captions';
import {GraphicView} from './Graphics';
import {cropRect, pointInOutput, reframeAt, zoomAt} from './layout';
import {normalizePlan, type CompositionProps, type EditPlan} from './plan';
import {buildTimeline, frameToSource, isKept, type Timeline, type TimelineSegment} from './timing';

const isUrl = (s: string) => /^(https?:|blob:|data:)/.test(s);
export const resolveSrc = (src: string) => (isUrl(src) ? src : staticFile(src));

/** The speaker, cropped to the output and zoomed. Source pixels are never altered beyond scale/crop. */
const VideoSegment: React.FC<{plan: EditPlan; seg: TimelineSegment; src: string}> = ({plan, seg, src}) => {
	const local = useCurrentFrame();
	const {fps, width, height} = {...plan.output};
	const t = seg.start + local / fps;
	const {cx, cy} = reframeAt(plan.reframe.keys, t);
	const rect = cropRect(plan.source, plan.output, cx, cy);
	const zoom = zoomAt(plan.zooms, t);
	return (
		<AbsoluteFill style={{overflow: 'hidden', background: '#000'}}>
			{/* Zoom about the frame center, where the crop puts the subject. */}
			<AbsoluteFill style={{transform: `scale(${zoom})`, transformOrigin: `${width / 2}px ${height / 2}px`}}>
				<OffthreadVideo
					src={src}
					startFrom={Math.round(seg.start * fps)}
					style={{position: 'absolute', left: rect.left, top: rect.top, width: rect.width, height: rect.height}}
				/>
			</AbsoluteFill>
		</AbsoluteFill>
	);
};

const Overlays: React.FC<{plan: EditPlan; tl: Timeline}> = ({plan, tl}) => {
	const frame = useCurrentFrame();
	const t = frameToSource(tl, frame);
	// Words in cut time never show, and lines are grouped from what is actually played.
	const words = useMemo(() => plan.transcript.words.filter((w) => isKept(tl, (w.start + w.end) / 2)), [plan, tl]);
	if (t === null) return null;

	const {width, height} = plan.output;
	const {cx, cy} = reframeAt(plan.reframe.keys, t);
	const rect = cropRect(plan.source, plan.output, cx, cy);
	const zoom = zoomAt(plan.zooms, t);
	// Where the face ends up in the output frame, as a fraction of its height (zoom is about the center).
	const faceYpx = pointInOutput(rect, cx, cy).y;
	const faceY = plan.reframe.keys.length ? (height / 2 + (faceYpx - height / 2) * zoom) / height : 0.4;

	return (
		<AbsoluteFill>
			{plan.graphics
				.filter((g) => t >= g.start && t < g.end)
				.map((g) => (
					<GraphicView
						key={`${g.id}`}
						graphic={g}
						t={t}
						style={plan.style.graphics}
						captionPos={plan.style.caption.position}
						faceY={faceY}
						width={width}
						height={height}
					/>
				))}
			<Captions words={words} style={plan.style.caption} t={t} height={height} />
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
