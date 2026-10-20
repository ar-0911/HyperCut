'use client';

import {useRouter} from 'next/navigation';
import {useEffect, useState, type FormEvent} from 'react';
import {createJob, deleteRecipe, listRecipes, type Recipe} from '@/lib/api';
import {PRESETS} from '@/lib/presets';

export default function UploadPage() {
	const router = useRouter();
	const [file, setFile] = useState<File | null>(null);
	const [style, setStyle] = useState('');
	const [strategy, setStrategy] = useState<'cold_open' | 'trim'>('cold_open');
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [recipes, setRecipes] = useState<Recipe[]>([]);
	const [recipe, setRecipe] = useState('');

	useEffect(() => {
		listRecipes()
			.then((r) => setRecipes(r.recipes))
			.catch(() => setRecipes([])); // the upload still works without them
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
			const {id} = await createJob(file, recipe ? '' : style, strategy, recipe);
			router.push(`/jobs/${id}`);
		} catch (err) {
			setError((err as Error).message);
			setBusy(false);
		}
	}

	return (
		<form onSubmit={submit}>
			<h1>New short</h1>
			<p className="sub">Upload a talking-head video (10 seconds to 3 minutes). Your footage is never regenerated, only cut and overlaid.</p>

			<div className="card">
				<label htmlFor="video">Video</label>
				<input id="video" type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
			</div>

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

			<div className="row">
				<button className="primary" disabled={!file || busy}>
					{busy ? 'Uploading…' : 'Create short'}
				</button>
				{error && <span className="error">{error}</span>}
			</div>
		</form>
	);
}
