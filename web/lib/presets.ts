// Mirrors hypercut/style/presets.py. A chip fills the style prompt; Claude maps the prompt to the closest preset.
export const PRESETS = [
	{name: 'Bold creator', prompt: 'Bold creator: loud, high-energy, big uppercase yellow captions, regular zooms'},
	{name: 'Clean corporate', prompt: 'Clean corporate: professional and calm, smaller sentence-case captions, blue accent, few graphics'},
	{name: 'Playful', prompt: 'Playful: fun and bouncy, pink accent, lots of graphics and emoji, frequent zooms'},
	{name: 'Cinematic', prompt: 'Cinematic: moody and elegant, serif captions, gold accent, slow pacing, subtle camera'},
	{name: 'Minimal', prompt: 'Minimal: nearly invisible small plain captions, no zooms, no frills'},
	{name: 'Podcast', prompt: 'Podcast: conversational, mid-screen green karaoke captions, moderate graphics and zooms'},
] as const;
