// Bundlers (Remotion's webpack, Next with the rule in web/next.config.mjs, Vite in tests) turn a font
// import into its URL.
declare module '*.woff2' {
	const url: string;
	export default url;
}
