'use client';

import Link from 'next/link';
import {useParams} from 'next/navigation';
import {useEffect, useState} from 'react';
import {getAgent, type AgentSession} from '@/lib/api';

const STEPS = [
	{key: 'understand', label: 'Listening to the recording'},
	{key: 'plan', label: 'Choosing the moments'},
	{key: 'make', label: 'Making and checking each reel'},
] as const;

const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

/** The editing agent's session (ADR 0031): its plan first, then each reel as it is made. */
export default function AgentPage() {
	const {id} = useParams<{id: string}>();
	const [session, setSession] = useState<AgentSession | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let stop = false;
		let timer: ReturnType<typeof setTimeout>;
		const tick = async () => {
			try {
				const next = await getAgent(id);
				if (stop) return;
				setSession(next);
				setError(null);
				if (next.status === 'queued' || next.status === 'running') timer = setTimeout(tick, 2000);
			} catch (e) {
				if (stop) return;
				setError((e as Error).message);
				timer = setTimeout(tick, 4000);
			}
		};
		tick();
		return () => {
			stop = true;
			clearTimeout(timer);
		};
	}, [id]);

	if (!session) return <p className={error ? 'error' : 'muted'}>{error ?? 'Loading…'}</p>;
	const at = STEPS.findIndex((s) => s.key === session.step);
	const finished = session.status === 'done' || session.status === 'error';

	return (
		<>
			<h1>{session.filename ?? 'Your recording'}</h1>
			<p className="sub">
				{finished
					? `${session.clips.filter((c) => c.status === 'done').length} of ${session.clips.length} reels are ready. Open one to edit and export it.`
					: `Making up to ${session.count} reels. The plan shows up first; each reel opens in the editor once it is made.`}
			</p>
			{!finished && (
				<div className="card first-steps">
					<ol>
						{STEPS.map((s, i) => (
							<li key={s.key} className={i < at ? 'done' : i === at ? 'now' : ''}>
								<strong>{s.label}</strong>
							</li>
						))}
					</ol>
				</div>
			)}
			{session.status === 'error' && <p className="error">{session.error}</p>}
			{session.clips.map((c, i) => (
				<div className="card" key={`${c.start}-${c.end}`}>
					<label>
						{i + 1}. {c.title}
					</label>
					<p className="hint">
						{clock(c.start)}–{clock(c.end)} of the recording{c.reel_seconds ? `, ${c.reel_seconds.toFixed(0)} s reel` : ''}.{' '}
						{c.why}
						{c.picked_by === 'code' ? ' (Chosen without Claude.)' : ''}
					</p>
					{c.fixes.length > 0 && <p className="hint">Fixed by its own check: {c.fixes.join(' ')}</p>}
					{c.issues.length > 0 && <p className="hint">Worth a look: {c.issues.join(' ')}</p>}
					<div className="row">
						{c.status === 'done' && c.job_id ? (
							<Link className="btn primary" href={`/jobs/${c.job_id}`}>
								Open in the editor
							</Link>
						) : c.status === 'failed' ? (
							<span className="error">Could not make this one: {c.error}</span>
						) : (
							<span className="muted">{c.status === 'making' ? `Making it${c.stage ? ` (${c.stage})` : ''}…` : 'Waiting its turn'}</span>
						)}
					</div>
				</div>
			))}
			{error && <p className="error">{error}</p>}
		</>
	);
}
