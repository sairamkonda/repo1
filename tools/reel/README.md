# reel: free kinetic-typography video maker

Makes 9:16 motivational reels in the Fortune Global style. The video is animated text, particles, light rays and the logo, and the music is synthesized on the spot. It runs entirely on this machine: no paid APIs, no stock assets, no photos.

## Setup (once)
```
cd tools/reel
npm install              # fonts: Anton + Montserrat (OFL)
pip install numpy scipy  # music synthesis
```
It needs `ffmpeg`, plus Playwright's Chromium, which is preinstalled in Claude cloud sessions.

## Make a video
1. Copy `videos/002-start-today/reel.json` to a new folder and edit `scenes` (words, timing, style) and `music` (cues).
2. Preview stills: `node render.js <reel.json> <outdir> --preview 1,5,9.3`
3. Render: `node render.js <reel.json> <out.mp4>`. 24 s takes about 2 minutes.

## Scene styles
`reveal`, `clock`, `glitch`, `flicker`, `dim`, `impact`, `strike` (set `"strike": <line index>`), `rise`, `slam`, `hero`, `endcard`.
Use `"gold": [i]` to make line `i` gold.

## Files
- `reel.html`: the canvas renderer (`setup(cfg)`, `frame(t)`)
- `render.js`: drives Chromium and pipes frames into ffmpeg
- `music.py`: synthesizes the soundtrack from the `music` cue sheet
- `make_logo.py`: cuts the logo mark out of `brand/logo.png` and saves it as `assets/logo-mark.png`
