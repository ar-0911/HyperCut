'use client';

import type {EditPlan, GraphicType, LayoutMode} from '@render/plan';
import {useRef, useState, type DragEvent} from 'react';
import {fileUrl, type Kit} from '@/lib/api';
import {GRAPHIC_NAMES, LAYOUT_NAMES, graphicLabel, removedGraphics, type Asset, type BinPayload} from '@/lib/timeline';
import {chooseHook, editWord} from '@/lib/rehook';
import BrandPanel from './BrandPanel';
import StylePanel from './StylePanel';
import {DRAG_TYPE} from './Timeline';

type Tab = 'add' | 'media' | 'style' | 'brand' | 'hook' | 'captions';

const ADDABLE: GraphicType[] = ['kinetic_text', 'stat_card', 'list_build', 'lower_third', 'progress_bar', 'motion', 'card_stack', 'scene', 'chart', 'particles'];
const ICONS: Partial<Record<GraphicType, string>> = {
	kinetic_text: 'Aa',
	stat_card: '10x',
	list_build: '☰',
	lower_third: '▭',
	emoji_burst: '✱',
	progress_bar: '━',
	illustration: '✎',
	media: '▶',
	orbit: '◌',
	fly_out: '✺',
	particles: '✦',
	card_stack: '▤',
	scene: '⛰',
	chart: '↗',
	motion: '◆',
};

/** A draggable tile; clicking it adds the thing at the playhead instead (for trackpads and touch). */
function Tile({payload, icon, label, sub, onAdd}: {payload: BinPayload; icon: React.ReactNode; label: string; sub?: string; onAdd: (p: BinPayload) => void}) {
	const start = (e: DragEvent) => {
		e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(payload));
		e.dataTransfer.effectAllowed = 'copy';
	};
	return (
		<button className="tile" draggable onDragStart={start} onClick={() => onAdd(payload)} title="Drag onto the timeline, or click to add at the playhead">
			<span className="tile-icon">{icon}</span>
			<span className="tile-label">{label}</span>
			{sub && <span className="tile-sub">{sub}</span>}
		</button>
	);
}

export default function Bin({
	jobId,
	plan,
	base,
	assets,
	onAdd,
	onChange,
	onUpload,
	onDeleteAsset,
	onRecut,
	onKit,
}: {
	jobId: string;
	plan: EditPlan;
	base: EditPlan | null;
	assets: Asset[];
	onAdd: (p: BinPayload) => void;
	onChange: (plan: EditPlan) => void;
	onUpload: (files: File[]) => Promise<void>;
	onDeleteAsset: (name: string) => void;
	onRecut: (plan: EditPlan) => Promise<void>;
	/** Put a brand kit on the edit (server side, as a new version). */
	onKit: (kit: Kit) => Promise<void>;
}) {
	const [tab, setTab] = useState<Tab>('add');
	const [uploading, setUploading] = useState(0);
	const fileInput = useRef<HTMLInputElement>(null);
	const removed = removedGraphics(plan, base);

	async function upload(files: File[]) {
		if (!files.length) return;
		setUploading((n) => n + files.length);
		try {
			await onUpload(files);
		} finally {
			setUploading((n) => n - files.length);
		}
	}

	const hook = plan.hook;
	return (
		<div className="bin card">
			<div className="tabs" role="tablist">
				{(
					[
						['add', 'Add'],
						['media', 'Media'],
						['style', 'Style'],
						['brand', 'Brand'],
						['hook', 'Hook'],
						['captions', 'Captions'],
					] as [Tab, string][]
				).map(([id, label]) => (
					<button key={id} role="tab" aria-selected={tab === id} className={`tab${tab === id ? ' active' : ''}`} onClick={() => setTab(id)}>
						{label}
					</button>
				))}
			</div>

			{tab === 'add' && (
				<>
					<p className="hint">Drag onto the timeline, or click to add at the playhead.</p>
					<h3>Text and graphics</h3>
					<div className="tiles">
						{ADDABLE.map((type) => (
							<Tile key={type} payload={{kind: 'graphic', type}} icon={ICONS[type]} label={GRAPHIC_NAMES[type]} onAdd={onAdd} />
						))}
					</div>
					<h3>Camera and layout</h3>
					<div className="tiles">
						<Tile payload={{kind: 'zoom'}} icon="⊕" label="Zoom in" onAdd={onAdd} />
						{(['split', 'visual', 'speaker'] as LayoutMode[]).map((mode) => (
							<Tile key={mode} payload={{kind: 'layout', mode}} icon={mode === 'split' ? '◫' : mode === 'visual' ? '▣' : '☺'} label={LAYOUT_NAMES[mode]} onAdd={onAdd} />
						))}
					</div>
					{removed.length > 0 && (
						<>
							<h3>Removed</h3>
							<div className="tiles">
								{removed.map((g) => (
									<Tile key={g.id} payload={{kind: 'restore', id: g.id}} icon={ICONS[g.type] ?? '•'} label={graphicLabel(g)} sub={GRAPHIC_NAMES[g.type]} onAdd={onAdd} />
								))}
							</div>
						</>
					)}
				</>
			)}

			{tab === 'media' && (
				<>
					<div
						className="dropzone"
						onClick={() => fileInput.current?.click()}
						onDragOver={(e) => {
							if (e.dataTransfer.types.includes('Files')) e.preventDefault();
						}}
						onDrop={(e) => {
							e.preventDefault();
							upload(Array.from(e.dataTransfer.files));
						}}
					>
						<strong>Import footage or pictures</strong>
						<span className="hint">Drop files here or click to choose. Clips up to a minute, shown muted over your voice.</span>
						{uploading > 0 && <span className="hint">Importing {uploading}…</span>}
					</div>
					<input
						ref={fileInput}
						type="file"
						accept="image/*,video/*"
						multiple
						hidden
						onChange={(e) => {
							upload(Array.from(e.target.files ?? []));
							e.target.value = '';
						}}
					/>
					{assets.length === 0 ? (
						<p className="hint">Nothing imported yet.</p>
					) : (
						<div className="tiles media">
							{assets.map((a) => (
								<div key={a.name} className="media-tile">
									<Tile
										payload={{kind: 'asset', asset: a}}
										icon={
											a.kind === 'image' ? (
												// eslint-disable-next-line @next/next/no-img-element
												<img src={fileUrl(jobId, a.name)} alt="" />
											) : (
												<video src={fileUrl(jobId, a.name)} muted preload="metadata" />
											)
										}
										label={a.label}
										sub={a.kind === 'video' && a.duration ? `${a.duration.toFixed(1)}s clip` : a.kind}
										onAdd={onAdd}
									/>
									<button className="link danger" onClick={() => onDeleteAsset(a.name)} title="Delete this file">
										Delete
									</button>
								</div>
							))}
						</div>
					)}
				</>
			)}

			{tab === 'style' && <StylePanel plan={plan} onChange={onChange} onRecut={onRecut} />}

			{tab === 'brand' && <BrandPanel jobId={jobId} plan={plan} onChange={onChange} onUse={onKit} />}

			{tab === 'hook' &&
				(hook.candidates.length === 0 ? (
					<p className="hint">No hook candidates were found for this video.</p>
				) : (
					<>
						<p className="hint">The line your short opens with.</p>
						<div className="hooks">
							{hook.candidates.map((c, i) => (
								<button key={i} className={`hook${i === hook.chosen ? ' chosen' : ''}`} onClick={() => onChange(chooseHook(plan, i))}>
									“{c.text}”
									<small>
										{c.start.toFixed(1)}s–{c.end.toFixed(1)}s · score {Math.round(c.score * 100)}
										{c.why ? ` · ${c.why}` : ''}
									</small>
								</button>
							))}
						</div>
						<label className="check">
							<input
								type="checkbox"
								checked={hook.strategy === 'trim'}
								onChange={(e) => onChange(chooseHook(plan, hook.chosen, e.target.checked ? 'trim' : 'cold_open'))}
							/>
							Start the video at the hook instead of a cold open
						</label>
					</>
				))}

			{tab === 'captions' && (
				<>
					<p className="hint">Fix words here; timings stay as spoken. To remove a line, select it on the Captions track and press Delete.</p>
					<div className="words">
						{plan.transcript.words.map((w, i) => (
							<input key={i} aria-label={`word ${i + 1}`} value={w.text} size={Math.max(2, w.text.length)} onChange={(e) => onChange(editWord(plan, i, e.target.value))} />
						))}
					</div>
				</>
			)}
		</div>
	);
}
