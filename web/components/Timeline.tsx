'use client';

import type {PlayerRef} from '@remotion/player';
import type {EditPlan} from '@render/plan';
import {useEffect, useMemo, useRef, useState, type DragEvent, type PointerEvent as ReactPointerEvent, type RefObject} from 'react';
import {
	TRACKS,
	fmtTime,
	moveItem,
	snap,
	snapPoints,
	trimItem,
	type BinPayload,
	type Item,
	type ItemRef,
	type Piece,
	type TrackId,
} from '@/lib/timeline';

export const DRAG_TYPE = 'application/x-hypercut';

type Drag = {
	mode: 'move' | 'start' | 'end';
	item: Item;
	piece: Piece;
	x0: number;
	base: EditPlan;
	moved: boolean;
	points: number[];
};

export default function Timeline({
	plan,
	items,
	duration,
	pps,
	snapping,
	selected,
	playerRef,
	onSelect,
	onLive,
	onCommit,
	onDrop,
}: {
	plan: EditPlan;
	items: Item[];
	/** Reel length in seconds. */
	duration: number;
	/** Pixels per second. */
	pps: number;
	snapping: boolean;
	selected: string | null;
	playerRef: RefObject<PlayerRef | null>;
	onSelect: (ref: ItemRef | null, at?: number) => void;
	/** A drag in progress: show it, but don't record an undo step yet. */
	onLive: (plan: EditPlan) => void;
	/** A drag finished: one undo step from `before` to `after`. */
	onCommit: (before: EditPlan, after: EditPlan) => void;
	onDrop: (payload: BinPayload, at: number) => void;
}) {
	const scroller = useRef<HTMLDivElement>(null);
	const [playhead, setPlayhead] = useState(0);
	const [dropAt, setDropAt] = useState<number | null>(null);
	const drag = useRef<Drag | null>(null);
	const width = Math.max(1, duration * pps);
	const fps = plan.output.fps;

	// Follow the player: move the playhead and keep it in view while playing.
	useEffect(() => {
		const player = playerRef.current;
		if (!player) return;
		const onFrame = (e: {detail: {frame: number}}) => {
			const t = e.detail.frame / fps;
			setPlayhead(t);
			const el = scroller.current;
			if (el && player.isPlaying()) {
				const x = t * pps;
				if (x > el.scrollLeft + el.clientWidth - 40 || x < el.scrollLeft) el.scrollLeft = Math.max(0, x - 80);
			}
		};
		player.addEventListener('frameupdate', onFrame);
		player.addEventListener('seeked', onFrame);
		return () => {
			player.removeEventListener('frameupdate', onFrame);
			player.removeEventListener('seeked', onFrame);
		};
	}, [playerRef, fps, pps]);

	const byTrack = useMemo(() => {
		const m = new Map<TrackId, Item[]>();
		for (const t of TRACKS) m.set(t.id, []);
		for (const it of items) m.get(it.track)!.push(it);
		return m;
	}, [items]);

	const ticks = useMemo(() => {
		const step = pps >= 60 ? 1 : pps >= 25 ? 2 : pps >= 12 ? 5 : 10;
		const out: number[] = [];
		for (let t = 0; t <= duration + 1e-6; t += step) out.push(t);
		return out;
	}, [duration, pps]);

	const timeAt = (clientX: number) => {
		const el = scroller.current!;
		const x = clientX - el.getBoundingClientRect().left + el.scrollLeft;
		return Math.min(duration, Math.max(0, x / pps));
	};

	const seek = (t: number) => playerRef.current?.seekTo(Math.round(t * fps));

	function startDrag(e: ReactPointerEvent, item: Item, piece: Piece, mode: Drag['mode']) {
		e.stopPropagation();
		e.preventDefault();
		onSelect(item.ref);
		const canDrag = mode === 'move' ? item.movable : item.track !== 'captions';
		if (!canDrag) {
			seek(piece.from);
			return;
		}
		drag.current = {mode, item, piece, x0: e.clientX, base: plan, moved: false, points: snapPoints(plan, items, item.key)};
		window.addEventListener('pointermove', onMove);
		window.addEventListener('pointerup', onUp, {once: true});
	}

	function onMove(e: PointerEvent) {
		const d = drag.current;
		if (!d) return;
		const dx = e.clientX - d.x0;
		if (!d.moved && Math.abs(dx) < 3) return;
		d.moved = true;
		const dt = dx / pps;
		const tol = snapping ? 8 / pps : 0;
		if (d.mode === 'move') {
			const len = d.piece.to - d.piece.from;
			const rawStart = d.piece.from + dt;
			const s1 = snap(rawStart, d.points, tol);
			const s2 = snap(rawStart + len, d.points, tol) - len;
			const to = Math.abs(s1 - rawStart) <= Math.abs(s2 - rawStart) ? s1 : s2;
			onLive(moveItem(d.base, d.item.ref, d.piece, Math.max(0, to)));
		} else {
			const edge = d.mode === 'start' ? d.piece.from : d.piece.to;
			const target = snap(edge + dt, d.points, tol);
			onLive(trimItem(d.base, d.item.ref, d.mode, target - edge));
		}
	}

	function onUp() {
		window.removeEventListener('pointermove', onMove);
		const d = drag.current;
		drag.current = null;
		if (!d) return;
		if (d.moved) onCommit(d.base, latest.current);
		else seek(d.piece.from);
	}

	// The drag handlers above are attached once per drag; read the newest plan through a ref.
	const latest = useRef(plan);
	latest.current = plan;

	function scrub(e: ReactPointerEvent) {
		if (e.button !== 0) return;
		seek(timeAt(e.clientX));
		const move = (ev: PointerEvent) => seek(timeAt(ev.clientX));
		window.addEventListener('pointermove', move);
		window.addEventListener('pointerup', () => window.removeEventListener('pointermove', move), {once: true});
	}

	function laneDown(e: ReactPointerEvent) {
		if (e.target !== e.currentTarget) return;
		onSelect(null);
		scrub(e);
	}

	function dragOver(e: DragEvent) {
		if (!e.dataTransfer.types.includes(DRAG_TYPE)) return;
		e.preventDefault();
		e.dataTransfer.dropEffect = 'copy';
		setDropAt(timeAt(e.clientX));
	}

	function drop(e: DragEvent) {
		const raw = e.dataTransfer.getData(DRAG_TYPE);
		setDropAt(null);
		if (!raw) return;
		e.preventDefault();
		const at = snapping ? snap(timeAt(e.clientX), snapPoints(plan, items), 8 / pps) : timeAt(e.clientX);
		onDrop(JSON.parse(raw) as BinPayload, at);
	}

	return (
		<div className="tl">
			<div className="tl-labels">
				<div className="tl-ruler-label">{fmtTime(playhead)}</div>
				{TRACKS.map((t) => (
					<div key={t.id} className="tl-label" title={t.hint}>
						{t.label}
					</div>
				))}
			</div>
			<div className="tl-scroll" ref={scroller} onDragOver={dragOver} onDragLeave={() => setDropAt(null)} onDrop={drop}>
				<div className="tl-inner" style={{width: width + 40}}>
					<div className="tl-ruler" onPointerDown={scrub}>
						{ticks.map((t) => (
							<span key={t} className="tl-tick" style={{left: t * pps}}>
								{fmtTime(t).replace(/\.0$/, '')}
							</span>
						))}
					</div>
					{TRACKS.map((t) => (
						<div key={t.id} className={`tl-lane tl-lane-${t.id}`} onPointerDown={laneDown}>
							{byTrack.get(t.id)!.flatMap((it) =>
								it.pieces.map((p, i) => (
									<div
										key={`${it.key}#${i}`}
										className={`tl-block tone-${it.tone}${selected === it.key ? ' selected' : ''}`}
										style={{left: p.from * pps, width: Math.max(4, (p.to - p.from) * pps)}}
										title={`${it.label || TRACKS.find((x) => x.id === it.track)!.label} · ${fmtTime(p.from)}–${fmtTime(p.to)}${it.pieces.length > 1 ? ' · also plays in the hook' : ''}`}
										onPointerDown={(e) => startDrag(e, it, p, 'move')}
									>
										{it.track !== 'captions' && <span className="tl-handle left" onPointerDown={(e) => startDrag(e, it, p, 'start')} />}
										<span className="tl-text">{it.label}</span>
										{it.track !== 'captions' && <span className="tl-handle right" onPointerDown={(e) => startDrag(e, it, p, 'end')} />}
									</div>
								)),
							)}
						</div>
					))}
					<div className="tl-playhead" style={{left: playhead * pps}} />
					{dropAt !== null && <div className="tl-drop" style={{left: dropAt * pps}} />}
				</div>
			</div>
		</div>
	);
}
