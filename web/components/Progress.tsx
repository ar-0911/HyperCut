import {STAGES, type Job} from '@/lib/api';

export default function Progress({job}: {job: Job}) {
	const current = job.stage ? STAGES.indexOf(job.stage as (typeof STAGES)[number]) : -1;
	return (
		<ol className="steps">
			{/* The speaker cut-out runs only when the style asked for green-screen effects, and fetching pictures only
			    when the plan asks for stock footage or generated pictures. */}
			{STAGES.filter((stage) => (stage !== 'matte' && stage !== 'generate') || job.stage === stage).map((stage) => {
				const i = STAGES.indexOf(stage);
				const cls = job.status === 'done' || i < current ? 'done' : i === current ? 'active' : '';
				return (
					<li key={stage} className={cls}>
						{cls === 'done' ? '✓ ' : ''}
						{stage === 'matte' ? 'cut out speaker' : stage === 'generate' ? 'fetch pictures' : stage}
					</li>
				);
			})}
		</ol>
	);
}
