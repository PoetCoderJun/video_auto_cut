import fs from 'fs';
import path from 'path';
import {fileURLToPath} from 'url';
import {bundle} from '@remotion/bundler';
import {getCompositions, renderMedia} from '@remotion/renderer';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const parseArgs = (argv) => {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (!key.startsWith('--')) {
      continue;
    }
    const value = argv[i + 1];
    args[key.slice(2)] = value;
    i += 1;
  }
  return args;
};

const args = parseArgs(process.argv.slice(2));
const propsPath = args.props;
const output = args.output;
const codec = args.codec || 'h264';
const crf = args.crf ? Number(args.crf) : undefined;
const hardwareAcceleration = args['hardware-acceleration'] || 'if-possible';

const hardwareAccelerationModes = new Set(['disable', 'if-possible', 'required']);
if (!hardwareAccelerationModes.has(hardwareAcceleration)) {
  throw new Error(
    `Invalid --hardware-acceleration value: ${hardwareAcceleration}. ` +
      'Use disable, if-possible, or required.'
  );
}

if (!propsPath || !output) {
  throw new Error('Usage: node render.mjs --props <props.json> --output <output.mp4>');
}

const propsRaw = fs.readFileSync(propsPath, 'utf-8');
const props = JSON.parse(propsRaw);
if (!props.src || typeof props.src !== 'string') {
  throw new Error('`src` is required in Remotion input props.');
}

const fps = Number(props.fps || 30);
const width = Number(props.width || 1920);
const height = Number(props.height || 1080);
const durationInFrames = Math.max(1, Number(props.durationInFrames || 1));
const clamp01 = (v) => Math.max(0, Math.min(1, v));
let lastProgressPct = -1;

const emitProgress = (ratio) => {
  const numeric = Number(ratio) || 0;
  const normalized = numeric > 1 ? numeric / 100 : numeric;
  const pct = Math.floor(clamp01(normalized) * 100);
  if (!Number.isFinite(pct) || pct <= lastProgressPct) {
    return;
  }
  lastProgressPct = pct;
  // Stable marker consumed by Python to update backend progress.
  console.log(`RENDER_PROGRESS_PCT=${pct}`);
};

const getVideoEncoder = (ffmpegArgs) => {
  const codecIndex = ffmpegArgs.findIndex((item) => item === '-c:v');
  if (codecIndex === -1 || codecIndex + 1 >= ffmpegArgs.length) {
    return null;
  }
  return ffmpegArgs[codecIndex + 1];
};

const enforceBt709 = ({type, args: ffmpegArgs}) => {
  if (type !== 'stitcher') {
    return ffmpegArgs;
  }

  const args = [...ffmpegArgs];
  const videoEncoder = getVideoEncoder(args);
  const isLibX264 = videoEncoder === 'libx264';
  const isVideoToolbox = Boolean(videoEncoder && videoEncoder.endsWith('_videotoolbox'));

  // Output file path is the last arg in stitcher command.
  const outputIndex = Math.max(0, args.length - 1);
  const inject = [
    ...(isVideoToolbox ? ['-allow_sw', '1'] : []),
    '-pix_fmt',
    'yuv420p',
    ...(isLibX264
      ? ['-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv']
      : []),
    '-color_range',
    'tv',
    '-colorspace',
    'bt709',
    '-color_primaries',
    'bt709',
    '-color_trc',
    'bt709',
    '-movflags',
    '+faststart+write_colr',
  ];
  args.splice(outputIndex, 0, ...inject);
  return args;
};

const entry = path.join(__dirname, 'src', 'index.tsx');

const serveUrl = await bundle({
  entryPoint: entry,
  publicDir: path.join(__dirname, 'public'),
  // Avoid noisy non-fatal webpack filesystem cache warnings in CLI renders.
  enableCaching: false,
});

const compositions = await getCompositions(serveUrl, {
  inputProps: props,
});

const composition = compositions.find((c) => c.id === 'StitchVideo');
if (!composition) {
  throw new Error('Composition "StitchVideo" not found.');
}

const finalComposition = {
  ...composition,
  fps,
  width,
  height,
  durationInFrames,
};

emitProgress(0);
await renderMedia({
  composition: finalComposition,
  serveUrl,
  codec,
  crf,
  hardwareAcceleration,
  colorSpace: 'bt709',
  pixelFormat: 'yuv420p',
  ffmpegOverride: enforceBt709,
  outputLocation: output,
  inputProps: props,
  onProgress: (update) => {
    if (!update || typeof update !== 'object') {
      return;
    }

    const asAny = update;
    if (typeof asAny.progress === 'number') {
      emitProgress(asAny.progress);
      return;
    }
    if (typeof asAny.overallProgress === 'number') {
      emitProgress(asAny.overallProgress);
      return;
    }

    const totalFrames =
      typeof asAny.totalFrames === 'number'
        ? asAny.totalFrames
        : typeof asAny.renderedFramesTotal === 'number'
          ? asAny.renderedFramesTotal
          : typeof asAny.encodedFramesTotal === 'number'
            ? asAny.encodedFramesTotal
            : null;

    const doneFrames =
      typeof asAny.encodedFrames === 'number'
        ? asAny.encodedFrames
        : typeof asAny.renderedFrames === 'number'
          ? asAny.renderedFrames
          : typeof asAny.frame === 'number'
            ? asAny.frame
            : null;

    if (
      typeof doneFrames === 'number' &&
      typeof totalFrames === 'number' &&
      Number.isFinite(doneFrames) &&
      Number.isFinite(totalFrames) &&
      totalFrames > 0
    ) {
      emitProgress(doneFrames / totalFrames);
    }
  },
});
emitProgress(1);

console.log(`Rendered to ${output}`);
