'use client';

import {Player, type PlayerRef} from '@remotion/player';
import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {HyperCut, calculateMetadata} from '@render/HyperCut';
import type {EditPlan} from '@render/plan';
import {
	API_URL,
	askAssistant,
	checkPlan,
	deleteAsset,
	discardDraft,
	explainCut,
	fileUrl,
	generateAssets,
	getDraft,
	getHistory,
	getJob,
	nameVersion,
	recutPlan,
	applyKit,
	requestMatte,
	restorePlan,
	restoreVersion,
	saveDraft,
	savePlan,
	startRender,
	uploadAsset,
	type CheckReport,
	type Draft,
	type Explanation,
	type Generation,
	type HistoryListing,
	type Job,
	type Version,
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
import Finish from './Finish';
import Inspector from './Inspector';
import OnScreen from './OnScreen';
import Quality from './Quality';
import Timeline from './Timeline';
import Versions from './Versions';
import WhyPanel from './WhyPanel';

const AUTOSAVE_MS = 2500;

const PPS_STEPS = [6, 10, 16, 24, 36, 54, 80, 120];

/** Key the assistant uses for a block (graphic id, z<i>, l<i>), so "this" in a request means the selection. */
function assistantKey(ref: ItemRef | null): string | null {
	if (!ref) return null;
	if (ref.kind === 'graphic') return ref.id;
	if (ref.kind === 'zoom') return `z${ref.index}`;
	if (ref.kind === 'layout') return `l${ref.index}`;
	return null;
}

/** Stock or generated pictures the plan still waits for (requested, not fetched, not given up on). */
export const pendingAssets = (plan: EditPlan) =>
	plan.graphics.filter((g) => {
		const req = g.props.generate as {kind?: string; failed?: string} | undefined;
		return (g.type === 'media' || g.type === 'motion') && Boolean(req?.kind) && !g.props.src && !req?.failed;
	});

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
	// The version the last render is of (ADR 0028); edits saved during a render are newer than the download.
	const [renderedVersion, setRenderedVersion] = useState<number | null>(job.render_version ?? null);
	const [renderError, setRenderError] = useState<string | null>(job.render_error);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const [generation, setGeneration] = useState<Generation | undefined>(job.generation);
	const [fetching, setFetching] = useState(false);
	// The speaker cut-out behind green-screen effects: made once, when the plan first asks for them.
	const [matte, setMatte] = useState<Job['matte']>(job.files.includes('matte.webm') ? 'done' : job.matte === 'error' ? 'error' : null);
	// Saved versions on disk, an autosaved draft found on opening, and why the first cut looks as it does (ADR 0021).
	const [versions, setVersions] = useState<HistoryListing | null>(null);
	const [draft, setDraft] = useState<Draft | null>(null);
	const [autosaved, setAutosaved] = useState<number | null>(null);
	const [why, setWhy] = useState<Explanation | null>(null);
	// An assistant edit waiting to be kept or rejected; the preview shows it (or the edit before it).
	const [proposal, setProposal] = useState<{before: EditPlan; after: EditPlan; instruction: string; showing: 'after' | 'before'} | null>(null);
	const shown = proposal ? proposal[proposal.showing] : plan;
	// Automatic checks of the edit as it is now, and the validation of the last render (ADR 0023).
	const [report, setReport] = useState<CheckReport | null>(null);
	const [qa, setQa] = useState<Job['qa']>(job.qa);
	const wantsMatte = Boolean(plan.style.depth?.enabled && plan.style.depth?.cutout);
	const playerRef = useRef<PlayerRef>(null);
	const latest = useRef(plan);
	latest.current = plan;
	const dirty = plan !== saved;

	const meta = useMemo(() => calculateMetadata({props: {plan: shown, videoSrc: ''}}), [shown]);
	const inputProps = useMemo(
		() => ({
			plan: shown,
			// The light preview copy when there is one (ADR 0028); the render always uses the full video.
			videoSrc: fileUrl(job.id, job.files?.includes('proxy.mp4') ? 'proxy.mp4' : 'normalized.mp4'),
			assetBase: `${API_URL}/jobs/${job.id}/files/`,
			matteSrc: matte === 'done' ? fileUrl(job.id, 'matte.webm') : undefined,
		}),
		[shown, job.id, job.files, matte],
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
				setQa(next.qa);
				setRenderedVersion(next.render_version ?? null);
			} catch (e) {
				setError((e as Error).message);
			}
		}, 2000);
		return () => clearInterval(timer);
	}, [render, job.id]);

	// The file is checked right after the render finishes; poll until that is done too.
	useEffect(() => {
		if (qa !== 'running' || render === 'running') return;
		const timer = setInterval(async () => {
			try {
				setQa((await getJob(job.id)).qa);
			} catch {
				// keep polling
			}
		}, 2000);
		return () => clearInterval(timer);
	}, [qa, render, job.id]);

	// Re-check the edit shortly after each change (cheap: no AI, no rendering).
	useEffect(() => {
		const timer = setTimeout(() => {
			checkPlan(job.id, plan).then(setReport, () => setReport(null));
		}, 800);
		return () => clearTimeout(timer);
	}, [plan, job.id]);

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

	const refreshVersions = useCallback(() => {
		getHistory(job.id).then(setVersions, () => setVersions(null));
	}, [job.id]);

	// On opening: the versions, why the first cut is as it is, and edits autosaved but never saved (a closed tab, a crash).
	useEffect(() => {
		refreshVersions();
		explainCut(job.id).then((r) => setWhy(r.first_cut), () => setWhy(null));
		getDraft(job.id).then((r) => setDraft(r.draft), () => setDraft(null));
	}, [job.id, refreshVersions]);

	// Autosave: unsaved edits are written as a draft a moment after each change.
	useEffect(() => {
		if (!dirty) return;
		const timer = setTimeout(() => {
			saveDraft(job.id, plan).then((r) => setAutosaved(r.saved), () => undefined);
		}, AUTOSAVE_MS);
		return () => clearTimeout(timer);
	}, [plan, dirty, job.id]);

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

	/** Save `p` as a version (kind and note say who made it and why), then show it in the versions list. */
	async function commit(p: EditPlan, opts: Parameters<typeof savePlan>[2] = {}) {
		await savePlan(job.id, p, opts);
		setSaved(p);
		if (!base) setBase(p);
		setDraft(null);
		refreshVersions();
	}

	const save = () => run(() => commit(plan));

	const renderNow = () =>
		run(async () => {
			if (dirty) await commit(plan);
			await startRender(job.id);
			setRender('running');
			setRenderError(null);
			setQa(null);
		});

	const restore = () => {
		if (!window.confirm('Go back to the edit HyperCut made? Your changes can still be undone afterwards.')) return;
		run(async () => {
			const original = await restorePlan(job.id);
			change(original);
			setSaved(original);
			setSelected(null);
			refreshVersions();
		});
	};

	const goBackTo = (v: Version) => {
		if (dirty && !window.confirm('Your unsaved edits will be replaced by this version (they stay in Undo). Go back?')) return;
		run(async () => {
			const res = await restoreVersion(job.id, v.id);
			change(res.plan);
			setSaved(res.plan);
			setSelected(null);
			refreshVersions();
		});
	};

	const nameIt = (v: Version, label: string | null) => run(async () => {
		await nameVersion(job.id, v.id, label);
		refreshVersions();
	});

	const saveNamed = (label: string) =>
		run(async () => {
			if (dirty) await commit(plan, {label});
			else if (versions?.head != null) {
				await nameVersion(job.id, versions.head, label);
				refreshVersions();
			}
		});

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

	/** Fetch the pictures the plan waits for (or one again), applied as one undoable step. */
	async function fetchPictures(from: EditPlan, graphicId?: string, prompt?: string) {
		setFetching(true);
		setError(null);
		try {
			const res = await generateAssets(job.id, from, graphicId, prompt);
			setGeneration(res.generation);
			// Edits made while fetching stay: only the graphics that were fetched are taken from the answer.
			const before = new Map(from.graphics.map((g) => [g.id, JSON.stringify(g)]));
			const fetched = new Map(res.plan.graphics.filter((g) => before.get(g.id) !== JSON.stringify(g)).map((g) => [g.id, g]));
			const now = latest.current;
			change({...now, graphics: now.graphics.map((g) => fetched.get(g.id) ?? g)});
		} catch (e) {
			setError((e as Error).message);
		} finally {
			setFetching(false);
		}
	}

	/** The assistant proposes; the preview shows the result until it is kept (saved as a version) or rejected. */
	async function ask(instruction: string) {
		const res = await askAssistant(job.id, {instruction, plan, playhead: playhead(), selected: assistantKey(selected)});
		setProposal(JSON.stringify(res.plan) !== JSON.stringify(plan) ? {before: plan, after: res.plan, instruction, showing: 'after'} : null);
		return res;
	}

	const acceptProposal = () => {
		if (!proposal) return;
		const {after, instruction} = proposal;
		setProposal(null);
		change(after);
		setSelected(null);
		run(() => commit(after, {kind: 'assistant', note: instruction}));
		// Footage or pictures the assistant added are fetched right away, so the preview shows them.
		if (pendingAssets(after).some((g) => g.type === 'media')) void fetchPictures(after);
	};

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
			{draft && (
				<div className="banner">
					<p>
						You have edits from {new Date(draft.saved * 1000).toLocaleString()} that were never saved
						{draft.changes.length ? `: ${draft.changes.slice(0, 3).join('; ')}${draft.changes.length > 3 ? '…' : ''}` : ''}.
					</p>
					<button
						className="primary"
						onClick={() => {
							change(draft.plan);
							setDraft(null);
						}}
					>
						Recover them
					</button>
					<button
						onClick={() => {
							setDraft(null);
							void discardDraft(job.id);
						}}
					>
						Discard
					</button>
				</div>
			)}
			{proposal && <p className="hint">The preview shows the AI’s proposed edit ({proposal.showing}). Keep or reject it in the AI box.</p>}
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
					onKit={async (kit) => {
						// The kit goes on the saved edit, so save unsaved edits first.
						if (dirty) await commit(plan);
						const res = await applyKit(job.id, kit.id);
						change(res.plan);
						setSaved(res.plan);
						setSelected(null);
						refreshVersions();
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
					<OnScreen plan={plan} playerRef={playerRef} onSelect={setSelected} />
				</div>
				<div className="side">
					<Inspector
						plan={plan}
						item={selectedItem}
						onChange={change}
						onDelete={remove}
						onDuplicate={duplicate}
						onSplit={split}
						onRegenerate={generation?.available.length ? (id, prompt) => void fetchPictures(plan, id, prompt) : undefined}
					/>
					<Assistant
						onAsk={ask}
						disabled={busy}
						proposal={
							proposal && {
								showing: proposal.showing,
								onAccept: acceptProposal,
								onReject: () => setProposal(null),
								onToggle: () => setProposal({...proposal, showing: proposal.showing === 'after' ? 'before' : 'after'}),
							}
						}
					/>
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
					{pendingAssets(plan).length > 0 && generation?.available.length ? (
						<button disabled={busy || fetching} onClick={() => void fetchPictures(plan)} title="Fetch the stock footage and generated pictures still missing">
							{fetching ? 'Fetching pictures…' : `Fetch ${pendingAssets(plan).length} picture${pendingAssets(plan).length === 1 ? '' : 's'}`}
						</button>
					) : null}
					{generation && generation.spent > 0 ? (
						<span className="hint" title="What generating pictures and clips has cost for this video, and its limit">
							${generation.spent.toFixed(2)} of ${generation.budget.toFixed(2)}
						</span>
					) : null}
					{dirty && autosaved && <span className="hint" title="Unsaved edits are kept on disk; reopening offers them back">Draft kept {new Date(autosaved * 1000).toLocaleTimeString()}</span>}
					<button disabled={!dirty || busy} onClick={save} title="Save as a new version (⌘/Ctrl+S)">
						{dirty ? 'Save version' : 'Saved'}
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
			{render === 'running' && (
				<p className="hint">Rendering the final video takes a few minutes. Keep editing and saving: the render is of the version you started it on.</p>
			)}
			{render === 'done' && renderedVersion != null && (dirty || (versions?.head != null && versions.head !== renderedVersion)) && (
				<p className="hint">The download is version {renderedVersion}; your edits since then need another render.</p>
			)}
			{render === 'error' && <p className="error">Render failed: {renderError}</p>}
			{wantsMatte && matte === 'running' && (
				<p className="hint">Cutting the speaker out for the green-screen effects. The preview shows them once that is done (a few minutes).</p>
			)}
			{fetching && <p className="hint">Fetching stock footage and generating pictures. Clips can take a minute or two each.</p>}
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

			<Finish
				job={job}
				plan={plan}
				dirty={dirty}
				rendered={render === 'done' && !dirty}
				onApply={(p) => {
					change(p);
					setSelected(null);
				}}
				onSeek={(t) => playerRef.current?.seekTo(Math.round(t * plan.output.fps))}
				onSave={() => commit(plan)}
			/>

			<div className="history-row">
				<Quality report={report} qa={render === 'done' ? qa : null} onSeek={(t) => playerRef.current?.seekTo(Math.round(t * plan.output.fps))} />
				<WhyPanel why={why} onSeek={(t) => playerRef.current?.seekTo(Math.round(t * plan.output.fps))} />
				<Versions history={versions} dirty={dirty} onRestore={goBackTo} onName={nameIt} onSaveNamed={saveNamed} />
			</div>
		</div>
	);
}
