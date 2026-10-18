'use client';

import {Player, type PlayerRef} from '@remotion/player';
import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {HyperCut, calculateMetadata} from '@render/HyperCut';
import type {EditPlan} from '@render/plan';
import {
	API_URL,
	askAssistant,
	deleteAsset,
	fileUrl,
	getJob,
	recutPlan,
	requestMatte,
	restorePlan,
	savePlan,
	startRender,
	uploadAsset,
	type Job,
} from '@/lib/api';
import {useHistory} from '@/lib/history';
import {
	buildItems,
	dropOnTimeline,
	duplicateItem,
	reelDuration,
	removeItem,
	splitAt,
	type Asset,
	type BinPayload,
	type ItemRef,
} from '@/lib/timeline';
import Assistant from './Assistant';
import Bin from './Bin';
import Inspector from './Inspector';
import Timeline from './Timeline';

const PPS_STEPS = [6, 10, 16, 24, 36, 54, 80, 120];

/** Key the assistant uses for a block (graphic id, z<i>, l<i>), so "this" in a request means the selection. */
function assistantKey(ref: ItemRef | null): string | null {
	if (!ref) return null;
	if (ref.kind === 'graphic') return ref.id;
	if (ref.kind === 'zoom') return `z${ref.index}`;
	if (ref.kind === 'layout') return `l${ref.index}`;
	return null;
}

const typing = (el: EventTarget | null) => el instanceof HTMLElement && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));

export default function Editor({job}: {job: Job}) {
	const history = useHistory<EditPlan>(job.plan as EditPlan);
	const plan = history.value;
	const [saved, setSaved] = useState<EditPlan>(job.plan as EditPlan);
	const [base, setBase] = useState<EditPlan | null>(job.base_plan ?? (job.plan as EditPlan));
	const [assets, setAssets] = useState<Asset[]>(job.assets ?? []);
	const [selected, setSelected] = useState<ItemRef | null>(null);
	const [pps, setPps] = useState(16);
	const [snapping, setSnapping] = useState(true);
	const [render, setRender] = useState<Job['render']>(job.render);
	const [renderError, setRenderError] = useState<string | null>(job.render_error);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	// The speaker cut-out behind green-screen effects: made once, when the plan first asks for them.
	const [matte, setMatte] = useState<Job['matte']>(job.files.includes('matte.webm') ? 'done' : job.matte === 'error' ? 'error' : null);
	const wantsMatte = Boolean(plan.style.depth?.enabled);
	const playerRef = useRef<PlayerRef>(null);
	const dirty = plan !== saved;

	const meta = useMemo(() => calculateMetadata({props: {plan, videoSrc: ''}}), [plan]);
	const inputProps = useMemo(
		() => ({
			plan,
			videoSrc: fileUrl(job.id, 'normalized.mp4'),
			assetBase: `${API_URL}/jobs/${job.id}/files/`,
			matteSrc: matte === 'done' ? fileUrl(job.id, 'matte.webm') : undefined,
		}),
		[plan, job.id, matte],
	);
	const items = useMemo(() => buildItems(plan), [plan]);
	const duration = useMemo(() => reelDuration(plan), [plan]);
	const selectedKey = useMemo(() => {
		if (!selected) return null;
		return items.find((it) => JSON.stringify(it.ref) === JSON.stringify(selected))?.key ?? null;
	}, [items, selected]);
	const selectedItem = items.find((it) => it.key === selectedKey) ?? null;

	// Fit the whole reel in view to start with.
	const scrollArea = useRef<HTMLDivElement>(null);
	useEffect(() => {
		const w = scrollArea.current?.clientWidth ?? 900;
		const fit = (w - 160) / Math.max(1, duration);
		setPps(PPS_STEPS.reduce((best, s) => (s <= fit ? s : best), PPS_STEPS[0]));
		// Only on first load: later edits change the length and should not jump the zoom.
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);

	// While rendering, poll the job until the render settles.
	useEffect(() => {
		if (render !== 'running') return;
		const timer = setInterval(async () => {
			try {
				const next = await getJob(job.id);
				setRender(next.render);
				setRenderError(next.render_error);
			} catch (e) {
				setError((e as Error).message);
			}
		}, 2000);
		return () => clearInterval(timer);
	}, [render, job.id]);

	// Green-screen effects turned on (style prompt, AI box): make the cut-out, then poll until it is there.
	useEffect(() => {
		if (!wantsMatte || matte !== null) return;
		setMatte('running');
		requestMatte(job.id)
			.then((r) => setMatte(r.matte))
			.catch((e) => {
				setMatte('error');
				setError((e as Error).message);
			});
	}, [wantsMatte, matte, job.id]);
	useEffect(() => {
		if (matte !== 'running') return;
		const timer = setInterval(async () => {
			try {
				const next = await getJob(job.id);
				if (next.files.includes('matte.webm')) setMatte('done');
				else if (next.matte === 'error') {
					setMatte('error');
					setError(`Could not cut the speaker out: ${next.matte_error ?? 'unknown error'}`);
				}
			} catch (e) {
				setError((e as Error).message);
			}
		}, 3000);
		return () => clearInterval(timer);
	}, [matte, job.id]);

	// Don't lose edits by closing the tab.
	useEffect(() => {
		if (!dirty) return;
		const warn = (e: BeforeUnloadEvent) => e.preventDefault();
		window.addEventListener('beforeunload', warn);
		return () => window.removeEventListener('beforeunload', warn);
	}, [dirty]);

	const change = useCallback(
		(next: EditPlan) => {
			history.set(next);
			setRender((r) => (r === 'running' ? r : null)); // an earlier render no longer matches
		},
		[history],
	);

	const playhead = () => (playerRef.current?.getCurrentFrame() ?? 0) / plan.output.fps;

	async function run(fn: () => Promise<unknown>) {
		setBusy(true);
		setError(null);
		try {
			await fn();
		} catch (e) {
			setError((e as Error).message);
		} finally {
			setBusy(false);
		}
	}

	const add = (payload: BinPayload, at = playhead()) => {
		const res = dropOnTimeline(plan, payload, at, base);
		if (res.plan === plan) return;
		change(res.plan);
		setSelected(res.ref);
	};

	const remove = () => {
		if (!selected) return;
		change(removeItem(plan, selected));
		setSelected(null);
	};

	const duplicate = () => {
		if (!selected) return;
		const res = duplicateItem(plan, selected);
		change(res.plan);
		if (res.ref) setSelected(res.ref);
	};

	const split = () => change(splitAt(plan, playhead()));

	const save = () =>
		run(async () => {
			await savePlan(job.id, plan);
			setSaved(plan);
			if (!base) setBase(plan);
		});

	const renderNow = () =>
		run(async () => {
			if (dirty) {
				await savePlan(job.id, plan);
				setSaved(plan);
			}
			await startRender(job.id);
			setRender('running');
			setRenderError(null);
		});

	const restore = () => {
		if (!window.confirm('Go back to the edit HyperCut made? Your changes can still be undone afterwards.')) return;
		run(async () => {
			const original = await restorePlan(job.id);
			change(original);
			setSaved(original);
			setSelected(null);
		});
	};

	async function upload(files: File[]) {
		setError(null);
		for (const f of files) {
			try {
				const a = await uploadAsset(job.id, f);
				setAssets((list) => [...list, a]);
			} catch (e) {
				setError(`${f.name}: ${(e as Error).message}`);
			}
		}
	}

	const removeAsset = (name: string) => {
		if (plan.graphics.some((g) => g.type === 'media' && g.props.src === name)) {
			setError('That file is still on the timeline. Remove it there first.');
			return;
		}
		run(async () => {
			await deleteAsset(job.id, name);
			setAssets((list) => list.filter((a) => a.name !== name));
		});
	};

	async function ask(instruction: string) {
		const res = await askAssistant(job.id, {instruction, plan, playhead: playhead(), selected: assistantKey(selected)});
		if (JSON.stringify(res.plan) !== JSON.stringify(plan)) {
			change(res.plan);
			setSelected(null);
		}
		return res;
	}

	// Keyboard shortcuts, ignored while typing in a field.
	useEffect(() => {
		const onKey = (e: KeyboardEvent) => {
			if (typing(e.target)) return;
			const mod = e.metaKey || e.ctrlKey;
			if (mod && e.key.toLowerCase() === 'z') {
				e.preventDefault();
				if (e.shiftKey) history.redo();
				else history.undo();
			} else if (mod && e.key.toLowerCase() === 'y') {
				e.preventDefault();
				history.redo();
			} else if (mod && e.key.toLowerCase() === 'd') {
				e.preventDefault();
				duplicate();
			} else if (mod && e.key.toLowerCase() === 's') {
				e.preventDefault();
				if (dirty) save();
			} else if (e.key === 'Delete' || e.key === 'Backspace') {
				if (selected) {
					e.preventDefault();
					remove();
				}
			} else if (e.key === ' ') {
				e.preventDefault();
				playerRef.current?.toggle();
			} else if (e.key.toLowerCase() === 's' && !mod) {
				split();
			} else if (e.key === 'Escape') {
				setSelected(null);
			}
		};
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});

	const zoomBy = (dir: 1 | -1) => {
		const i = PPS_STEPS.indexOf(pps);
		setPps(PPS_STEPS[Math.min(PPS_STEPS.length - 1, Math.max(0, (i < 0 ? 2 : i) + dir))]);
	};

	return (
		<div className="editor-page">
			<div className="editor-top">
				<Bin
					jobId={job.id}
					plan={plan}
					base={base}
					assets={assets}
					onAdd={(p) => add(p)}
					onChange={change}
					onUpload={upload}
					onDeleteAsset={removeAsset}
					onRecut={async (next) => {
						setError(null);
						try {
							change(await recutPlan(job.id, next));
							setSelected(null);
						} catch (e) {
							setError((e as Error).message);
						}
					}}
				/>
				<div className="player">
					<Player
						ref={playerRef}
						component={HyperCut}
						inputProps={inputProps}
						durationInFrames={meta.durationInFrames}
						fps={meta.fps}
						compositionWidth={meta.width}
						compositionHeight={meta.height}
						style={{width: '100%'}}
						controls
						clickToPlay={false}
					/>
				</div>
				<div className="side">
					<Inspector plan={plan} item={selectedItem} onChange={change} onDelete={remove} onDuplicate={duplicate} onSplit={split} />
					<Assistant onAsk={ask} disabled={busy} />
				</div>
			</div>

			<div className="toolbar" ref={scrollArea}>
				<div className="row">
					<button onClick={history.undo} disabled={!history.canUndo} title="Undo (⌘/Ctrl+Z)">
						↶ Undo
					</button>
					<button onClick={history.redo} disabled={!history.canRedo} title="Redo (⇧⌘Z)">
						↷ Redo
					</button>
					<button onClick={split} title="Split the clip at the playhead (S)">
						✂ Split
					</button>
					<button onClick={duplicate} disabled={!selected || (selected.kind !== 'graphic' && selected.kind !== 'zoom')} title="Duplicate (⌘/Ctrl+D)">
						Duplicate
					</button>
					<button onClick={remove} disabled={!selected} title="Delete (Del)">
						Delete
					</button>
					<span className="sep" />
					<button onClick={() => zoomBy(-1)} title="Zoom out of the timeline">
						−
					</button>
					<button onClick={() => zoomBy(1)} title="Zoom into the timeline">
						+
					</button>
					<label className="check">
						<input type="checkbox" checked={snapping} onChange={(e) => setSnapping(e.target.checked)} /> Snap
					</label>
				</div>
				<div className="row">
					<button onClick={restore} disabled={busy} title="Go back to the edit HyperCut made">
						Restore original
					</button>
					<button disabled={!dirty || busy} onClick={save}>
						{dirty ? 'Save' : 'Saved'}
					</button>
					<button className="primary" disabled={busy || render === 'running'} onClick={renderNow}>
						{render === 'running' ? 'Rendering…' : 'Render video'}
					</button>
					{render === 'done' && (
						<a className="btn" href={fileUrl(job.id, 'output.mp4')} download>
							Download mp4
						</a>
					)}
				</div>
			</div>
			{render === 'running' && <p className="hint">Rendering the final video takes a few minutes. Keep editing; the preview is always live.</p>}
			{render === 'error' && <p className="error">Render failed: {renderError}</p>}
			{wantsMatte && matte === 'running' && (
				<p className="hint">Cutting the speaker out for the green-screen effects. The preview shows them once that is done (a few minutes).</p>
			)}
			{error && <p className="error">{error}</p>}

			<Timeline
				plan={plan}
				items={items}
				duration={duration}
				pps={pps}
				snapping={snapping}
				selected={selectedKey}
				playerRef={playerRef}
				onSelect={(ref) => setSelected(ref)}
				onLive={history.replace}
				onCommit={(before, after) => {
					history.replace(before);
					change(after);
				}}
				onDrop={(payload, at) => add(payload, at)}
			/>
		</div>
	);
}
