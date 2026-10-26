import {afterEach, describe, expect, it, vi} from 'vitest';
import {ApiError, API_URL, createJob, errorMessage, fileUrl, getJob, savePlan} from './api';

afterEach(() => vi.unstubAllGlobals());

const reply = (status: number, body: unknown) =>
	vi.fn().mockResolvedValue(new Response(JSON.stringify(body), {status}));

describe('api client', () => {
	it('defaults the API url and builds file urls', () => {
		expect(API_URL).toBe('http://localhost:8000');
		expect(fileUrl('abc', 'output.mp4')).toBe('http://localhost:8000/jobs/abc/files/output.mp4');
	});

	it('uploads multipart with style and strategy', async () => {
		const fetchMock = reply(202, {id: 'abc', status: 'queued'});
		vi.stubGlobal('fetch', fetchMock);
		const out = await createJob(new File(['x'], 'a.mp4'), 'bold', 'trim');
		expect(out.id).toBe('abc');
		const [url, init] = fetchMock.mock.calls[0];
		expect(url).toBe('http://localhost:8000/jobs');
		expect(init.method).toBe('POST');
		const form = init.body as FormData;
		expect(form.get('style')).toBe('bold');
		expect(form.get('hook_strategy')).toBe('trim');
		expect((form.get('video') as File).name).toBe('a.mp4');
	});

	it('puts the plan as JSON', async () => {
		const fetchMock = reply(200, {});
		vi.stubGlobal('fetch', fetchMock);
		await savePlan('abc', {version: 1} as never);
		const [url, init] = fetchMock.mock.calls[0];
		expect(url).toBe('http://localhost:8000/jobs/abc/plan');
		expect(init.method).toBe('PUT');
		expect(JSON.parse(init.body)).toEqual({version: 1});
	});

	it('says who made a saved version', async () => {
		const fetchMock = reply(200, {});
		vi.stubGlobal('fetch', fetchMock);
		await savePlan('abc', {version: 1} as never, {kind: 'assistant', note: 'cut the pause'});
		expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8000/jobs/abc/plan?kind=assistant&note=cut+the+pause');
	});

	it('surfaces string and validation errors', async () => {
		vi.stubGlobal('fetch', reply(409, {detail: 'job is running'}));
		await expect(getJob('abc')).rejects.toMatchObject({status: 409, message: 'job is running'});
		expect(errorMessage({detail: [{loc: ['body', 'hook', 'chosen'], msg: 'bad index'}]}, 'x')).toBe('hook.chosen: bad index');
		expect(errorMessage(null, 'fallback')).toBe('fallback');
	});

	it('reports an unreachable API', async () => {
		vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')));
		const err = await getJob('abc').catch((e) => e);
		expect(err).toBeInstanceOf(ApiError);
		expect(err.message).toContain('Cannot reach the API');
	});
});
