import type {GraphicsStyle} from './plan';

export type Theme = {
	fontFamily: string;
	fontWeight: number;
	text: string;
	/** Panel behind text. */
	panel: string;
	panelText: string;
	radius: number;
	accent: string;
	border: string;
	shadow: string;
	uppercase: boolean;
};

const SANS = '"Montserrat", "Inter", "Helvetica Neue", Arial, sans-serif';
const SERIF = '"Playfair Display", Georgia, "Times New Roman", serif';

export function themeTokens(g: GraphicsStyle): Theme {
	const accent = g.accent_color;
	switch (g.theme) {
		case 'clean':
			return {fontFamily: SANS, fontWeight: 600, text: '#FFFFFF', panel: 'rgba(255,255,255,0.94)', panelText: '#111111', radius: 28, accent, border: 'none', shadow: '0 12px 40px rgba(0,0,0,0.25)', uppercase: false};
		case 'playful':
			return {fontFamily: SANS, fontWeight: 900, text: '#FFFFFF', panel: accent, panelText: '#111111', radius: 56, accent, border: '6px solid #111111', shadow: '10px 10px 0 #111111', uppercase: false};
		case 'cinematic':
			return {fontFamily: SERIF, fontWeight: 500, text: '#F4EBDD', panel: 'rgba(8,8,8,0.72)', panelText: '#F4EBDD', radius: 6, accent, border: `2px solid ${accent}`, shadow: '0 18px 60px rgba(0,0,0,0.6)', uppercase: false};
		case 'bold':
		default:
			return {fontFamily: SANS, fontWeight: 900, text: '#FFFFFF', panel: '#0B0B0B', panelText: '#FFFFFF', radius: 20, accent, border: `6px solid ${accent}`, shadow: '0 14px 40px rgba(0,0,0,0.5)', uppercase: true};
	}
}
