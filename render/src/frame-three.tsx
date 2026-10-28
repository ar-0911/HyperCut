// A three.js canvas that draws exactly once per frame of the reel (ADR 0032). react-three-fiber never runs its own
// loop here: each time the frame changes, the scene is committed and rendered, and the frame waits for that.

import {Canvas, useThree} from '@react-three/fiber';
import React, {useLayoutEffect, useRef} from 'react';
import {useCurrentFrame, useRuntime, waitFor} from './frame';

type Props = {width: number; height: number; camera?: Record<string, unknown>; children?: React.ReactNode};

/** Renders the scene after each commit of the canvas tree, then lets the waiting frame go. */
const DrawEachFrame: React.FC<{tick: number; done: React.MutableRefObject<(() => void) | null>}> = ({tick, done}) => {
	const {gl, scene, camera} = useThree();
	useLayoutEffect(() => {
		gl.render(scene, camera);
		done.current?.();
		done.current = null;
	}, [tick, gl, scene, camera, done]);
	return null;
};

export const ThreeCanvas: React.FC<Props> = ({width, height, camera, children}) => {
	const {mode} = useRuntime();
	const frame = useCurrentFrame();
	const done = useRef<(() => void) | null>(null);
	const asked = useRef<number | null>(null);
	if (mode === 'collect') return null;
	// Each new frame waits until the canvas tree has drawn it (or 3 s, so a broken scene can't hang a render).
	// Set up while rendering, before the canvas tree can commit.
	if (asked.current !== frame) {
		asked.current = frame;
		done.current?.();
		waitFor(
			new Promise<void>((resolve) => {
				const timer = setTimeout(resolve, 3000);
				done.current = () => {
					clearTimeout(timer);
					resolve();
				};
			}),
		);
	}
	return (
		<Canvas
			frameloop="never"
			dpr={1}
			gl={{preserveDrawingBuffer: true, antialias: true}}
			camera={camera}
			style={{position: 'absolute', left: 0, top: 0, width, height}}
		>
			{children}
			<DrawEachFrame tick={frame} done={done} />
		</Canvas>
	);
};
