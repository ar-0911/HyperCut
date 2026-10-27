'use client';

import type {CheckReport, QAResult} from '@/lib/api';

const clock = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;
const NAMES: Record<string, string> = {
	audio: 'Audio track',
	size: 'Size',
	frame_rate: 'Frame rate',
	duration: 'Length',
	av_sync: 'Sound and picture end together',
	black_frames: 'Black frames',
	frozen_frames: 'Frozen picture',
	audio_dropouts: 'Sound dropouts',
	loudness: 'Loudness',
	true_peak: 'Peaks',
	file: 'File',
	streams: 'Streams',
	analysis: 'Analysis',
};

/** What the automatic checks see (ADR 0023): defects in the edit as it is now, and the validation of the last export. */
export default function Quality({report, qa, onSeek}: {report: CheckReport | null; qa: QAResult | 'running' | null | undefined; onSeek: (t: number) => void}) {
	const issues = report?.issues ?? [];
	return (
		<div className="card quality">
			<h2>Checks</h2>
			{report && issues.length === 0 && <p className="hint">No problems found in the edit.</p>}
			{issues.length > 0 && (
				<ul className="why-list">
					{issues.map((i, n) => (
						<li key={n} className={i.severity}>
							<button type="button" className="linkish" onClick={() => i.at != null && onSeek(i.at)} disabled={i.at == null}>
								<span className={`tag ${i.severity}`}>{i.severity === 'fail' ? 'fix' : 'look'}</span> {i.at != null && <span className="muted">{clock(i.at)}</span>} {i.message}
							</button>
						</li>
					))}
				</ul>
			)}
			<h3>Last export</h3>
			{qa === 'running' && <p className="hint">Checking the rendered file…</p>}
			{!qa && <p className="hint">Render the video to check the file itself: size, length, black or frozen frames, sound.</p>}
			{qa && qa !== 'running' && (
				<>
					<p className={qa.ok ? 'hint' : 'error'}>{qa.ok ? 'The file passed every check.' : qa.ok === false ? 'The file has problems; see below before posting it.' : `Could not check the file: ${qa.error}`}</p>
					<ul className="why-list">
						{(qa.checks ?? []).filter((c) => c.status !== 'pass' || !qa.ok).map((c) => (
							<li key={c.name}>
								<span className={`tag ${c.status}`}>{c.status}</span> {NAMES[c.name] ?? c.name}: {c.detail}
							</li>
						))}
					</ul>
				</>
			)}
		</div>
	);
}
