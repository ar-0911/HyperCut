// The studio behind visuals and a replaced background (ADR 0613): never a flat colour. A floor grid that runs
// away to a horizon, a faint wall grid above it and soft light give the frame depth, like a set rather than a
// slide. It drifts very slowly so a held frame still feels alive. Pure function of time.

import React from 'react';
import {AbsoluteFill} from 'remotion';

export type StudioLook = 'light' | 'dark';

const LOOK = {
	light: {bg: '#E9ECF0', far: '#F4F6F8', line: 'rgba(30,36,48,0.11)', wall: 'rgba(30,36,48,0.05)', shade: 'rgba(40,44,52,0.16)'},
	dark: {bg: '#0B0B0E', far: '#16171C', line: 'rgba(255,255,255,0.09)', wall: 'rgba(255,255,255,0.035)', shade: 'rgba(0,0,0,0.6)'},
} as const;

/**
 * A studio filling its box. `tint` (a CSS colour) washes the light softly, for a background the user asked to
 * be a colour; `horizon` is where the floor meets the wall, as a fraction of the box height.
 */
export const StudioBackdrop: React.FC<{seconds: number; look?: StudioLook; tint?: string; horizon?: number; accent?: string}> = ({
	seconds,
	look = 'dark',
	tint,
	horizon = 0.58,
	accent,
}) => {
	const L = LOOK[look];
	const drift = (seconds * 6) % 80; // px the floor grid slides toward the camera per second
	const sway = Math.sin(seconds * 0.25) * 4;
	const glow = tint ?? accent;
	return (
		<AbsoluteFill style={{background: `linear-gradient(180deg, ${L.bg} 0%, ${L.far} ${horizon * 100}%, ${L.bg} 100%)`, overflow: 'hidden'}}>
			{/* The wall: a fine square grid, fading out toward the top. */}
			<AbsoluteFill
				style={{
					backgroundImage: `linear-gradient(${L.wall} 1px, transparent 1px), linear-gradient(90deg, ${L.wall} 1px, transparent 1px)`,
					backgroundSize: '72px 72px',
					backgroundPosition: `${sway}px 0`,
					maskImage: `linear-gradient(180deg, transparent 0%, #000 ${horizon * 70}%, #000 ${horizon * 100}%, transparent ${horizon * 100 + 0.5}%)`,
				}}
			/>
			{/* The floor: the same grid laid down in perspective, sliding slowly toward the viewer. */}
			<div style={{position: 'absolute', left: 0, right: 0, top: `${horizon * 100}%`, bottom: 0, perspective: 700, perspectiveOrigin: '50% 0%', overflow: 'hidden'}}>
				<div
					style={{
						position: 'absolute',
						left: '-100%',
						right: '-100%',
						top: 0,
						height: '300%',
						transformOrigin: '50% 0%',
						transform: 'rotateX(76deg)',
						backgroundImage: `linear-gradient(${L.line} 2px, transparent 2px), linear-gradient(90deg, ${L.line} 2px, transparent 2px)`,
						backgroundSize: '80px 80px',
						backgroundPosition: `${sway}px ${drift}px`,
						maskImage: 'linear-gradient(180deg, transparent 0%, #000 22%)',
					}}
				/>
			</div>
			{glow ? (
				<AbsoluteFill style={{background: `radial-gradient(ellipse 70% 45% at 50% ${horizon * 100 - 8}%, color-mix(in srgb, ${glow} ${tint ? 30 : 12}%, transparent) 0%, transparent 70%)`}} />
			) : null}
			<AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 45%, transparent 55%, ${L.shade} 100%)`}} />
		</AbsoluteFill>
	);
};
