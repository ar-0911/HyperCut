import type {EditPlan, LogoCorner, Style} from '@render/plan';
import type {Asset} from '@/lib/timeline';

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

export const STAGES = ['ingest', 'transcribe', 'style', 'look', 'analyze', 'matte', 'generate'] as const;
export type Stage = (typeof STAGES)[number];

export type Job = {
	id: string;
	status: 'queued' | 'running' | 'done' | 'error';
	stage: Stage | 'done' | null;
	error: string | null;
	render: 'running' | 'done' | 'error' | null;
	render_error: string | null;
	/** The speaker cut-out for green-screen effects (made only when the user asks for those). */
	matte?: 'running' | 'done' | 'error' | null;
	matte_error?: string | null;
	style: string;
	hook_strategy: 'cold_open' | 'trim';
	filename?: string;
	plan: EditPlan | null;
	/** The plan as the pipeline made it (before any edit). */
	base_plan: EditPlan | null;
	assets: Asset[];
	files: string[];
	/** Stock and generated pictures: what this machine can fetch and what this video has spent (ADR 0016). */
	generation?: Generation;
	/** The Final Cut / Resolve / Premiere export (ADR 0017). */
	export?: 'running' | 'done' | 'error' | null;
	export_error?: string | null;
	/** The job this one is a variant of (ADR 0018). */
	variant_of?: string;
	/** The server stopped while this job was being processed; it can be retried. */
	interrupted?: boolean;
	/** Validation of the last render (ADR 0023): 'running' just after it finishes. */
	qa?: QAResult | 'running' | null;
	/** What ingest found in the upload (ADR 0104); null for jobs from before the manifest. */
	manifest?: Manifest | null;
};

export type Manifest = {
	video: {width: number; height: number; display_width: number; display_height: number; orientation: 'portrait' | 'landscape' | 'square'; fps: number; variable_frame_rate: boolean; rotation: number; hdr: boolean} | null;
	audio: {present: boolean; tracks: number} | null;
	warnings: string[] | null;
	stages: Record<string, {status: 'running' | 'done' | 'failed' | 'skipped'; at?: string}> | null;
};

export type Generation = {spent: number; budget: number; available: ('stock' | 'image' | 'video')[]; items?: unknown[]};

export type Recipe = {name: string; style: Style; note: string; created: number};

export type ReviewIssue = {at: number; severity: 'high' | 'low'; problem: string; fixable: boolean};
export type ReviewResult = {summary: string; issues: ReviewIssue[]; plan: EditPlan; changes: string[]};

export class ApiError extends Error {
	constructor(public status: number, message: string) {
		super(message);
	}
}

/** FastAPI errors are `{detail: string | [{msg, loc}]}`; turn either into one readable line. */
export function errorMessage(body: unknown, fallback: string): string {
	const detail = (body as {detail?: unknown} | null)?.detail;
	if (typeof detail === 'string') return detail;
	if (Array.isArray(detail)) {
		return detail.map((d) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`).join('; ') || fallback;
	}
	return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	let res: Response;
	try {
		res = await fetch(`${API_URL}${path}`, {cache: 'no-store', ...init});
	} catch {
		throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is it running?`);
	}
	const body = await res.json().catch(() => null);
	if (!res.ok) throw new ApiError(res.status, errorMessage(body, `${res.status} ${res.statusText}`));
	return body as T;
}

export function fileUrl(id: string, name: string): string {
	return `${API_URL}/jobs/${id}/files/${encodeURIComponent(name)}`;
}

/** `vision`: who describes frames of the footage: '' (the server's default), 'none' (local only), 'ollama' or 'claude' (sends frames).
 * `mode`: the editing mode (ADR 0025); empty for the server's default (talking head). `kit`: a brand kit's id (ADR 0026). */
export function createJob(video: File, style: string, hookStrategy: 'cold_open' | 'trim', recipe = '', pictures = false, vision = '', mode = '', kit = '') {
	const form = new FormData();
	form.set('video', video);
	form.set('style', style);
	form.set('hook_strategy', hookStrategy);
	if (recipe) form.set('recipe', recipe);
	if (pictures) form.set('pictures', 'true');
	if (vision) form.set('vision', vision);
	if (mode) form.set('mode', mode);
	if (kit) form.set('kit', kit);
	return request<{id: string; status: string}>('/jobs', {method: 'POST', body: form});
}

/** Which kinds of picture the engine can fetch: empty when no stock or generation keys are set. */
export const generationSources = () => request<{available: string[]}>('/generation');

export const getJob = (id: string) => request<Job>(`/jobs/${id}`);

/** Who made a saved version (ADR 0021). */
export type VersionKind = 'pipeline' | 'edit' | 'assistant' | 'review' | 'restore' | 'render' | 'import';

/** Save the plan as a new version of the project. */
export function savePlan(id: string, plan: EditPlan, opts: {kind?: VersionKind; note?: string; label?: string} = {}) {
	const query = new URLSearchParams(Object.entries(opts).filter(([, v]) => v) as [string, string][]).toString();
	return request<EditPlan>(`/jobs/${id}/plan${query ? `?${query}` : ''}`, {
		method: 'PUT',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify(plan),
	});
}

export const startRender = (id: string) => request<{id: string; render: string}>(`/jobs/${id}/render`, {method: 'POST'});

export const restorePlan = (id: string) => request<EditPlan>(`/jobs/${id}/plan/restore`, {method: 'POST'});

/** Start cutting the speaker out of the video (green-screen effects); a no-op once it exists. */
export function requestMatte(id: string) {
	return request<{id: string; matte: 'running' | 'done'}>(`/jobs/${id}/matte`, {method: 'POST'});
}

export function uploadAsset(id: string, file: File) {
	const form = new FormData();
	form.set('file', file);
	return request<Asset>(`/jobs/${id}/assets`, {method: 'POST', body: form});
}

export const deleteAsset = (id: string, name: string) =>
	request<{deleted: string}>(`/jobs/${id}/assets/${encodeURIComponent(name)}`, {method: 'DELETE'});

/** `explanation`: what the edit does, in words, worked out from the plans themselves. */
export type AssistResult = {plan: EditPlan; message: string; changes: string[]; explanation: string[]};

export const askAssistant = (id: string, body: {instruction: string; plan: EditPlan; playhead: number; selected?: string | null}) =>
	request<AssistResult>(`/jobs/${id}/assistant`, {
		method: 'POST',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify(body),
	});

/** Rebuild the cuts from the plan's pacing (how much pause to keep). Returns the new plan; nothing is saved. */
export const recutPlan = (id: string, plan: EditPlan) =>
	request<EditPlan>(`/jobs/${id}/recut`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(plan)});

const json = (body: unknown): RequestInit => ({method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});

/** Fetch the stock footage and generated pictures the plan waits for; with graphicId, that one again. Not saved. */
export const generateAssets = (id: string, plan: EditPlan, graphicId?: string, prompt?: string) =>
	request<{plan: EditPlan; generation: Generation}>(`/jobs/${id}/generate`, json({plan, graphic_id: graphicId ?? null, prompt: prompt ?? null}));

export const listRecipes = () => request<{recipes: Recipe[]}>('/recipes');
export const saveRecipe = (name: string, style: Style, note = '') => request<Recipe>('/recipes', json({name, style, note}));
export const deleteRecipe = (name: string) => request<{deleted: string}>(`/recipes/${encodeURIComponent(name)}`, {method: 'DELETE'});

/** A brand kit (ADR 0026): a look plus a logo, music, font and end card, reused on every reel. */
export type Kit = {id: string; name: string; logo: string | null; music: boolean; font: string | null; end_card: string; caption_font: string | null; colors: string[]};
export type NewKit = {
	name: string;
	/** Keep the current look of this job's edit. */
	fromJob?: string;
	logo?: File | null;
	music?: File | null;
	font?: File | null;
	logoCorner?: LogoCorner;
	endCard?: string;
	fontName?: string;
};

export const listKits = () => request<{kits: Kit[]}>('/kits');
export function createKit(k: NewKit) {
	const form = new FormData();
	form.set('name', k.name);
	if (k.fromJob) form.set('from_job', k.fromJob);
	if (k.logo) form.set('logo', k.logo);
	if (k.music) form.set('music', k.music);
	if (k.font) form.set('font', k.font);
	if (k.logoCorner) form.set('logo_corner', k.logoCorner);
	if (k.endCard) form.set('end_card', k.endCard);
	if (k.fontName) form.set('font_name', k.fontName);
	return request<Kit>('/kits', {method: 'POST', body: form});
}
export const deleteKit = (id: string) => request<{deleted: string}>(`/kits/${encodeURIComponent(id)}`, {method: 'DELETE'});
export const kitFileUrl = (id: string, name: string) => `${API_URL}/kits/${encodeURIComponent(id)}/files/${encodeURIComponent(name)}`;
/** Put a kit on the job's edit; the server saves it as a new version. */
export const applyKit = (jobId: string, kit: string) =>
	request<{plan: EditPlan; changes: string[]}>(`/jobs/${jobId}/kit`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({kit})});

/** New jobs from this edit: other hooks and shorter cuts. */
export const makeVariants = (id: string, plan: EditPlan) =>
	request<{variants: {id: string; label: string; duration: number}[]}>(`/jobs/${id}/variants`, json(plan));

/** Claude looks at the latest render and proposes fixes; nothing is saved. */
export const reviewRender = (id: string) => request<ReviewResult>(`/jobs/${id}/review`, {method: 'POST'});

/** Build hypercut-export.zip (Final Cut, Resolve, Premiere) from the saved plan. */
export const startExport = (id: string, overlays = true) => request<{id: string; export: string}>(`/jobs/${id}/export`, json({overlays}));

export type Version = {
	id: number;
	parent: number | null;
	kind: VersionKind;
	created: number;
	label: string | null;
	note: string | null;
	changes: string[];
	duration: number;
};
export type HistoryListing = {head: number | null; can_undo: boolean; can_redo: boolean; versions: Version[]};

export const getHistory = (id: string) => request<HistoryListing>(`/jobs/${id}/history`);
export const getVersion = (id: string, vid: number) => request<{plan: EditPlan; changes_from_current: string[]}>(`/jobs/${id}/history/${vid}`);
export const restoreVersion = (id: string, vid: number) =>
	request<{plan: EditPlan; version: Version}>(`/jobs/${id}/history/${vid}/restore`, {method: 'POST'});
export const nameVersion = (id: string, vid: number, label: string | null) =>
	request<Version>(`/jobs/${id}/history/${vid}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({label})});

export type Draft = {saved: number; base: number | null; plan: EditPlan; changes: string[]};
/** Autosave unsaved edits; offered back when the editor reopens. */
export const saveDraft = (id: string, plan: EditPlan) =>
	request<{saved: number; base: number | null}>(`/jobs/${id}/draft`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(plan)});
export const getDraft = (id: string) => request<{draft: Draft | null}>(`/jobs/${id}/draft`);
export const discardDraft = (id: string) => request<{deleted: boolean}>(`/jobs/${id}/draft`, {method: 'DELETE'});

export type ExplainItem = {at: number; kind: 'hook' | 'silence' | 'filler' | 'trim' | 'ending' | 'graphic' | 'zoom' | 'spelling' | 'footage' | 'speaker'; text: string; id?: string};
export type Explanation = {summary: string; items: ExplainItem[]};
/** Why the first cut (and the current edit) look the way they do. */
export const explainCut = (id: string) => request<{first_cut: Explanation; current: Explanation}>(`/jobs/${id}/explain`);

/** Run the pipeline again on a job that failed or was interrupted. */
export const retryJob = (id: string) => request<{id: string; status: string}>(`/jobs/${id}/retry`, {method: 'POST'});

/** An automatic check of the plan (ADR 0023): `fail` is a defect a viewer notices, `warn` is worth a look. */
export type Issue = {code: string; severity: 'fail' | 'warn'; message: string; at: number | null; key: string | null};
export type CheckReport = {ok: boolean; issues: Issue[]};
export type QACheck = {name: string; status: 'pass' | 'warn' | 'fail'; detail: string};
export type QAResult = {ok: boolean | null; checks?: QACheck[]; error?: string};

export const checkPlan = (id: string, plan: EditPlan) => request<CheckReport>(`/jobs/${id}/checks`, json(plan));
