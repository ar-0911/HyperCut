import type {EditPlan} from '@render/plan';

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
