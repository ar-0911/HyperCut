import {STAGES, type Job} from '@/lib/api';

export default function Progress({job}: {job: Job}) {
	const current = job.stage ? STAGES.indexOf(job.stage as (typeof STAGES)[number]) : -1;
	return (
		<ol className="steps">
			{STAGES.map((stage, i) => {
				const cls = job.status === 'done' || i < current ? 'done' : i === current ? 'active' : '';
				return (
					<li key={stage} className={cls}>
						{cls === 'done' ? '✓ ' : ''}
						{stage}
					</li>
				);
			})}
		</ol>
	);
}
