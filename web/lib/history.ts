import {useCallback, useState} from 'react';

const LIMIT = 100;

type State<T> = {past: T[]; present: T; future: T[]};

/** Undo/redo over immutable values. `set` records a step; `replace` changes the present without one. */
export function useHistory<T>(initial: T) {
	const [s, setS] = useState<State<T>>({past: [], present: initial, future: []});
	const set = useCallback((next: T) => setS((h) => (next === h.present ? h : {past: [...h.past, h.present].slice(-LIMIT), present: next, future: []})), []);
	const replace = useCallback((next: T) => setS((h) => ({...h, present: next})), []);
	const undo = useCallback(() => setS((h) => (h.past.length ? {past: h.past.slice(0, -1), present: h.past[h.past.length - 1], future: [h.present, ...h.future]} : h)), []);
	const redo = useCallback(() => setS((h) => (h.future.length ? {past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1)} : h)), []);
	return {value: s.present, set, replace, undo, redo, canUndo: s.past.length > 0, canRedo: s.future.length > 0};
}
