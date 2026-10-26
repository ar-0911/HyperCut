'use client';

import {useEffect, useState} from 'react';
import type {EditPlan} from '@render/plan';
import {fileUrl, getJob, makeVariants, reviewRender, saveRecipe, startExport, type Job, type ReviewResult} from '@/lib/api';
import {fmtTime} from '@/lib/timeline';

/**
 * Finishing tools under the timeline: check the render (Claude looks at it), make variants, save the look as a
 * recipe, and export for Final Cut / Resolve / Premiere.
 */
export default function Finish({
	job,
	plan,
	dirty,
	rendered,
	onApply,
	onSeek,
	onSave,
}: {
	job: Job;
	plan: EditPlan;
	dirty: boolean;
	rendered: boolean;
	onApply: (p: EditPlan) => void;
	onSeek: (reelSeconds: number) => void;
	onSave: () => Promise<void>;
}) {
	const [busy, setBusy] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [review, setReview] = useState<ReviewResult | null>(null);
	const [variants, setVariants] = useState<{id: string; label: string; duration: number}[]>([]);
	const [recipe, setRecipe] = useState('');
	const [saved, setSaved] = useState<string | null>(null);
	const [exporting, setExporting] = useState<Job['export']>(job.export ?? null);
	const [exportError, setExportError] = useState<string | null>(job.export_error ?? null);

	useEffect(() => {
		if (exporting !== 'running') return;
		const timer = setInterval(async () => {
			try {
				const next = await getJob(job.id);
				setExporting(next.export ?? null);
				setExportError(next.export_error ?? null);
			} catch (e) {
				setError((e as Error).message);
			}
		}, 3000);
		return () => clearInterval(timer);
	}, [exporting, job.id]);

	async function go(name: string, fn: () => Promise<void>) {
		setBusy(name);
		setError(null);
		try {
			await fn();
		} catch (e) {
			setError((e as Error).message);
		} finally {
			setBusy(null);
		}
	}

	return (
		<div className="card finish">
			<h2>Finish</h2>
			<div className="finish-grid">
				<section>
					<h3>Check the video</h3>
					<p className="hint">Claude watches frames of the last render and flags faces covered, cut-off text and visuals that miss.</p>
					<button disabled={!rendered || busy !== null} onClick={() => go('review', async () => setReview(await reviewRender(job.id)))}>
						{busy === 'review' ? 'Watching…' : 'Check the render'}
					</button>
					{!rendered && <p className="hint">Render the video first.</p>}
					{review && (
						<div className="review">
							{review.summary && <p>{review.summary}</p>}
							{review.issues.length === 0 && <p className="hint">Nothing to fix.</p>}
							<ul>
								{review.issues.map((i, n) => (
									<li key={n} className={i.severity === 'high' ? 'high' : ''}>
										<button className="link" onClick={() => onSeek(i.at)}>
											{fmtTime(i.at)}
										</button>{' '}
										{i.problem}
										{i.fixable ? '' : ' (needs you)'}
									</li>
								))}
							</ul>
							{review.changes.length > 0 && (
								<button
									className="primary"
									onClick={() => {
										onApply(review.plan);
										setReview(null);
									}}
								>
									Apply {review.changes.length} fix{review.changes.length === 1 ? '' : 'es'}
								</button>
							)}
						</div>
					)}
				</section>

				<section>
					<h3>Variants</h3>
					<p className="hint">The same edit opening on each other hook, plus 30 s and 45 s cuts. Each opens as its own editable video.</p>
					<button
						disabled={busy !== null}
						onClick={() =>
							go('variants', async () => {
								if (dirty) await onSave();
								setVariants((await makeVariants(job.id, plan)).variants);
							})
						}
					>
						{busy === 'variants' ? 'Making…' : 'Make variants'}
					</button>
					{variants.length > 0 && (
						<ul>
							{variants.map((v) => (
								<li key={v.id}>
									<a href={`/jobs/${v.id}`} target="_blank" rel="noreferrer">
										{v.label}
									</a>{' '}
									<span className="hint">({v.duration.toFixed(0)} s)</span>
								</li>
							))}
						</ul>
					)}
				</section>

				<section>
					<h3>Save as recipe</h3>
					<p className="hint">Keep this look (captions, colours, graphics, pacing, cuts) to start new videos with.</p>
					<div className="row">
						<input type="text" placeholder="Recipe name" value={recipe} onChange={(e) => setRecipe(e.target.value)} maxLength={60} />
						<button
							disabled={!recipe.trim() || busy !== null}
							onClick={() =>
								go('recipe', async () => {
									const r = await saveRecipe(recipe.trim(), plan.style);
									setSaved(r.name);
									setRecipe('');
								})
							}
						>
							Save
						</button>
					</div>
					{saved && <p className="hint">Saved “{saved}”. Pick it when you upload the next video.</p>}
				</section>

				<section>
					<h3>Export for an editor</h3>
					<p className="hint">Final Cut Pro, DaVinci Resolve or Premiere Pro: the cuts as a timeline, captions, and the graphics as a transparent track.</p>
					<button
						disabled={busy !== null || exporting === 'running'}
						onClick={() =>
							go('export', async () => {
								if (dirty) await onSave();
								await startExport(job.id, true);
								setExporting('running');
								setExportError(null);
							})
						}
					>
						{exporting === 'running' ? 'Exporting…' : 'Export'}
					</button>{' '}
					{exporting === 'done' && (
						<a className="btn" href={fileUrl(job.id, 'hypercut-export.zip')} download>
							Download export
						</a>
					)}
					{exporting === 'running' && <p className="hint">Rendering the graphics track takes about as long as a render.</p>}
					{exporting === 'error' && <p className="error">Export failed: {exportError}</p>}
				</section>
			</div>
			{error && <p className="error">{error}</p>}
		</div>
	);
}
