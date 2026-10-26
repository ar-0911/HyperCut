'use client';

import type {Brand, EditPlan, LogoCorner} from '@render/plan';
import {useEffect, useState} from 'react';
import {createKit, deleteKit, kitFileUrl, listKits, type Kit} from '@/lib/api';

const CORNERS: {value: LogoCorner; label: string}[] = [
	{value: 'top_left', label: 'Top left'},
	{value: 'top_right', label: 'Top right'},
	{value: 'bottom_left', label: 'Bottom left'},
	{value: 'bottom_right', label: 'Bottom right'},
];

/** Brand kits (ADR 0026): put a saved kit on this reel, adjust its logo, music and end card, or save a new kit. */
export default function BrandPanel({jobId, plan, onChange, onUse}: {
	jobId: string;
	plan: EditPlan;
	onChange: (plan: EditPlan) => void;
	/** Put a kit on the edit (server side, as a new version). */
	onUse: (kit: Kit) => Promise<void>;
}) {
	const [kits, setKits] = useState<Kit[]>([]);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [making, setMaking] = useState(false);
	const [name, setName] = useState('');
	const [logo, setLogo] = useState<File | null>(null);
	const [music, setMusic] = useState<File | null>(null);
	const [font, setFont] = useState<File | null>(null);
	const [endCard, setEndCard] = useState('');
	const [corner, setCorner] = useState<LogoCorner>('top_right');
	const brand = plan.brand;
	const setBrand = (patch: Partial<Brand>) => onChange({...plan, brand: {...brand, ...patch}});

	useEffect(() => {
		listKits()
			.then((r) => setKits(r.kits))
			.catch(() => setKits([]));
	}, []);

	async function run(action: () => Promise<void>) {
		setBusy(true);
		setError(null);
		try {
			await action();
		} catch (e) {
			setError((e as Error).message);
		} finally {
			setBusy(false);
		}
	}

	const apply = (kit: Kit) => run(() => onUse(kit));
	const remove = (kit: Kit) =>
		window.confirm(`Delete the brand kit “${kit.name}”? Reels that use it keep their copy.`) &&
		run(async () => {
			await deleteKit(kit.id);
			setKits((list) => list.filter((k) => k.id !== kit.id));
		});
	const save = () =>
		run(async () => {
			const kit = await createKit({name, fromJob: jobId, logo, music, font, endCard, logoCorner: corner, fontName: font ? name : ''});
			setKits((list) => [...list, kit]);
			setMaking(false);
			setName('');
			setLogo(null);
			setMusic(null);
			setFont(null);
			setEndCard('');
		});

	const has = brand.logo || brand.music || brand.end_card || brand.font;
	return (
		<div className="brand-panel">
			<h3>Brand kits</h3>
			<p className="hint">A kit is your captions, colours and cuts plus a logo, music and an end card, ready for every reel.</p>
			{kits.length === 0 ? <p className="hint">No kits yet.</p> : null}
			<div className="kits">
				{kits.map((k) => (
					<div key={k.id} className={`kit${brand.name === k.name ? ' active' : ''}`}>
						{/* eslint-disable-next-line @next/next/no-img-element */}
						{k.logo ? <img src={kitFileUrl(k.id, k.logo)} alt="" /> : <span className="kit-swatch" style={{background: k.colors[0] ?? '#888'}} />}
						<span className="kit-name">{k.name}</span>
						<span className="hint">{[k.caption_font, k.music ? 'music' : '', k.end_card ? 'end card' : ''].filter(Boolean).join(' · ')}</span>
						<button disabled={busy} onClick={() => apply(k)}>
							Use
						</button>
						<button className="link danger" disabled={busy} onClick={() => remove(k)} title="Delete this kit">
							×
						</button>
					</div>
				))}
			</div>
			{making ? (
				<div className="kit-form">
					<label>
						Name
						<input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Acme" />
					</label>
					<label>
						Logo (PNG with a transparent background works best)
						<input type="file" accept=".png,.jpg,.jpeg,.webp,.svg" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
					</label>
					<label>
						Logo corner
						<select value={corner} onChange={(e) => setCorner(e.target.value as LogoCorner)}>
							{CORNERS.map((c) => (
								<option key={c.value} value={c.value}>
									{c.label}
								</option>
							))}
						</select>
					</label>
					<label>
						Music (dips under the voice by itself)
						<input type="file" accept=".mp3,.m4a,.aac,.wav,.ogg" onChange={(e) => setMusic(e.target.files?.[0] ?? null)} />
					</label>
					<label>
						Font for captions (optional)
						<input type="file" accept=".ttf,.otf,.woff,.woff2" onChange={(e) => setFont(e.target.files?.[0] ?? null)} />
					</label>
					<label>
						End card line (optional)
						<input type="text" value={endCard} maxLength={80} onChange={(e) => setEndCard(e.target.value)} placeholder="e.g. Follow for more" />
					</label>
					<p className="hint">The kit keeps this reel&apos;s captions, colours and cuts. Only use music you have the rights to.</p>
					<div className="row">
						<button className="primary" disabled={busy || !name.trim()} onClick={save}>
							Save kit
						</button>
						<button className="link" onClick={() => setMaking(false)}>
							Cancel
						</button>
					</div>
				</div>
			) : (
				<button onClick={() => setMaking(true)}>Save this look as a kit…</button>
			)}

			{has ? (
				<>
					<h3>On this reel{brand.name ? `: ${brand.name}` : ''}</h3>
					{brand.logo ? (
						<>
							<label>
								Logo
								<select value={brand.logo_corner} onChange={(e) => setBrand({logo_corner: e.target.value as LogoCorner})}>
									{CORNERS.map((c) => (
										<option key={c.value} value={c.value}>
											{c.label}
										</option>
									))}
								</select>
							</label>
							<label>
								Logo size {Math.round(brand.logo_size * 100)}%
								<input type="range" min={0.05} max={0.4} step={0.01} value={brand.logo_size} onChange={(e) => setBrand({logo_size: Number(e.target.value)})} />
							</label>
							<button className="link danger" onClick={() => setBrand({logo: null})}>
								Remove the logo
							</button>
						</>
					) : null}
					{brand.music ? (
						<>
							<label>
								Music {Math.round(brand.music_volume * 100)}%
								<input type="range" min={0} max={1} step={0.05} value={brand.music_volume} onChange={(e) => setBrand({music_volume: Number(e.target.value)})} />
							</label>
							<label>
								Under the voice {Math.round(brand.duck * 100)}% of that
								<input type="range" min={0} max={1} step={0.05} value={brand.duck} onChange={(e) => setBrand({duck: Number(e.target.value)})} />
							</label>
							<button className="link danger" onClick={() => setBrand({music: null})}>
								Remove the music
							</button>
						</>
					) : null}
					<label>
						End card
						<input type="text" value={brand.end_card} maxLength={80} onChange={(e) => setBrand({end_card: e.target.value})} placeholder="No end card" />
					</label>
				</>
			) : null}
			{error && <p className="error">{error}</p>}
		</div>
	);
}
