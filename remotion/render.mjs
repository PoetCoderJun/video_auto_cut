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

const enforceBt709 = ({type, args: ffmpegArgs}) => {
  if (type !== 'stitcher') {
    return ffmpegArgs;
  }

  const args = [...ffmpegArgs];
  // Output file path is the last arg in stitcher command.
  const outputIndex = Math.max(0, args.length - 1);
  const inject = [
    '-pix_fmt',
    'yuv420p',
    '-x264-params',
    'colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv',
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

await renderMedia({
  composition: finalComposition,
  serveUrl,
  codec,
  crf,
  colorSpace: 'bt709',
  pixelFormat: 'yuv420p',
  ffmpegOverride: enforceBt709,
  outputLocation: output,
  inputProps: props,
});

console.log(`Rendered to ${output}`);
