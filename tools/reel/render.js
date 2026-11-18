// Render a reel: node render.js <reel.json> <out.mp4> [--preview t1,t2,...] [--music music.wav]
// Frames are drawn by reel.html in headless Chromium and piped straight into ffmpeg.
const { chromium } = require('playwright');
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

(async () => {
  const args = process.argv.slice(2);
  const cfgPath = path.resolve(args[0]);
  const out = path.resolve(args[1]);
  const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };
  const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
  cfg.fontDir = 'file://' + path.join(__dirname, 'node_modules/@fontsource');
  // A data URL keeps the canvas untainted so frames can be exported.
  cfg.logo = 'data:image/png;base64,' + fs.readFileSync(path.join(__dirname, 'assets/logo-mark.png')).toString('base64');

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: cfg.width, height: cfg.height }, deviceScaleFactor: 1 });
  page.on('pageerror', (e) => { console.error('page error:', e.message); process.exit(1); });
  await page.goto('file://' + path.join(__dirname, 'reel.html'));
  console.log('setup', await page.evaluate((c) => window.setup(c), cfg));

  const preview = opt('--preview');
  if (preview) {
    fs.mkdirSync(out, { recursive: true });
    for (const t of preview.split(',').map(Number)) {
      const url = await page.evaluate(([tt, i]) => window.frame(tt, i, 'image/png'), [t, Math.round(t * cfg.fps)]);
      fs.writeFileSync(path.join(out, `t${t.toFixed(2).padStart(5, '0')}.png`), Buffer.from(url.split(',')[1], 'base64'));
    }
    await browser.close();
    console.log('preview frames written to', out);
    return;
  }

  let music = opt('--music');
  if (!music) {
    music = out.replace(/\.mp4$/, '') + '.music.wav';
    execFileSync('python3', [path.join(__dirname, 'music.py'), cfgPath, music], { stdio: 'inherit' });
  }

  const ff = spawn('ffmpeg', [
    '-v', 'error', '-y',
    '-f', 'image2pipe', '-framerate', String(cfg.fps), '-c:v', 'mjpeg', '-i', '-',
    '-i', music,
    // CRF 22 keeps the film grain from bloating the file (~20 MB for 24 s).
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '22', '-pix_fmt', 'yuv420p', '-profile:v', 'high',
    '-r', String(cfg.fps), '-g', String(cfg.fps * 2),
    // -14 LUFS for Reels/Shorts; the limiter keeps true peaks under -1 dBFS after AAC.
    '-af', 'loudnorm=I=-14:TP=-2:LRA=11,aresample=48000,alimiter=limit=0.7:attack=1:release=50:level=false',
    '-c:a', 'aac', '-b:a', '192k',
    '-shortest', '-movflags', '+faststart', out,
  ], { stdio: ['pipe', 'inherit', 'inherit'] });

  const total = Math.round(cfg.duration * cfg.fps);
  const started = Date.now();
  for (let i = 0; i < total; i++) {
    const url = await page.evaluate(([t, idx]) => window.frame(t, idx), [i / cfg.fps, i]);
    const buf = Buffer.from(url.split(',')[1], 'base64');
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
    if (i % 60 === 0) console.log(`frame ${i}/${total} (${((Date.now() - started) / 1000).toFixed(0)}s)`);
  }
  ff.stdin.end();
  await new Promise((r, j) => ff.on('close', (code) => (code === 0 ? r() : j(new Error('ffmpeg exited ' + code)))));
  await browser.close();
  console.log('wrote', out, `in ${((Date.now() - started) / 1000).toFixed(0)}s`);
})().catch((e) => { console.error(e); process.exit(1); });
