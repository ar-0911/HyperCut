'use client';

import {Player} from '@remotion/player';
import {useEffect, useMemo, useState} from 'react';
import {HyperCut, calculateMetadata} from '@render/HyperCut';
import type {EditPlan} from '@render/plan';
import {fileUrl, getJob, savePlan, startRender, type Job} from '@/lib/api';
import {chooseHook, editWord} from '@/lib/rehook';

export default function Editor({job}: {job: Job}) {
	const [plan, setPlan] = useState<EditPlan>(job.plan as EditPlan);
	const [dirty, setDirty] = useState(false);
	const [render, setRender] = useState<Job['render']>(job.render);
	const [renderError, setRenderError] = useState<string | null>(job.render_error);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);

	const meta = useMemo(() => calculateMetadata({props: {plan, videoSrc: ''}}), [plan]);
	const inputProps = useMemo(() => ({plan, videoSrc: fileUrl(job.id, 'normalized.mp4')}), [plan, job.id]);

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

	function update(next: EditPlan) {
		setPlan(next);
		setDirty(true);
		setRender(null); // any earlier render no longer matches
	}

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

	const save = () =>
		run(async () => {
			await savePlan(job.id, plan);
			setDirty(false);
		});

	const renderNow = () =>
		run(async () => {
			if (dirty) {
				await savePlan(job.id, plan);
				setDirty(false);
			}
			await startRender(job.id);
			setRender('running');
			setRenderError(null);
		});

	const hook = plan.hook;
	return (
		<div className="editor">
			<div>
				<div className="player">
					<Player
						component={HyperCut}
						inputProps={inputProps}
						durationInFrames={meta.durationInFrames}
						fps={meta.fps}
						compositionWidth={meta.width}
						compositionHeight={meta.height}
						style={{width: '100%'}}
						controls
					/>
				</div>
			</div>

			<div>
				<div className="card">
					<h2>Hook</h2>
					{hook.candidates.length === 0 ? (
						<p className="muted">No hook candidates were found for this video.</p>
					) : (
						<div className="hooks">
							{hook.candidates.map((c, i) => (
								<button
									key={i}
									className={`hook${i === hook.chosen ? ' chosen' : ''}`}
									onClick={() => update(chooseHook(plan, i))}
								>
									“{c.text}”
									<small>
										{c.start.toFixed(1)}s–{c.end.toFixed(1)}s · score {Math.round(c.score * 100)}
										{c.why ? ` · ${c.why}` : ''}
									</small>
								</button>
							))}
						</div>
					)}
					{hook.candidates.length > 0 && (
						<p className="row" style={{marginTop: 12}}>
							<label style={{margin: 0}}>
								<input
									type="checkbox"
									checked={hook.strategy === 'trim'}
									onChange={(e) => update(chooseHook(plan, hook.chosen, e.target.checked ? 'trim' : 'cold_open'))}
								/>{' '}
								Start the video at the hook instead of a cold open
							</label>
						</p>
					)}
				</div>

				<div className="card">
					<h2>Transcript</h2>
					<p className="muted" style={{marginTop: 0}}>Fix words here; timings stay as spoken.</p>
					<div className="words">
						{plan.transcript.words.map((w, i) => (
							<input
								key={i}
								aria-label={`word ${i + 1}`}
								value={w.text}
								size={Math.max(2, w.text.length)}
								onChange={(e) => update(editWord(plan, i, e.target.value))}
							/>
						))}
					</div>
				</div>

				<div className="card">
					<h2>Export</h2>
					<div className="row">
						<button disabled={!dirty || busy} onClick={save}>
							Save changes
						</button>
						<button className="primary" disabled={busy || render === 'running'} onClick={renderNow}>
							{render === 'running' ? 'Rendering…' : 'Render'}
						</button>
						{render === 'done' && (
							<a className="btn" href={fileUrl(job.id, 'output.mp4')} download>
								Download mp4
							</a>
						)}
					</div>
					{render === 'error' && <p className="error">Render failed: {renderError}</p>}
					{error && <p className="error">{error}</p>}
				</div>
			</div>
		</div>
	);
}
