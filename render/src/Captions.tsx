import React, {useMemo} from 'react';
import {groupAt, groupWords, wordState} from './captions';
import {CAPTION_Y} from './layout';
import type {CaptionStyle, Word} from './plan';

const FONT_STACK = '"Montserrat", "Inter", "Helvetica Neue", Arial, sans-serif';

/** Word captions for the line on screen at source time `t`. `words` are the ones that survive the cuts. */
export const Captions: React.FC<{words: Word[]; style: CaptionStyle; t: number; height: number}> = ({
	words,
	style,
	t,
	height,
}) => {
	const groups = useMemo(() => groupWords(words, style.words_per_line), [words, style.words_per_line]);
	const hit = groupAt(groups, t);
	if (!hit) return null;
	const {group} = hit;
	const stroke = style.stroke_width;

	return (
		<div
			style={{
				position: 'absolute',
				left: 60,
				right: 60,
				top: CAPTION_Y[style.position] * height,
				transform: 'translateY(-50%)',
				display: 'flex',
				flexWrap: 'wrap',
				justifyContent: 'center',
				// wide enough for the active word's pop scale plus both outlines, so neighbours never touch
				gap: `${style.size * 0.05}px ${style.size * 0.45}px`,
				fontFamily: `"${style.font}", ${FONT_STACK}`,
				fontWeight: style.weight,
				fontSize: style.size,
				lineHeight: 1.1,
				textAlign: 'center',
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
							WebkitTextStroke: `${stroke * 2}px ${style.stroke_color}`,
							paintOrder: 'stroke fill',
							textShadow: `0 ${stroke}px ${stroke * 2}px rgba(0,0,0,0.45)`,
						}}
					>
						{text}
					</span>
				);
			})}
		</div>
	);
};
