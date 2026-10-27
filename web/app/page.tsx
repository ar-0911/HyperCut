'use client';

import {useRouter} from 'next/navigation';
import {useEffect, useState, type FormEvent} from 'react';
import {clearTelemetry, createJob, startAgent, deleteRecipe, getTelemetry, setTelemetry, telemetryFileUrl, type Telemetry, openProject, generationSources, kitFileUrl, listKits, listRecipes, type Kit, type Recipe} from '@/lib/api';
import {MODES, type Mode} from '@/lib/modes';
import {PRESETS} from '@/lib/presets';

export default function UploadPage() {
	const router = useRouter();
	const [file, setFile] = useState<File | null>(null);
	const [more, setMore] = useState<File[]>([]);
	const [several, setSeveral] = useState(false);
	const [reels, setReels] = useState(4);
	const [style, setStyle] = useState('');
	const [strategy, setStrategy] = useState<'cold_open' | 'trim'>('cold_open');
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [recipes, setRecipes] = useState<Recipe[]>([]);
	const [recipe, setRecipe] = useState('');
	const [sources, setSources] = useState<string[]>([]);
	const [pictures, setPictures] = useState(false);
	const [vision, setVision] = useState('none');
	const [mode, setMode] = useState<Mode>('talking_head');
	const [kits, setKits] = useState<Kit[]>([]);
	const [kit, setKit] = useState('');
	const [projectFile, setProjectFile] = useState<File | null>(null);
	const [projectSource, setProjectSource] = useState<File | null>(null);
	const [needsSource, setNeedsSource] = useState(false);
	const [usage, setUsage] = useState<Telemetry | null>(null);

	useEffect(() => {
		listRecipes()
			.then((r) => setRecipes(r.recipes))
			.catch(() => setRecipes([])); // the upload still works without them
		listKits()
			.then((r) => setKits(r.kits))
			.catch(() => setKits([]));
		getTelemetry()
			.then(setUsage)
			.catch(() => setUsage(null));
		generationSources()
			.then((r) => setSources(r.available))
			.catch(() => setSources([])); // no keys or an older engine: everything is drawn
	}, []);

	async function forget(name: string) {
		if (!window.confirm(`Delete the recipe “${name}”?`)) return;
		try {
			await deleteRecipe(name);
			setRecipes((list) => list.filter((r) => r.name !== name));
			if (recipe === name) setRecipe('');
		} catch (err) {
			setError((err as Error).message);
		}
	}

	async function submit(e: FormEvent) {
		e.preventDefault();
		if (!file) return;
		setBusy(true);
		setError(null);
		try {
			if (several) {
				const {id} = await startAgent(file, reels, recipe ? '' : style, mode, kit);
				router.push(`/agent/${id}`);
				return;
			}
			const {id} = await createJob(file, recipe ? '' : style, strategy, recipe, pictures && sources.length > 0, vision, mode, kit, more);
			router.push(`/jobs/${id}`);
		} catch (err) {
			setError((err as Error).message);
			setBusy(false);
		}
	}

	async function open() {
		if (!projectFile) return;
		setBusy(true);
		setError(null);
		try {
			const {id} = await openProject(projectFile, projectSource);
			router.push(`/jobs/${id}`);
		} catch (err) {
			const message = (err as Error).message;
			if (/footage|original/.test(message)) setNeedsSource(true);
			setError(message);
			setBusy(false);
		}
	}

	return (
		<form onSubmit={submit}>
			<h1>New short</h1>
			<p className="sub">
				Upload a video of someone talking (10 seconds to 3 minutes) and say what it is for. HyperCut makes the first cut, suggests one
				change, and you export. Your footage is never regenerated, only cut and overlaid.
			</p>

			<div className="card">
				<label htmlFor="video">Video</label>
				<input id="video" type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
				{file && (
					<>
						<label className="check">
							<input type="checkbox" checked={several} onChange={(e) => setSeveral(e.target.checked)} />
							It is a long recording: make several reels from it
						</label>
						{several && (
							<p className="hint">
								Up to an hour.{' '}
								<select value={reels} onChange={(e) => setReels(Number(e.target.value))} aria-label="How many reels">
									{[2, 3, 4, 5, 6, 8].map((n) => (
										<option key={n} value={n}>
											{n} reels
										</option>
									))}
								</select>{' '}
								HyperCut picks the moments that work on their own, shows you the plan, then makes and checks each reel.
							</p>
						)}
					</>
				)}
				{file && !several && (
					<>
						<label htmlFor="more">More clips (optional)</label>
						<input id="more" type="file" accept="video/*" multiple onChange={(e) => setMore(Array.from(e.target.files ?? []))} />
						<p className="hint">
							{more.length
								? `${more.length + 1} clips, joined in this order: ${[file, ...more].map((f) => f.name).join(', ')}.`
								: 'Recorded in pieces? Add the rest here and they are joined in order. Retakes are cut either way, keeping the last take.'}
						</p>
					</>
				)}
			</div>

			<div className="card">
				<label>What are you making?</label>
				<div className="chips">
					{MODES.map((m) => (
						<button type="button" key={m.name} className={`chip${mode === m.name ? ' active' : ''}`} onClick={() => setMode(m.name)}>
							{m.label}
						</button>
					))}
				</div>
				<p className="hint">{MODES.find((m) => m.name === mode)?.hint} It sets how the video is cut; how it looks is under More options.</p>
			</div>

			{kits.length > 0 && (
				<div className="card">
					<label>Brand kit</label>
					<p className="hint">Your logo, music, end card and caption look on this reel. Pick it again to go without.</p>
					<div className="chips">
						{kits.map((k) => (
							<button type="button" key={k.id} className={`chip${kit === k.id ? ' active' : ''}`} onClick={() => setKit(kit === k.id ? '' : k.id)}>
								{/* eslint-disable-next-line @next/next/no-img-element */}
								{k.logo ? <img className="chip-logo" src={kitFileUrl(k.id, k.logo)} alt="" /> : null}
								{k.name}
							</button>
						))}
					</div>
				</div>
			)}

			<details className="more">
				<summary>More options: look, hook, footage understanding, pictures</summary>
			{recipes.length > 0 && (
				<div className="card">
					<label>Your recipes</label>
					<p className="hint">A recipe is a look you saved from the editor. Pick one to use it exactly; pick it again to go back to a style prompt.</p>
					<div className="chips">
						{recipes.map((r) => (
							<span key={r.name} className={`chip${recipe === r.name ? ' active' : ''}`}>
								<button type="button" className="link" onClick={() => setRecipe(recipe === r.name ? '' : r.name)}>
									{r.name}
								</button>
								<button type="button" className="link" title="Delete this recipe" onClick={() => forget(r.name)}>
									×
								</button>
							</span>
						))}
					</div>
				</div>
			)}

			<div className="card" style={recipe ? {opacity: 0.5} : undefined}>
				<label htmlFor="style">Style{recipe ? ` (using the recipe “${recipe}”)` : ''}</label>
				<div className="chips">
					{PRESETS.map((p) => (
						<button type="button" key={p.name} className="chip" onClick={() => setStyle(p.prompt)}>
							{p.name}
						</button>
					))}
				</div>
				<textarea
					id="style"
					value={style}
					onChange={(e) => setStyle(e.target.value)}
					disabled={Boolean(recipe)}
					placeholder="Describe the look, or pick a preset. Leave empty for Bold creator."
				/>
			</div>

			<div className="card">
				<label htmlFor="strategy">Hook</label>
				<select id="strategy" value={strategy} onChange={(e) => setStrategy(e.target.value as 'cold_open' | 'trim')}>
					<option value="cold_open">Cold open: play the hook first, then the whole video</option>
					<option value="trim">Trim: start the video at the hook</option>
				</select>
			</div>

			<div className="card">
				<label htmlFor="vision">Understand the footage</label>
				<select id="vision" value={vision} onChange={(e) => setVision(e.target.value)}>
					<option value="none">On this computer: shots and on-screen text</option>
					<option value="ollama">With a local vision model (Ollama must be running)</option>
					<option value="claude">With Claude: sends about 24 still frames to Claude</option>
				</select>
				<p className="hint">
					HyperCut looks at frames of the video so it can tell what is on screen when, keep shots that show what is said
					clear of graphics, and spell names the way the footage writes them. Your video never leaves this computer
					unless you pick Claude, and then only the sampled frames do.
				</p>
			</div>

			<div className="card">
				<label className="check">
					<input type="checkbox" checked={pictures} disabled={sources.length === 0} onChange={(e) => setPictures(e.target.checked)} />
					Use stock footage and AI pictures (optional)
				</label>
				<p className="hint">
					{sources.length === 0
						? 'Off: no stock or picture keys are set, so every visual is drawn. Everything else works the same.'
						: 'Some visuals become real footage or generated pictures instead of drawings. Generated ones cost a little; drawings are free.'}
				</p>
			</div>

			<div className="card">
				<label className="check">
					<input
						type="checkbox"
						checked={usage?.enabled ?? false}
						disabled={!usage}
						onChange={(e) => void setTelemetry(e.target.checked).then(setUsage).catch((err) => setError((err as Error).message))}
					/>
					Count how I use HyperCut (optional, off by default)
				</label>
				<p className="hint">
					Counts like “a render took 4 minutes” or “the suggested change was kept”, saved on this computer only. Never your video, frames,
					words, prompts or file names. Nothing is sent: you can read the file and share it if you want to help improve HyperCut.
					{usage && usage.events > 0 && (
						<>
							{' '}
							{usage.events} counted.{' '}
							<a href={telemetryFileUrl} download>
								See the file
							</a>{' '}
							·{' '}
							<button type="button" className="link" onClick={() => void clearTelemetry().then(setUsage)}>
								Delete it
							</button>
						</>
					)}
				</p>
			</div>
			</details>

			<div className="row">
				<button className="primary" disabled={!file || busy}>
					{busy ? 'Uploading…' : several ? `Make ${reels} reels` : 'Create short'}
				</button>
				{error && <span className="error">{error}</span>}
			</div>

			<div className="card">
				<label htmlFor="project">Or open a project</label>
				<p className="hint">A .hypercut file saved from the editor, with its versions. One saved without the video asks for the original, which HyperCut checks is the same file.</p>
				<input id="project" type="file" accept=".hypercut" onChange={(e) => setProjectFile(e.target.files?.[0] ?? null)} />
				{needsSource && (
					<>
						<label htmlFor="project-source">The original video</label>
						<input id="project-source" type="file" accept="video/*" onChange={(e) => setProjectSource(e.target.files?.[0] ?? null)} />
					</>
				)}
				<div className="row">
					<button type="button" disabled={!projectFile || busy} onClick={open}>
						{busy && projectFile ? 'Opening…' : 'Open project'}
					</button>
				</div>
			</div>
		</form>
	);
}
