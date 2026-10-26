'use client';

import {useState} from 'react';
import type {Explanation} from '@/lib/api';

const clock = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;

/** Why HyperCut cut the video the way it did, one line per decision; click a line to jump there. */
export default function WhyPanel({why, onSeek}: {why: Explanation | null; onSeek: (t: number) => void}) {
	const [all, setAll] = useState(false);
	if (!why) return null;
	const items = all ? why.items : why.items.slice(0, 8);
	return (
		<div className="card why">
			<h2>Why this cut</h2>
			<p className="hint">{why.summary}</p>
			<ul className="why-list">
				{items.map((it, i) => (
					<li key={i}>
						<button type="button" className="linkish" onClick={() => onSeek(it.at)}>
							<span className="muted">{clock(it.at)}</span> {it.text}
						</button>
					</li>
				))}
			</ul>
			{why.items.length > 8 && (
				<button type="button" className="linkish" onClick={() => setAll(!all)}>
					{all ? 'Show fewer' : `Show all ${why.items.length}`}
				</button>
			)}
		</div>
	);
}
