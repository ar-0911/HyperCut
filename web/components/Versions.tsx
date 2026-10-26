'use client';

import {useState} from 'react';
import type {HistoryListing, Version} from '@/lib/api';

const KIND: Record<Version['kind'], string> = {
	pipeline: 'HyperCut’s cut',
	edit: 'Your edit',
	assistant: 'AI edit',
	review: 'Review fixes',
	restore: 'Went back',
	render: 'Drawn for render',
	import: 'Imported',
};

const when = (t: number) => new Date(t * 1000).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});

/** Every saved version of the project (ADR 0021): name the good ones, go back to any of them. Kept on disk, so it
 * survives closing the app; going back adds a new version, so nothing is lost. */
export default function Versions({
	history,
	onRestore,
	onName,
	onSaveNamed,
	dirty,
}: {
	history: HistoryListing | null;
	onRestore: (v: Version) => void;
	onName: (v: Version, label: string | null) => void;
	onSaveNamed: (label: string) => void;
	dirty: boolean;
}) {
	const [label, setLabel] = useState('');
	const [open, setOpen] = useState<number | null>(null);
	if (!history) return null;
	return (
		<div className="card versions">
			<h2>Versions</h2>
			<form
				className="row"
				onSubmit={(e) => {
					e.preventDefault();
					if (label.trim()) onSaveNamed(label.trim());
					setLabel('');
				}}
			>
				<input type="text" value={label} placeholder={dirty ? 'Name and save this edit, e.g. “tight cut”' : 'Name the current version'} onChange={(e) => setLabel(e.target.value)} maxLength={80} />
				<button type="submit" disabled={!label.trim()}>
					{dirty ? 'Save as version' : 'Name it'}
				</button>
			</form>
			<ol className="version-list">
				{history.versions.map((v) => (
					<li key={v.id} className={v.id === history.head ? 'current' : ''}>
						<div className="row">
							<button type="button" className="linkish" onClick={() => setOpen(open === v.id ? null : v.id)} title="What changed in this version">
								<strong>{v.label ?? `Version ${v.id}`}</strong> <span className="muted">{KIND[v.kind]} · {when(v.created)} · {v.duration.toFixed(1)} s</span>
							</button>
							{v.id === history.head ? (
								<span className="tag">current</span>
							) : (
								<button type="button" onClick={() => onRestore(v)} title="Make this version current again (added as a new version)">
									Go back
								</button>
							)}
							<button
								type="button"
								onClick={() => {
									const next = window.prompt('Name this version', v.label ?? '');
									if (next !== null) onName(v, next.trim() || null);
								}}
								title="Name or rename this version"
							>
								Name
							</button>
						</div>
						{v.note && <p className="hint">{v.note}</p>}
						{open === v.id && (
							<ul className="changes">{v.changes.length ? v.changes.map((c, i) => <li key={i}>{c}</li>) : <li>The first cut</li>}</ul>
						)}
					</li>
				))}
			</ol>
		</div>
	);
}
