'use client';

import {useEffect, useState} from 'react';
import type {EditPlan} from '@render/plan';
import {getSuggestion, type Suggestion} from '@/lib/api';
import {MODES} from '@/lib/modes';

type Props = {
	jobId: string;
	plan: EditPlan;
	duration: number;
	render: string | null;
	downloadUrl: string;
	onTry: (plan: EditPlan) => void;
	onKeep: () => void;
	onExport: () => void;
	onShowAll: () => void;
};

type Step = 'loading' | 'offer' | 'trying' | 'done';

/** The first-run path (ADR 0029): your goal, the first cut, one change worth trying, export. Everything else in
 * the editor stays out of the way until asked for. */
export default function FirstSteps({jobId, plan, duration, render, downloadUrl, onTry, onKeep, onExport, onShowAll}: Props) {
	const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
	const [step, setStep] = useState<Step>('loading');
	const [before, setBefore] = useState<EditPlan | null>(null);
	const [outcome, setOutcome] = useState('');
	const [firstCut] = useState(duration); // the first cut's length, not the one being tried

	useEffect(() => {
		getSuggestion(jobId)
			.then((r) => {
				setSuggestion(r.suggestion);
				setStep(r.suggestion ? 'offer' : 'done');
				if (!r.suggestion) setOutcome('Nothing stands out: the first cut is ready as it is.');
			})
			.catch(() => {
				setStep('done');
				setOutcome('The first cut is ready.');
			});
	}, [jobId]);

	const mode = MODES.find((m) => m.name === (plan.style.mode ?? 'talking_head'));
	const tryIt = () => {
		if (!suggestion) return;
		setBefore(plan);
		onTry(suggestion.plan);
		setStep('trying');
	};
	const finish = (text: string) => {
		setStep('done');
		setOutcome(text);
	};

	return (
		<div className="card first-steps">
			<ol>
				<li className="done">
					<strong>Your goal</strong>
					<span>{mode?.label ?? 'Talking head'}</span>
				</li>
				<li className="done">
					<strong>First cut</strong>
					<span>{firstCut.toFixed(0)} s with captions, the hook first and graphics. Play it to see.</span>
				</li>
				<li className={step === 'done' ? 'done' : 'now'}>
					<strong>One change to try</strong>
					{step === 'loading' && <span className="muted">Looking for one…</span>}
					{step === 'offer' && suggestion && (
						<>
							<span>
								<b>{suggestion.label}.</b> {suggestion.why}
							</span>
							<span className="row">
								<button className="primary" onClick={tryIt}>
									Try it
								</button>
								<button onClick={() => finish('Skipped; the first cut stays as it was.')}>Skip</button>
							</span>
						</>
					)}
					{step === 'trying' && suggestion && (
						<>
							<span>
								The preview shows it now
								{suggestion.changes.length ? `: ${suggestion.changes.slice(0, 2).join('; ')}` : ''}.
							</span>
							<span className="row">
								<button className="primary" onClick={() => {
											onKeep();
											finish(`Kept and saved: ${suggestion.label.toLowerCase()}.`);
										}}>
									Keep it
								</button>
								<button
									onClick={() => {
										if (before) onTry(before);
										finish('Put back; the first cut stays as it was.');
									}}
								>
									Put it back
								</button>
							</span>
						</>
					)}
					{step === 'done' && <span>{outcome}</span>}
				</li>
				<li className={step === 'done' ? (render === 'done' ? 'done' : 'now') : ''}>
					<strong>Export</strong>
					{render === 'done' ? (
						<span className="row">
							<a className="btn primary" href={downloadUrl} download>
								Download mp4
							</a>
						</span>
					) : (
						<span className="row">
							<button className={step === 'done' ? 'primary' : ''} disabled={render === 'running'} onClick={onExport}>
								{render === 'running' ? 'Rendering… (a few minutes)' : 'Render the video'}
							</button>
						</span>
					)}
				</li>
			</ol>
			<p className="hint">
				Want to change something else? Ask the AI box in plain words, or{' '}
				<button type="button" className="link" onClick={onShowAll}>
					show all the controls
				</button>{' '}
				(timeline, graphics, style, brand, versions).
			</p>
		</div>
	);
}
