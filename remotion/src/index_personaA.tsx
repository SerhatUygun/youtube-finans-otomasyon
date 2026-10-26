import React from 'react';
import {registerRoot, Composition} from 'remotion';
import {PersonaA_Broadcast, defaultPersonaABroadcastProps, PersonaABroadcastProps} from './PersonaA_Broadcast';

function metadataFromSeconds<T extends {seconds?: number; fps?: number}>({props}: {props: T}) {
  const fps = props.fps ?? 30;
  const seconds = props.seconds ?? 5;
  return {fps, durationInFrames: Math.max(Math.round(seconds * fps), 1)};
}

const PersonaARoot: React.FC = () => (
  <Composition
    id="PersonaA-Broadcast"
    component={PersonaA_Broadcast}
    fps={30}
    width={1920}
    height={1080}
    durationInFrames={120}
    defaultProps={defaultPersonaABroadcastProps}
    calculateMetadata={async ({props}: {props: PersonaABroadcastProps}) => metadataFromSeconds({props})}
  />
);

registerRoot(PersonaARoot);
