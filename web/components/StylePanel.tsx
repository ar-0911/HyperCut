'use client';

import {CAPTION_FONTS, captionFamily, captionWeight} from '@render/fonts';
import type {BackgroundKind, CaptionStyle, Depth, EditPlan, TransitionStyle, Transitions} from '@render/plan';
import {useState} from 'react';

const PAUSES = [
	{value: 0.08, label: 'Tight'},
	{value: 0.15, label: 'Natural'},
	{value: 0.3, label: 'Relaxed'},
];

const CUTS: {value: TransitionStyle; label: string; hint: string}[] = [
	{value: 'hard', label: 'Hard cuts', hint: 'Straight cuts, fastest feel'},
	{value: 'smooth', label: 'Smooth', hint: 'A quick crossfade at each cut'},
	{value: 'zoom', label: 'Zoom cuts', hint: 'Alternating punch-in hides jump cuts'},
];

const BACKGROUNDS: {value: BackgroundKind; label: string}[] = [
	{value: 'original', label: 'Original'},
	{value: 'blur', label: 'Blurred'},
	{value: 'dim', label: 'Dimmed'},
	{value: 'gradient', label: 'Gradient'},
	{value: 'color', label: 'Colour'},
];

/** Pace, cuts, caption look and green-screen effects for the whole reel. */
export default function StylePanel({
	plan,
	onChange,
	onRecut,
}: {
	plan: EditPlan;
	onChange: (plan: EditPlan) => void;
	/** Rebuild the cuts for new pacing (server side, uses the audio). */
	onRecut: (plan: EditPlan) => Promise<void>;
}) {
	const [recutting, setRecutting] = useState(false);
	const {pacing, transitions, caption} = plan.style;
	const setCaption = (patch: Partial<CaptionStyle>) => onChange({...plan, style: {...plan.style, caption: {...caption, ...patch}}});
	const depth: Depth = plan.style.depth ?? {enabled: false, background: 'original', behind_titles: true};
	const setDepth = (patch: Partial<Depth>) => onChange({...plan, style: {...plan.style, depth: {...depth, ...patch}}});
	const setTransitions = (patch: Partial<Transitions>) => onChange({...plan, style: {...plan.style, transitions: {...transitions, ...patch}}});
	const pause = PAUSES.reduce((best, p) => (Math.abs(p.value - pacing.keep_pause) < Math.abs(best.value - pacing.keep_pause) ? p : best), PAUSES[0]);

	async function setPause(value: number) {
		if (value === pacing.keep_pause) return;
		setRecutting(true);
		try {
			await onRecut({...plan, style: {...plan.style, pacing: {...pacing, keep_pause: value}}});
		} finally {
			setRecutting(false);
		}
	}

	return (
		<div className="style-panel">
			<h3>Pace</h3>
			<label className="field">
				<span>
					Speed: {pacing.speed === 1 ? 'normal' : `${Math.round(pacing.speed * 100)}%`}
				</span>
				<input
					type="range"
					min={0.7}
					max={1.3}
					step={0.05}
					value={pacing.speed}
					onChange={(e) => onChange({...plan, style: {...plan.style, pacing: {...pacing, speed: Number(e.target.value)}}})}
				/>
				<span className="range-labels">
					<span>Slower</span>
					<span>Faster</span>
				</span>
			</label>
			<div className="field">
				<span>Pauses between cuts</span>
				<div className="seg">
					{PAUSES.map((p) => (
						<button key={p.value} className={pause.value === p.value ? 'active' : ''} disabled={recutting} onClick={() => setPause(p.value)}>
							{p.label}
						</button>
					))}
				</div>
				<span className="hint">{recutting ? 'Re-cutting…' : 'Re-cuts the video; clips you deleted by hand come back.'}</span>
			</div>

			<h3>Cuts</h3>
			<div className="seg">
				{CUTS.map((c) => (
					<button key={c.value} className={transitions.style === c.value ? 'active' : ''} title={c.hint} onClick={() => setTransitions({style: c.value})}>
						{c.label}
					</button>
				))}
			</div>
			<p className="hint">{CUTS.find((c) => c.value === transitions.style)?.hint}</p>
			<label className="field">
				<span>Fade out at the end: {transitions.fade_out.toFixed(1)}s</span>
				<input type="range" min={0} max={2} step={0.1} value={transitions.fade_out} onChange={(e) => setTransitions({fade_out: Number(e.target.value)})} />
			</label>

			<h3>Green screen</h3>
			<label className="check">
				<input type="checkbox" checked={depth.enabled} onChange={(e) => setDepth({enabled: e.target.checked})} /> Cut the speaker out
			</label>
			<p className="hint">Lets titles sit behind your head and swaps the background. Off unless you turn it on.</p>
			{depth.enabled && (
				<div className="field">
					<span>Background</span>
					<div className="seg">
						{BACKGROUNDS.map((b) => (
							<button key={b.value} className={depth.background === b.value ? 'active' : ''} onClick={() => setDepth({background: b.value})}>
								{b.label}
							</button>
						))}
					</div>
				</div>
			)}

			<h3>Caption font</h3>
			<div className="fonts">
				{CAPTION_FONTS.map((f) => (
					<button
						key={f.name}
						className={`font${caption.font === f.name ? ' active' : ''}`}
						onClick={() => setCaption({font: f.name})}
						title={f.feel}
						style={{fontFamily: `"${captionFamily(f.name)}", sans-serif`, fontWeight: captionWeight(f.name, caption.weight)}}
					>
						{caption.uppercase ? f.name.toUpperCase() : f.name}
					</button>
				))}
			</div>
			<label className="field">
				<span>Size: {caption.size}px</span>
				<input type="range" min={40} max={110} step={2} value={caption.size} onChange={(e) => setCaption({size: Number(e.target.value)})} />
			</label>
			<div className="row">
				<label className="color">
					<input type="color" value={caption.color} onChange={(e) => setCaption({color: e.target.value.toUpperCase()})} /> Text
				</label>
				<label className="color">
					<input type="color" value={caption.highlight_color} onChange={(e) => setCaption({highlight_color: e.target.value.toUpperCase()})} /> Highlight
				</label>
				<label className="check">
					<input type="checkbox" checked={caption.uppercase} onChange={(e) => setCaption({uppercase: e.target.checked})} /> ALL CAPS
				</label>
			</div>
			<div className="row">
				<label className="field" style={{flex: 1}}>
					<span>Position</span>
					<select value={caption.position} onChange={(e) => setCaption({position: e.target.value as CaptionStyle['position']})}>
						<option value="bottom">Bottom</option>
						<option value="middle">Middle</option>
						<option value="top">Top</option>
					</select>
				</label>
				<label className="field" style={{flex: 1}}>
					<span>Animation</span>
					<select value={caption.animation} onChange={(e) => setCaption({animation: e.target.value as CaptionStyle['animation']})}>
						<option value="pop">Pop</option>
						<option value="karaoke">Karaoke</option>
						<option value="bounce">Bounce</option>
						<option value="typewriter">Typewriter</option>
					</select>
				</label>
			</div>
		</div>
	);
}
