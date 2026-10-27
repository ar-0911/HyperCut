'use client';

import {useParams} from 'next/navigation';
import {useEffect, useState} from 'react';
import Editor from '@/components/Editor';
import Progress from '@/components/Progress';
import {getJob, retryJob, type Job} from '@/lib/api';

export default function JobPage() {
	const {id} = useParams<{id: string}>();
	const [job, setJob] = useState<Job | null>(null);
	const [error, setError] = useState<string | null>(null);

	const [attempt, setAttempt] = useState(0);

	// Poll while the pipeline runs. The editor owns polling for the render afterwards.
	useEffect(() => {
		let stop = false;
		let timer: ReturnType<typeof setTimeout>;
		const tick = async () => {
			try {
				const next = await getJob(id);
				if (stop) return;
				setJob(next);
				setError(null);
				if (next.status === 'queued' || next.status === 'running') timer = setTimeout(tick, 1500);
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
	}, [id, attempt]);

	const retry = async () => {
		try {
			await retryJob(id);
			setAttempt((n) => n + 1);
		} catch (e) {
			setError((e as Error).message);
		}
	};

	if (!job) return <p className={error ? 'error' : 'muted'}>{error ?? 'Loading…'}</p>;

	return (
		<>
			<h1>{job.filename ?? 'Your short'}</h1>
			{job.manifest?.warnings?.length ? (
				<ul className="notes">
					{job.manifest.warnings.map((w) => (
						<li key={w}>{w}</li>
					))}
				</ul>
			) : null}
			{job.status === 'error' ? (
				<div className="banner">
					<p className="error">{job.interrupted ? job.error : `Processing failed: ${job.error}`}</p>
					<button className="primary" onClick={retry}>
						Try again
					</button>
				</div>
			) : job.status === 'done' && job.plan ? (
				<Editor job={job} />
			) : (
				<>
					<p className="sub">Working on it. This can take a few minutes.</p>
					<Progress job={job} />
				</>
			)}
			{error && <p className="error">{error}</p>}
		</>
	);
}
