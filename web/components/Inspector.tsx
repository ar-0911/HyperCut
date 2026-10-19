'use client';

import type {EditPlan, Graphic, LayoutMode} from '@render/plan';
import {isAroundType, isStageType, isVisualType} from '@render/layout';
import {
	GRAPHIC_NAMES,
	LAYOUT_NAMES,
	fmtTime,
	modeUnder,
	showAs,
	updateGraphic,
	type Item,
} from '@/lib/timeline';

function Field({label, children}: {label: string; children: React.ReactNode}) {
	return (
		<label className="field">
			<span>{label}</span>
			{children}
		</label>
	);
}

/** Text fields for the graphic types people edit by hand. */
function GraphicFields({plan, g, onChange}: {plan: EditPlan; g: Graphic; onChange: (p: EditPlan) => void}) {
	const set = (props: Record<string, unknown>) => onChange(updateGraphic(plan, g.id, {props}));
	const text = (key: string, label: string) => (
		<Field label={label} key={key}>
			<input type="text" value={String(g.props[key] ?? '')} onChange={(e) => set({[key]: e.target.value})} />
		</Field>
	);
	switch (g.type) {
		case 'kinetic_text':
			return text('text', 'Text');
		case 'stat_card':
			return (
				<>
					{text('value', 'Number')}
					{text('label', 'Label')}
				</>
			);
		case 'lower_third':
			return (
				<>
					{text('title', 'Name')}
					{text('subtitle', 'Subtitle')}
				</>
			);
		case 'emoji_burst':
			return text('emoji', 'Emoji');
		case 'list_build':
			return (
				<>
					{text('title', 'Title')}
					<Field label="Items, one per line">
						<textarea
							value={(Array.isArray(g.props.items) ? g.props.items : []).join('\n')}
							onChange={(e) => set({items: e.target.value.split('\n')})}
						/>
					</Field>
				</>
			);
		case 'orbit':
		case 'fly_out':
			return (
				<>
					<Field label="Things to draw, one per line">
						<textarea
							value={(Array.isArray(g.props.items) ? g.props.items : []).join('\n')}
							onChange={(e) => set({items: e.target.value.split('\n')})}
						/>
					</Field>
					<p className="hint">
						Passes behind and in front of the speaker, never over the face. New items show a stock icon here and are
						drawn to match when you render.
					</p>
				</>
			);
		case 'card_stack': {
			const cards = (Array.isArray(g.props.cards) ? g.props.cards : []) as Record<string, unknown>[];
			return (
				<>
					<Field label="Cards, one title per line (up to 3)">
						<textarea
							value={cards.map((c) => String(c.title ?? '')).join('\n')}
							onChange={(e) =>
								set({
									// A card keeps its drawing while its title stays the same; a new title is drawn when you render.
									cards: e.target.value
										.split('\n')
										.slice(0, 3)
										.map((title) => cards.find((c) => c.title === title) ?? {title, brief: title}),
								})
							}
						/>
					</Field>
					<p className="hint">Illustrated cards slide out from behind the speaker into the free side of the frame.</p>
				</>
			);
		}
		case 'motion':
			return (
				<>
					{text('title', 'Title')}
					<Field label="What to show in 3D">
						<textarea
							value={String(g.props.idea ?? '')}
							// A new idea is designed again when you render.
							onChange={(e) => set({idea: e.target.value, scene: null})}
						/>
					</Field>
					<p className="hint">Takes the whole frame for a few seconds while the speaker keeps talking.</p>
				</>
			);
		case 'scene':
			return (
				<>
					<Field label="What to draw behind the speaker">
						<textarea
							value={String(g.props.brief ?? '')}
							// A new description is drawn when you render.
							onChange={(e) => set({brief: e.target.value, layers: []})}
						/>
					</Field>
					<p className="hint">The room is replaced by a drawn scene and the speaker steps back a little so it shows.</p>
				</>
			);
		case 'chart': {
			const list = (key: string) => (Array.isArray(g.props[key]) ? (g.props[key] as unknown[]).join(', ') : '');
			return (
				<>
					{text('headline', 'Headline')}
					<Field label="Kind">
						<select value={g.props.kind === 'bars' ? 'bars' : 'line'} onChange={(e) => set({kind: e.target.value})}>
							<option value="line">Line</option>
							<option value="bars">Bars</option>
						</select>
					</Field>
					<Field label="Values, comma separated">
						<input
							type="text"
							value={list('values')}
							onChange={(e) => set({values: e.target.value.split(',').map((v) => Number(v.trim())).filter((v) => Number.isFinite(v))})}
						/>
					</Field>
					<Field label="Labels, comma separated">
						<input type="text" value={list('labels')} onChange={(e) => set({labels: e.target.value.split(',').map((v) => v.trim())})} />
					</Field>
					{text('unit', 'Unit')}
				</>
			);
		}
		case 'particles':
			return (
				<Field label="Kind">
					<select value={String(g.props.kind ?? 'sparkles')} onChange={(e) => set({kind: e.target.value})}>
						<option value="sparkles">Sparkles</option>
						<option value="bokeh">Soft lights</option>
						<option value="confetti">Confetti</option>
						<option value="embers">Embers</option>
					</select>
				</Field>
			);
		case 'illustration':
			return (
				<>
					{text('title', 'Title')}
					{typeof g.props.brief === 'string' && <p className="hint">Drawn from: {g.props.brief}</p>}
				</>
			);
		case 'media':
			return (
				<>
					{text('label', 'Name')}
					<Field label="Fit">
						<select value={g.props.fit === 'contain' ? 'contain' : 'cover'} onChange={(e) => set({fit: e.target.value})}>
							<option value="cover">Fill the frame (crop edges)</option>
							<option value="contain">Show it whole</option>
						</select>
					</Field>
					{g.props.kind === 'video' && (
						<Field label="Start the clip at (seconds)">
							<input
								type="number"
								min={0}
								step={0.1}
								max={typeof g.props.duration === 'number' ? g.props.duration : undefined}
								value={Number(g.props.trim_start ?? 0)}
								onChange={(e) => set({trim_start: Math.max(0, Number(e.target.value) || 0)})}
							/>
						</Field>
					)}
				</>
			);
		default:
			return null;
	}
}

export default function Inspector({
	plan,
	item,
	onChange,
	onDelete,
	onDuplicate,
	onSplit,
}: {
	plan: EditPlan;
	item: Item | null;
	onChange: (p: EditPlan) => void;
	onDelete: () => void;
	onDuplicate: () => void;
	onSplit: () => void;
}) {
	if (!item) {
		return (
			<div className="card inspector">
				<h2>Inspector</h2>
				<p className="hint">Click a block on the timeline to edit it. Drag blocks to move them, drag their edges to trim, press Delete to remove.</p>
				<p className="hint">Shortcuts: Space play/pause · Delete remove · ⌘/Ctrl+Z undo · ⇧⌘Z redo · ⌘/Ctrl+D duplicate · S split clip at playhead</p>
			</div>
		);
	}
	const {ref} = item;
	const when = item.pieces.map((p) => `${fmtTime(p.from)}–${fmtTime(p.to)}`).join(' and ');
	const g = ref.kind === 'graphic' ? plan.graphics.find((x) => x.id === ref.id) : undefined;
	const title =
		ref.kind === 'graphic' && g
			? GRAPHIC_NAMES[g.type]
			: ref.kind === 'zoom'
				? 'Zoom'
				: ref.kind === 'layout'
					? 'Layout'
					: ref.kind === 'segment'
						? 'Clip'
						: 'Caption line';

	return (
		<div className="card inspector">
			<h2>{title}</h2>
			<p className="hint">
				Plays at {when}
				{item.pieces.length > 1 ? ' (it also plays in the hook at the start)' : ''}
			</p>

			{g && <GraphicFields plan={plan} g={g} onChange={onChange} />}

			{g && g.type !== 'progress_bar' && !isAroundType(g.type) && !isStageType(g.type) && (
				<label className="check">
					<input
						type="checkbox"
						checked={g.layer === 'behind'}
						onChange={(e) =>
							onChange({
								...plan,
								// Behind the speaker needs the speaker cut out, so this turns green-screen effects on.
								style: e.target.checked ? {...plan.style, depth: {...plan.style.depth, enabled: true}} : plan.style,
								graphics: plan.graphics.map((x) => (x.id === g.id ? {...x, layer: e.target.checked ? 'behind' : 'front'} : x)),
							})
						}
					/>{' '}
					Behind the speaker
				</label>
			)}

			{g && isVisualType(g.type) && g.layer !== 'behind' && (
				<Field label="Show as">
					<div className="seg">
						{(['split', 'visual'] as const).map((m) => (
							<button key={m} className={modeUnder(plan, g) === m ? 'active' : ''} onClick={() => onChange(showAs(plan, g.id, m))}>
								{m === 'split' ? 'Split screen' : 'Full screen'}
							</button>
						))}
					</div>
				</Field>
			)}

			{ref.kind === 'zoom' && plan.zooms[ref.index] && (
				<>
					<Field label={`Strength: ${Math.round((plan.zooms[ref.index].scale - 1) * 100)}%`}>
						<input
							type="range"
							min={1.02}
							max={1.6}
							step={0.01}
							value={plan.zooms[ref.index].scale}
							onChange={(e) => onChange({...plan, zooms: plan.zooms.map((z, i) => (i === ref.index ? {...z, scale: Number(e.target.value)} : z))})}
						/>
					</Field>
					<Field label="Motion">
						<select
							value={plan.zooms[ref.index].ease}
							onChange={(e) => onChange({...plan, zooms: plan.zooms.map((z, i) => (i === ref.index ? {...z, ease: e.target.value as typeof z.ease} : z))})}
						>
							<option value="ease_in_out">Smooth</option>
							<option value="snap">Punch</option>
							<option value="linear">Steady</option>
						</select>
					</Field>
				</>
			)}

			{ref.kind === 'layout' && plan.layout[ref.index] && (
				<Field label="Mode">
					<div className="seg">
						{(['speaker', 'split', 'visual'] as LayoutMode[]).map((m) => (
							<button
								key={m}
								className={plan.layout[ref.index].mode === m ? 'active' : ''}
								onClick={() => onChange({...plan, layout: plan.layout.map((l, i) => (i === ref.index ? {...l, mode: m} : l))})}
							>
								{LAYOUT_NAMES[m]}
							</button>
						))}
					</div>
					<span className="hint">Split and full screen only show when a visual is on the Visuals track.</span>
				</Field>
			)}

			{ref.kind === 'segment' && <p className="hint">This is a piece of your footage. Delete it to cut it out of the short, or split it at the playhead first.</p>}
			{ref.kind === 'caption' && <p className="hint">“{item.label}”. Delete removes this line of subtitles; fix words in the Captions tab.</p>}

			<div className="row" style={{marginTop: 12}}>
				{(ref.kind === 'graphic' || ref.kind === 'zoom') && <button onClick={onDuplicate}>Duplicate</button>}
				{ref.kind === 'segment' && <button onClick={onSplit}>Split at playhead</button>}
				<button className="danger" onClick={onDelete}>
					{ref.kind === 'segment' ? 'Cut this part' : ref.kind === 'caption' ? 'Remove captions' : 'Delete'}
				</button>
			</div>
		</div>
	);
}
