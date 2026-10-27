'use client';

import {useState} from 'react';
import type {EditPlan} from '@render/plan';
import {count, fileUrl} from '@/lib/api';
import {postCaption} from '@/lib/share';

/** Share the rendered reel (ADR 0030): the system share sheet where the browser can share files (phones, most
 * desktops), else download it and copy a caption. Nothing is uploaded by HyperCut. */
export default function Share({jobId, plan, name}: {jobId: string; plan: EditPlan; name: string}) {
	const [note, setNote] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);

	async function share() {
		setBusy(true);
		setNote(null);
		const caption = postCaption(plan);
		try {
			const blob = await (await fetch(fileUrl(jobId, 'output.mp4'))).blob();
			const file = new File([blob], `${name}.mp4`, {type: 'video/mp4'});
			if (navigator.canShare?.({files: [file]})) {
				await navigator.share({files: [file], text: caption});
				count('share', {how: 'share_sheet'});
				return;
			}
			const link = document.createElement('a');
			link.href = URL.createObjectURL(blob);
			link.download = file.name;
			link.click();
			URL.revokeObjectURL(link.href);
			await navigator.clipboard?.writeText(caption).catch(() => undefined);
			setNote('Downloaded. A caption is copied: paste it when you post.');
			count('share', {how: 'download'});
		} catch (e) {
			if ((e as Error).name !== 'AbortError') setNote(`Could not share: ${(e as Error).message}`);
		} finally {
			setBusy(false);
		}
	}

	return (
		<>
			<button onClick={share} disabled={busy} title="Post it: the share sheet, or download with a caption ready to paste">
				{busy ? 'Getting it ready…' : 'Share'}
			</button>
			{note && <span className="hint">{note}</span>}
		</>
	);
}
