/** Editing modes (ADR 0025), the same list as `hypercut/modes.py` and GET /modes. */
export type Mode = 'talking_head' | 'podcast' | 'product_demo' | 'vlog';

export const MODES: {name: Mode; label: string; hint: string}[] = [
	{name: 'talking_head', label: 'Talking head', hint: 'One person to camera: strong hook, tight pauses, graphics where they help.'},
	{name: 'podcast', label: 'Podcast clip', hint: 'The best standalone answer, dead air removed, frequent punch-ins, the speaker in focus.'},
	{name: 'product_demo', label: 'Product demo', hint: 'Clear steps, the screen or product kept visible, feature labels, clean type.'},
	{name: 'vlog', label: 'Vlog / story', hint: 'A story with a beginning and an end, room for emotional beats, more visual variety.'},
];
