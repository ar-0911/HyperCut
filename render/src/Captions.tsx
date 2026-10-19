import React, {useMemo} from 'react';
import {groupAt, groupWords, wordState} from './captions';
import {captionFamily, captionStretch, captionWeight} from './fonts';
import {CAPTION_Y} from './layout';
import type {CaptionStyle, Word} from './plan';

const FONT_STACK = '"Montserrat", "Inter", "Helvetica Neue", Arial, sans-serif';

/** Word captions for the line on screen at source time `t`. `words` are the ones that survive the cuts. */
export const Captions: React.FC<{
	words: Word[];
	style: CaptionStyle;
	t: number;
	height: number;
	/** Line center as a fraction of height; defaults to the style's position. */
	y?: number;
}> = ({words, style, t, height, y}) => {
	const groups = useMemo(() => groupWords(words, style.words_per_line), [words, style.words_per_line]);
	const hit = groupAt(groups, t);
	if (!hit) return null;
	const {group} = hit;
	// A boxed caption (a rounded dark pill behind the line) needs no outline.
	const box = style.box || null;
	const stroke = box ? 0 : style.stroke_width;

	return (
		<div style={{position: 'absolute', left: 60, right: 60, top: (y ?? CAPTION_Y[style.position]) * height, transform: 'translateY(-50%)', display: 'flex', justifyContent: 'center'}}>
			<div
				style={{
					display: 'flex',
					flexWrap: 'wrap',
					justifyContent: 'center',
					// wide enough for the active word's pop scale plus both outlines, so neighbours never touch
					gap: `${style.size * 0.05}px ${style.size * 0.45}px`,
					fontFamily: `"${captionFamily(style.font)}", ${FONT_STACK}`,
					fontWeight: captionWeight(style.font, style.weight),
					fontStretch: captionStretch(style.font),
					fontSize: style.size,
					lineHeight: 1.1,
					textAlign: 'center',
					...(box ? {background: box, borderRadius: style.size * 0.38, padding: `${style.size * 0.2}px ${style.size * 0.42}px`, boxShadow: '0 10px 30px rgba(0,0,0,0.25)'} : {}),
				}}
			>
				{group.words.map((word, i) => {
					const s = wordState(style.animation, group, i, t);
					if (!s.visible) return null;
					const text = style.uppercase ? word.text.toUpperCase() : word.text;
					return (
						<span
							key={`${word.start}-${i}`}
							style={{
								display: 'inline-block',
								color: s.active ? style.highlight_color : style.color,
								opacity: s.opacity,
								transform: `translateY(${s.lift * style.size}px) scale(${s.scale})`,
								transformOrigin: '50% 70%',
								// paint-order keeps the outline outside the glyphs so thin weights stay readable
								WebkitTextStroke: stroke ? `${stroke * 2}px ${style.stroke_color}` : undefined,
								paintOrder: 'stroke fill',
								textShadow: stroke ? `0 ${stroke}px ${stroke * 2}px rgba(0,0,0,0.45)` : undefined,
							}}
						>
							{text}
						</span>
					);
				})}
			</div>
		</div>
	);
};
