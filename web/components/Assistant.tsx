'use client';

import {useState, type FormEvent} from 'react';

const EXAMPLES = [
	'Remove the subtitles from 5s to 9s',
	'Add an illustration of a rocket launch at 12s with subtitles below',
	'Make the captions yellow and bigger',
	'Delete the zoom near the start',
	'Slow it down a little and smooth the cuts',
];

/** A box where you type what to change; Claude edits the plan and the result lands on the timeline as one undo step. */
export default function Assistant({onAsk, disabled}: {onAsk: (instruction: string) => Promise<{message: string; changes: string[]}>; disabled?: boolean}) {
	const [text, setText] = useState('');
	const [busy, setBusy] = useState(false);
	const [last, setLast] = useState<{message: string; changes: string[]} | null>(null);
	const [error, setError] = useState<string | null>(null);

	async function submit(e?: FormEvent) {
		e?.preventDefault();
		const instruction = text.trim();
		if (!instruction || busy) return;
		setBusy(true);
		setError(null);
		try {
			setLast(await onAsk(instruction));
			setText('');
		} catch (err) {
			setError((err as Error).message);
		} finally {
			setBusy(false);
		}
	}

	return (
		<form className="card assistant" onSubmit={submit}>
			<h2>Ask AI to edit</h2>
			<textarea
				value={text}
				placeholder="Tell it what to change, e.g. “add an illustration of a coffee cup at 0:20 with subtitles below”"
				onChange={(e) => setText(e.target.value)}
				onKeyDown={(e) => {
					if (e.key === 'Enter' && !e.shiftKey) {
						e.preventDefault();
						submit();
					}
				}}
				disabled={busy || disabled}
			/>
			<div className="row">
				<button className="primary" type="submit" disabled={busy || disabled || !text.trim()}>
					{busy ? 'Working…' : 'Apply'}
				</button>
				<span className="hint">Times are as you see them in the player. Undo if you don’t like it.</span>
			</div>
			{!last && !busy && (
				<div className="chips">
					{EXAMPLES.map((ex) => (
						<button type="button" key={ex} className="chip" onClick={() => setText(ex)}>
							{ex}
						</button>
					))}
				</div>
			)}
			{busy && <p className="hint">Thinking… new illustrations take a minute or two to draw.</p>}
			{last && (
				<div className="assistant-result">
					<p>{last.message}</p>
					{last.changes.length > 0 && (
						<ul>
							{last.changes.map((c, i) => (
								<li key={i}>{c}</li>
							))}
						</ul>
					)}
				</div>
			)}
			{error && <p className="error">{error}</p>}
		</form>
	);
}
