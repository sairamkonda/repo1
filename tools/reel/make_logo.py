"""Cut the Fortune Global logo mark (the three arcs) out of its white background."""
import sys
import numpy as np
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
im = np.asarray(Image.open(src).convert("RGB")).astype(np.float32) / 255.0
# The mark sits above the wordmark; find its rows/cols from non-white pixels.
whiteness = im.min(axis=2)
mask = whiteness < 0.85
rows = np.where(mask[:950].any(axis=1))[0]
cols = np.where(mask[:950].any(axis=0))[0]
y0, y1 = max(rows[0] - 20, 0), min(rows[-1] + 20, 950)
x0, x1 = max(cols[0] - 20, 0), min(cols[-1] + 20, im.shape[1])
crop = im[y0:y1, x0:x1]
# Unblend from white: alpha from how far the pixel is from white, colour un-premultiplied.
alpha = np.clip((1.0 - crop.min(axis=2)) / 0.75, 0, 1)
alpha = np.where(alpha < 0.06, 0, alpha)
safe = np.maximum(alpha, 1e-3)[..., None]
rgb = np.clip((crop - (1 - alpha[..., None])) / safe, 0, 1)
out = np.dstack([rgb, alpha])
Image.fromarray((out * 255).astype(np.uint8), "RGBA").save(dst)
print("crop", (x0, y0, x1, y1), "->", dst, out.shape)
