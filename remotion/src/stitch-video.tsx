import React from 'react';
import {AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame} from 'remotion';

export type Caption = {
  start: number;
  end: number;
  text: string;
};

export type StitchVideoProps = {
  src: string;
  captions: Caption[];
  fps: number;
  width: number;
  height: number;
};

const subtitleWrap: React.CSSProperties = {
  position: 'absolute',
  left: 0,
  right: 0,
  bottom: 48,
  display: 'flex',
  justifyContent: 'center',
  pointerEvents: 'none',
  paddingLeft: 24,
  paddingRight: 24,
};

const subtitleBox: React.CSSProperties = {
  color: '#ffffff',
  fontSize: 44,
  fontWeight: 700,
  lineHeight: 1.35,
  textAlign: 'center',
  textShadow: '0 2px 10px rgba(0, 0, 0, 0.8)',
  whiteSpace: 'pre-wrap',
  maxWidth: '90%',
};

export const StitchVideo: React.FC<StitchVideoProps> = ({src, captions, fps}) => {
  const frame = useCurrentFrame();
  const t = frame / fps;
  const active = captions.find((c) => t >= c.start && t < c.end);
  const videoSrc = src ? staticFile(src) : '';

  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {videoSrc ? (
        <OffthreadVideo src={videoSrc} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      ) : null}
      <div style={subtitleWrap}>
        <div style={subtitleBox}>{active ? active.text : ''}</div>
      </div>
    </AbsoluteFill>
  );
};
