import React, {useMemo} from 'react';
import {AbsoluteFill, Audio, Img, interpolate, spring, useCurrentFrame} from 'remotion';
import {endCardFrames, logoBox, musicVolumes} from './brand';
import {captionFamily, loadBrandFont} from './fonts';
import type {EditPlan} from './plan';
import type {Timeline} from './timing';

/** The brand kit on the reel (ADR 0026): music under everything, the logo in its corner, the end card last. */
/** `media(name)`: the URL of a file next to the video (the composition's own `mediaSrc`). */
export const BrandLayer: React.FC<{plan: EditPlan; tl: Timeline; media: (name: string) => string}> = ({plan, tl, media}) => {
	const frame = useCurrentFrame();
	const {brand, output} = plan;
	const vols = useMemo(() => (brand.music ? musicVolumes(plan, tl) : []), [plan, tl, brand.music]);
	if (brand.font && brand.font_name) loadBrandFont(brand.font_name, media(brand.font));
	const card = endCardFrames(plan, tl.durationInFrames);
	const onCard = card !== null && frame >= card.from;
	const box = logoBox(brand.logo_corner, brand.logo_size, output.width, output.height);
	return (
		<>
			{brand.music ? (
				<Audio src={media(brand.music)} loop loopVolumeCurveBehavior="extend" volume={(f) => vols[Math.min(vols.length - 1, Math.max(0, f))] ?? 0} />
			) : null}
			{brand.logo && !onCard ? (
				<Img src={media(brand.logo)} style={{position: 'absolute', left: box.left, top: box.top, width: box.width, height: 'auto', opacity: brand.logo_opacity, filter: 'drop-shadow(0 4px 14px rgba(0,0,0,0.35))'}} />
			) : null}
			{card && onCard ? <EndCard plan={plan} local={frame - card.from} media={media} /> : null}
		</>
	);
};

/** The logo large and the kit's line under it, rising in over the reel's fade to black. */
const EndCard: React.FC<{plan: EditPlan; local: number; media: (name: string) => string}> = ({plan, local, media}) => {
	const {brand, output, style} = plan;
	const fps = output.fps;
	const k = spring({frame: local, fps, config: {damping: 200}, durationInFrames: Math.round(0.6 * fps)});
	const lift = interpolate(k, [0, 1], [40, 0]);
	return (
		<AbsoluteFill style={{background: `rgba(0,0,0,${0.93 * k})`, alignItems: 'center', justifyContent: 'center', gap: 48, flexDirection: 'column'}}>
			{brand.logo ? <Img src={media(brand.logo)} style={{width: output.width * 0.42, height: 'auto', opacity: k, transform: `translateY(${lift}px)`}} /> : null}
			<div
				style={{
					maxWidth: output.width * 0.8,
					textAlign: 'center',
					color: '#FFFFFF',
					fontFamily: `"${captionFamily(style.caption.font)}", "Inter", sans-serif`,
					fontWeight: 800,
					fontSize: 64,
					lineHeight: 1.15,
					opacity: k,
					transform: `translateY(${lift * 1.5}px)`,
				}}
			>
				{brand.end_card}
			</div>
			<div style={{width: 120 * k, height: 8, borderRadius: 4, background: style.graphics.accent_color}} />
		</AbsoluteFill>
	);
};
