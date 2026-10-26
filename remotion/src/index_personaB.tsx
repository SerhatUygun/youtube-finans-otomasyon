import React from 'react';
import {registerRoot, Composition} from 'remotion';
import {PersonaBCinematic, defaultPersonaBCinematicProps, PersonaBCinematicProps} from './PersonaB_Cinematic';

// Izole entry point -- Root.tsx/index.ts'e DOKUNMADAN standalone render/onizleme icin.
// Kullanim: npx remotion render src/index_personaB.ts PersonaB_Cinematic <out> --props=<file>
const PersonaBRoot: React.FC = () => (
  <Composition
    id="PersonaB-Cinematic"
    component={PersonaBCinematic}
    fps={30}
    width={1920}
    height={1080}
    durationInFrames={150}
    defaultProps={defaultPersonaBCinematicProps}
    calculateMetadata={async ({props}: {props: PersonaBCinematicProps}) => {
      const fps = props.fps ?? 30;
      const seconds = props.seconds ?? 5;
      return {fps, durationInFrames: Math.max(Math.round(seconds * fps), 1)};
    }}
  />
);

registerRoot(PersonaBRoot);
