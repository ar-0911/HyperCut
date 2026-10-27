// Which stretches of a video to extract (ADR 0032): the frames the dry run listed, joined into runs so ffmpeg
// decodes each stretch once. Small gaps are filled, since decoding through them is cheaper than seeking again.

export type Run = {first: number; last: number};

/** Sorted runs covering `frames` (frame indices); gaps of up to `gap` frames are filled. */
export function frameRuns(frames: Iterable<number>, gap = 12): Run[] {
	const sorted = [...new Set(frames)].filter((f) => Number.isFinite(f) && f >= 0).sort((a, b) => a - b);
	const runs: Run[] = [];
	for (const f of sorted) {
		const last = runs[runs.length - 1];
		if (last && f - last.last <= gap + 1) last.last = f;
		else runs.push({first: f, last: f});
	}
	return runs;
}

/** ffmpeg arguments writing frames first..last of `input` (at `fps`) as `${dir}/${index}.${ext}`. */
export function extractArgs(input: string, run: Run, fps: number, dir: string, ext: 'jpg' | 'png', alpha: boolean): string[] {
	return [
		'-v', 'error', '-y',
		// VP9 with alpha (the speaker cut-out) keeps its alpha only through libvpx.
		...(alpha ? ['-c:v', 'libvpx-vp9'] : []),
		'-ss', (run.first / fps).toFixed(6),
		'-i', input,
		'-frames:v', String(run.last - run.first + 1),
		'-vf', `fps=${fps}`,
		...(ext === 'jpg' ? ['-q:v', '2'] : ['-pix_fmt', 'rgba']),
		'-start_number', String(run.first),
		`${dir}/%d.${ext}`,
	];
}
