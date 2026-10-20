'use client';

import type {PlayerRef} from '@remotion/player';
import {useEffect, useMemo, useState, type RefObject} from 'react';
import type {EditPlan} from '@render/plan';
import {GRAPHIC_NAMES, graphicLabel, onScreenAt, timelineOf, type ItemRef} from '@/lib/timeline';

/** The graphics in the frame at the playhead, as buttons: click one to edit its words, numbers and colour. */
export default function OnScreen({plan, playerRef, onSelect}: {plan: EditPlan; playerRef: RefObject<PlayerRef>; onSelect: (ref: ItemRef) => void}) {
	const [frame, setFrame] = useState(0);
	const tl = useMemo(() => timelineOf(plan), [plan]);
	useEffect(() => {
		const player = playerRef.current;
		if (!player) return;
		const onFrame = (e: {detail: {frame: number}}) => setFrame(e.detail.frame);
		player.addEventListener('frameupdate', onFrame);
		player.addEventListener('seeked', onFrame);
		return () => {
			player.removeEventListener('frameupdate', onFrame);
			player.removeEventListener('seeked', onFrame);
		};
	}, [playerRef]);
	const shown = onScreenAt(plan, tl, frame / plan.output.fps);
	if (!shown.length) return <p className="hint on-screen">Nothing over the speaker here. Pause on a graphic to edit it.</p>;
	return (
		<div className="chips on-screen">
			<span className="hint">On screen:</span>
			{shown.map((g) => (
				<button key={g.id} className="chip" onClick={() => onSelect({kind: 'graphic', id: g.id})} title={GRAPHIC_NAMES[g.type]}>
					{graphicLabel(g)}
				</button>
			))}
		</div>
	);
}
