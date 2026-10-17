import React from 'react';
import {Composition} from 'remotion';
import samplePlan from '../../schema/examples/sample_plan.json';
import {calculateMetadata, HyperCut} from './HyperCut';
import {normalizePlan, type CompositionProps} from './plan';

export const COMPOSITION_ID = 'HyperCut';

const defaultProps: CompositionProps = {plan: normalizePlan(samplePlan), videoSrc: 'sample.mp4'};

export const Root: React.FC = () => (
	<Composition
		id={COMPOSITION_ID}
		component={HyperCut}
		durationInFrames={30}
		fps={30}
		width={1080}
		height={1920}
		defaultProps={defaultProps}
		calculateMetadata={calculateMetadata}
	/>
);
