// Built-in sticker icons for the effects around the speaker (ADR 0610), used when an item has no
// Claude-drawn graphic (added by hand in the editor, or drawing failed). Flat, thick-outlined, on a
// 100x100 canvas; `A` is replaced by the style's accent colour.

const O = 'stroke="#111" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"';

const ICONS: Record<string, string> = {
	rocket: `<path d="M50 8c14 10 20 26 18 46H32C30 34 36 18 50 8z" fill="#fff" ${O}/><circle cx="50" cy="34" r="8" fill="A" ${O}/><path d="M32 46l-12 16 14 2M68 46l12 16-14 2" fill="A" ${O}/><path d="M40 64c0 10 4 18 10 26 6-8 10-16 10-26z" fill="#FF7A1A" ${O}/>`,
	chart: `<rect x="12" y="54" width="18" height="34" rx="3" fill="#fff" ${O}/><rect x="41" y="38" width="18" height="50" rx="3" fill="A" ${O}/><rect x="70" y="18" width="18" height="70" rx="3" fill="#fff" ${O}/><path d="M14 40L44 22l14 8 28-20" fill="none" ${O}/><path d="M74 8h14v14" fill="none" ${O}/>`,
	coins: `<ellipse cx="50" cy="74" rx="32" ry="12" fill="A" ${O}/><path d="M18 60v14M82 60v14" ${O}/><ellipse cx="50" cy="60" rx="32" ry="12" fill="A" ${O}/><path d="M18 46v14M82 46v14" ${O}/><ellipse cx="50" cy="46" rx="32" ry="12" fill="#fff" ${O}/><path d="M50 40v12M44 43h12" ${O}/>`,
	bulb: `<path d="M50 10a26 26 0 0 0-16 46c4 4 6 8 6 14h20c0-6 2-10 6-14a26 26 0 0 0-16-46z" fill="A" ${O}/><rect x="39" y="70" width="22" height="14" rx="4" fill="#fff" ${O}/><path d="M44 92h12M42 30a12 12 0 0 1 10-8" fill="none" ${O}/>`,
	clock: `<circle cx="50" cy="52" r="36" fill="#fff" ${O}/><circle cx="50" cy="52" r="28" fill="A" ${O}/><path d="M50 32v20l14 8" fill="none" ${O}/><path d="M38 10h24" ${O}/>`,
	target: `<circle cx="50" cy="50" r="38" fill="#fff" ${O}/><circle cx="50" cy="50" r="26" fill="A" ${O}/><circle cx="50" cy="50" r="12" fill="#fff" ${O}/><path d="M50 50L84 16M74 12l10 4 4 10" fill="none" ${O}/>`,
	heart: `<path d="M50 86L16 52a20 20 0 0 1 34-28 20 20 0 0 1 34 28z" fill="A" ${O}/><path d="M30 36a9 9 0 0 1 9-7" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"/>`,
	star: `<path d="M50 8l12 26 28 3-21 19 6 28-25-14-25 14 6-28-21-19 28-3z" fill="A" ${O}/>`,
	bolt: `<path d="M58 6L20 56h24l-6 38 40-52H54z" fill="A" ${O}/>`,
	globe: `<circle cx="50" cy="50" r="38" fill="A" ${O}/><ellipse cx="50" cy="50" rx="16" ry="38" fill="none" ${O}/><path d="M12 50h76M18 30h64M18 70h64" fill="none" ${O}/>`,
	check: `<circle cx="50" cy="50" r="38" fill="A" ${O}/><path d="M30 52l14 14 26-30" fill="none" stroke="#111" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>`,
	trophy: `<path d="M28 12h44v24a22 22 0 0 1-44 0z" fill="A" ${O}/><path d="M28 20H14c0 14 6 20 16 22M72 20h14c0 14-6 20-16 22" fill="none" ${O}/><path d="M44 58h12v14H44z" fill="#fff" ${O}/><rect x="30" y="72" width="40" height="14" rx="3" fill="A" ${O}/>`,
	phone: `<rect x="28" y="6" width="44" height="88" rx="9" fill="#fff" ${O}/><rect x="34" y="16" width="32" height="58" rx="3" fill="A" ${O}/><circle cx="50" cy="84" r="3" fill="#111"/>`,
	lock: `<path d="M32 44V32a18 18 0 0 1 36 0v12" fill="none" ${O}/><rect x="20" y="44" width="60" height="46" rx="8" fill="A" ${O}/><path d="M50 60v14" ${O}/>`,
	people: `<circle cx="34" cy="34" r="12" fill="#fff" ${O}/><circle cx="66" cy="34" r="12" fill="A" ${O}/><path d="M12 82c0-16 10-26 22-26s22 10 22 26z" fill="#fff" ${O}/><path d="M44 82c0-16 10-26 22-26s22 10 22 26z" fill="A" ${O}/>`,
	cloud: `<path d="M28 76a18 18 0 0 1 0-36 24 24 0 0 1 46-4 20 20 0 0 1-2 40z" fill="#fff" ${O}/><path d="M36 58l10 8 18-18" fill="none" ${O}/>`,
	mail: `<rect x="10" y="22" width="80" height="56" rx="8" fill="#fff" ${O}/><path d="M12 26l38 30 38-30" fill="A" ${O}/>`,
	fire: `<path d="M50 6c4 18 26 26 26 52a26 26 0 0 1-52 0c0-14 8-20 12-28 2 10 8 12 8 12 0-14 2-26 6-36z" fill="#FF7A1A" ${O}/><path d="M50 58c4 8 12 10 12 20a12 12 0 0 1-24 0c0-8 8-12 12-20z" fill="A" ${O}/>`,
	gear: `<path d="M44 8h12l2 12 10 4 10-8 8 8-8 10 4 10 12 2v12l-12 2-4 10 8 10-8 8-10-8-10 4-2 12H44l-2-12-10-4-10 8-8-8 8-10-4-10-12-2V44l12-2 4-10-8-10 8-8 10 8 10-4z" fill="A" ${O}/><circle cx="50" cy="50" r="13" fill="#fff" ${O}/>`,
	idea_chat: `<path d="M12 18h76v50H44L26 86V68H12z" fill="#fff" ${O}/><path d="M30 38h40M30 52h26" fill="none" ${O}/>`,
};

/** Words that pick an icon; the first match wins. */
const WORDS: [RegExp, string][] = [
	[/\b(?:rocket|launch|ship|start)/, 'rocket'],
	[/\b(?:chart|graph|growth|grow|rise|rising|sales|revenue|stock|percent)|%/, 'chart'],
	[/\b(?:coin|money|cash|dollar|pay|price|cost|rich|profit|income|save|saving)|\$|₹|€|£/, 'coins'],
	[/\b(?:idea|bulb|think|insight|smart|brain|learn)/, 'bulb'],
	[/\b(?:clock|time|hour|minute|fast|quick|deadline|day|week|year)/, 'clock'],
	[/\b(?:target|goal|aim|focus|plan)/, 'target'],
	[/\b(?:heart|love|like|health|care|wellness)/, 'heart'],
	[/\b(?:trophy|win|award|best|champion|first)/, 'trophy'],
	[/\b(?:star|review|rating|quality|top)/, 'star'],
	[/\b(?:bolt|lightning|energy|power|electric|boost)/, 'bolt'],
	[/\b(?:globe|world|global|earth|travel|international)/, 'globe'],
	[/\b(?:check|done|yes|right|success|correct)/, 'check'],
	[/\b(?:phone|mobile|app|call)/, 'phone'],
	[/\b(?:lock|secure|security|safe|privacy|password)/, 'lock'],
	[/\b(?:people|team|user|customer|community|friend|family)/, 'people'],
	[/\b(?:cloud|online|internet|server)/, 'cloud'],
	[/\b(?:mail|email|message|inbox|newsletter)/, 'mail'],
	[/\b(?:fire|hot|trend|viral|burn)/, 'fire'],
	[/\b(?:gear|tool|setting|system|work|build|engine|automat)/, 'gear'],
	[/\b(?:chat|talk|comment|say|speak|question)/, 'idea_chat'],
];

const FALLBACK = ['star', 'bolt', 'target', 'bulb', 'check'];

/** SVG inner markup (viewBox 0 0 100 100) of the built-in icon for an item; a generic one when no word matches. */
export function builtinIcon(item: string, accent: string, index = 0): string {
	const text = item.toLowerCase();
	const hit = WORDS.find(([re]) => re.test(text));
	const name = hit ? hit[1] : FALLBACK[index % FALLBACK.length];
	return ICONS[name].replace(/"A"/g, `"${accent}"`);
}
