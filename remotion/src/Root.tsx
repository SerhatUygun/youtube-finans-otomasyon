import React from 'react';
import {Composition} from 'remotion';
import {MarketChart, defaultMarketChartProps, MarketChartProps} from './MarketChart';
import {StatCallout, defaultStatCalloutProps, StatCalloutProps} from './StatCallout';
import {CompareBars, defaultCompareBarsProps, CompareBarsProps} from './CompareBars';
import {TitleCard, defaultTitleCardProps, TitleCardProps} from './TitleCard';
import {KeyQuote, defaultKeyQuoteProps, KeyQuoteProps} from './KeyQuote';
import {Captions, defaultCaptionsProps, CaptionsProps} from './Captions';
import {AccentOverlay, defaultAccentOverlayProps, AccentOverlayProps} from './AccentOverlay';
import {NewspaperHighlight, defaultNewspaperHighlightProps, NewspaperHighlightProps} from './NewspaperHighlight';
import {ChapterProgress, defaultChapterProgressProps, ChapterProgressProps} from './ChapterProgress';

// Tum sablonlar props.seconds/props.fps'ten durationInFrames turetir -- boylece Python
// tarafi (pipeline/stages/s05b_motion_graphics.py) her segment icin --props ile tam
// segment suresine esit bir klip alir (ffmpeg'in loop/kirpmasina gerek kalmaz).
function metadataFromSeconds<T extends {seconds?: number; fps?: number}>({props}: {props: T}) {
  const fps = props.fps ?? 30;
  const seconds = props.seconds ?? 5;
  return {fps, durationInFrames: Math.max(Math.round(seconds * fps), 1)};
}

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="MarketChart"
        component={MarketChart}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={150}
        defaultProps={defaultMarketChartProps}
        calculateMetadata={async ({props}: {props: MarketChartProps}) => metadataFromSeconds({props})}
      />
      <Composition
        id="StatCallout"
        component={StatCallout}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={120}
        defaultProps={defaultStatCalloutProps}
        calculateMetadata={async ({props}: {props: StatCalloutProps}) => metadataFromSeconds({props})}
      />
      <Composition
        id="CompareBars"
        component={CompareBars}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={150}
        defaultProps={defaultCompareBarsProps}
        calculateMetadata={async ({props}: {props: CompareBarsProps}) => metadataFromSeconds({props})}
      />
      <Composition
        id="TitleCard"
        component={TitleCard}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={120}
        defaultProps={defaultTitleCardProps}
        calculateMetadata={async ({props}: {props: TitleCardProps}) => metadataFromSeconds({props})}
      />
      <Composition
        id="KeyQuote"
        component={KeyQuote}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={120}
        defaultProps={defaultKeyQuoteProps}
        calculateMetadata={async ({props}: {props: KeyQuoteProps}) => metadataFromSeconds({props})}
      />
      <Composition
        id="AccentOverlay"
        component={AccentOverlay}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={240}
        defaultProps={defaultAccentOverlayProps}
        calculateMetadata={async ({props}: {props: AccentOverlayProps}) => metadataFromSeconds({props})}
      />
      <Composition
        id="Captions"
        component={Captions}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={90}
        defaultProps={defaultCaptionsProps}
        calculateMetadata={async ({props}: {props: CaptionsProps}) => metadataFromSeconds({
          props: {seconds: props.totalSeconds, fps: props.fps},
        })}
      />
      <Composition
        id="NewspaperHighlight"
        component={NewspaperHighlight}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={150}
        defaultProps={defaultNewspaperHighlightProps}
        calculateMetadata={async ({props}: {props: NewspaperHighlightProps}) => metadataFromSeconds({props})}
      />
      <Composition
        id="ChapterProgress"
        component={ChapterProgress}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={90}
        defaultProps={defaultChapterProgressProps}
        calculateMetadata={async ({props}: {props: ChapterProgressProps}) => metadataFromSeconds({
          props: {seconds: props.totalSeconds, fps: props.fps},
        })}
      />
    </>
  );
};
