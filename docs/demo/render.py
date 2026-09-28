"""Render docs/demo/explainer.html to MP4 (for X) and GIF (for the README).

Needs Playwright (pip install playwright && playwright install chromium) and
ffmpeg on PATH. The page is deterministic: seek(t) draws the frame at time t.

    python docs/demo/render.py                  # full render
    python docs/demo/render.py --stills 2,8,16  # a few PNG keyframes to eyeball
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PAGE = (HERE / "explainer.html").as_uri() + "?capture=1"
ASSETS = HERE.parent / "assets"
FPS = 30


def frames(times, out_dir):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(PAGE)
        page.wait_for_function("typeof window.seek === 'function'")
        for i, t in enumerate(times):
            page.evaluate("t => window.seek(t)", t)
            page.screenshot(path=str(out_dir / "f{:04d}.png".format(i)))
        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", help="comma-separated seconds; writes PNGs to docs/demo/stills")
    args = ap.parse_args()

    if args.stills:
        out = HERE / "stills"
        out.mkdir(exist_ok=True)
        times = [float(x) for x in args.stills.split(",")]
        frames(times, out)
        for i, t in enumerate(times):
            (out / "f{:04d}.png".format(i)).replace(out / "t{:05.1f}.png".format(t))
        print("wrote", len(times), "stills to", out)
        return

    with sync_playwright() as pw:
        duration = None
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(PAGE)
        duration = page.evaluate("window.DURATION")
        browser.close()

    tmp = Path(tempfile.mkdtemp(prefix="skillrot-frames-"))
    try:
        frames([i / FPS for i in range(int(duration * FPS))], tmp)
        ASSETS.mkdir(exist_ok=True)
        mp4, gif = ASSETS / "skillrot-explainer.mp4", ASSETS / "skillrot-explainer.gif"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                        "-i", str(tmp / "f%04d.png"), "-c:v", "libx264", "-preset", "slow",
                        "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
                       check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                        "fps=12,scale=960:-1:flags=lanczos,split[a][b];"
                        "[a]palettegen=max_colors=64:stats_mode=diff[p];"
                        "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                        str(gif)], check=True)
        for f in (mp4, gif):
            print("{}  {:.1f} MB".format(f, f.stat().st_size / 1e6))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
