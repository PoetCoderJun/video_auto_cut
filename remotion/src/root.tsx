import React from 'react';
import {Composition} from 'remotion';
import {StitchVideo, type StitchVideoProps} from './stitch-video';

const defaultProps: StitchVideoProps = {
  src: '',
  captions: [],
  topics: [],
  fps: 30,
  width: 1920,
  height: 1080,
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="StitchVideo"
        component={StitchVideo}
        durationInFrames={1}
        fps={defaultProps.fps}
        width={defaultProps.width}
        height={defaultProps.height}
        defaultProps={defaultProps}
      />
    </>
  );
};
