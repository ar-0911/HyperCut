'use client';

import {useParams} from 'next/navigation';
import {useEffect, useState} from 'react';
import Editor from '@/components/Editor';
import Progress from '@/components/Progress';
import {getJob, type Job} from '@/lib/api';

export default function JobPage() {
	const {id} = useParams<{id: string}>();
	const [job, setJob] = useState<Job | null>(null);
	const [error, setError] = useState<string | null>(null);

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
	}, [id]);

	if (!job) return <p className={error ? 'error' : 'muted'}>{error ?? 'Loading…'}</p>;

	return (
		<>
			<h1>{job.filename ?? 'Your short'}</h1>
			{job.status === 'error' ? (
				<p className="error">Processing failed: {job.error}</p>
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
