import type {EditPlan} from '@render/plan';
import type {Asset} from '@/lib/timeline';

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

export const STAGES = ['ingest', 'transcribe', 'style', 'analyze'] as const;
export type Stage = (typeof STAGES)[number];

export type Job = {
	id: string;
	status: 'queued' | 'running' | 'done' | 'error';
	stage: Stage | 'done' | null;
	error: string | null;
	render: 'running' | 'done' | 'error' | null;
	render_error: string | null;
	style: string;
	hook_strategy: 'cold_open' | 'trim';
	filename?: string;
	plan: EditPlan | null;
	/** The plan as the pipeline made it (before any edit). */
	base_plan: EditPlan | null;
	assets: Asset[];
	files: string[];
};

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

export function createJob(video: File, style: string, hookStrategy: 'cold_open' | 'trim') {
	const form = new FormData();
	form.set('video', video);
	form.set('style', style);
	form.set('hook_strategy', hookStrategy);
	return request<{id: string; status: string}>('/jobs', {method: 'POST', body: form});
}

export const getJob = (id: string) => request<Job>(`/jobs/${id}`);

export const savePlan = (id: string, plan: EditPlan) =>
	request<EditPlan>(`/jobs/${id}/plan`, {
		method: 'PUT',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify(plan),
	});

export const startRender = (id: string) => request<{id: string; render: string}>(`/jobs/${id}/render`, {method: 'POST'});

export const restorePlan = (id: string) => request<EditPlan>(`/jobs/${id}/plan/restore`, {method: 'POST'});

export function uploadAsset(id: string, file: File) {
	const form = new FormData();
	form.set('file', file);
	return request<Asset>(`/jobs/${id}/assets`, {method: 'POST', body: form});
}

export const deleteAsset = (id: string, name: string) =>
	request<{deleted: string}>(`/jobs/${id}/assets/${encodeURIComponent(name)}`, {method: 'DELETE'});

export type AssistResult = {plan: EditPlan; message: string; changes: string[]};

export const askAssistant = (id: string, body: {instruction: string; plan: EditPlan; playhead: number; selected?: string | null}) =>
	request<AssistResult>(`/jobs/${id}/assistant`, {
		method: 'POST',
		headers: {'Content-Type': 'application/json'},
		body: JSON.stringify(body),
	});

/** Rebuild the cuts from the plan's pacing (how much pause to keep). Returns the new plan; nothing is saved. */
export const recutPlan = (id: string, plan: EditPlan) =>
	request<EditPlan>(`/jobs/${id}/recut`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(plan)});
