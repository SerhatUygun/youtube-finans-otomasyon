import React from 'react';
import {registerRoot, Composition} from 'remotion';
import {PersonaC_Speed, defaultPersonaCSpeedProps, PersonaCSpeedProps} from './PersonaC_Speed';

const Root: React.FC = () => (
  <Composition
    id="PersonaC-Speed"
    component={PersonaC_Speed}
    fps={30}
    width={1920}
    height={1080}
    durationInFrames={180}
    defaultProps={defaultPersonaCSpeedProps}
    calculateMetadata={async ({props}: {props: PersonaCSpeedProps}) => {
      const fps = props.fps ?? 30;
      const seconds = props.seconds ?? 6;
      return {fps, durationInFrames: Math.max(Math.round(seconds * fps), 1)};
    }}
  />
);

registerRoot(Root);
