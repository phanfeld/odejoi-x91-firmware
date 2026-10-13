#!/usr/bin/env python3
"""Embed a cover picture into an MP3 in the form the X91 firmware expects.

What the firmware does (from MUSIC.AP): on the playing screen the cover area is the box at
x=9, y=19, 110 wide and 90 high; the picture is centred in it, so a square cover shows at 90 x 90.
Covers are looked for in MP1/MP2/MP3, WMA, APE and FLAC files only.
This writes a copy of the MP3 (audio untouched) with one 90 x 90 baseline JPEG as an ID3v2.3 front cover.
Not yet confirmed on the player.

usage: x91_cover.py IN.mp3 COVER.(jpg|png) OUT.mp3 [SIZE]      (SIZE defaults to 90)
"""
import subprocess
import sys


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    src, cover, out = sys.argv[1:4]
    size = int(sys.argv[4]) if len(sys.argv) > 4 else 90
    scale = ("scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:black,format=yuvj420p"
             % (size, size, size, size))
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-i", cover,
           "-map", "0:a:0", "-map", "1:v:0", "-c:a", "copy",
           "-c:v", "mjpeg", "-vf", scale, "-q:v", "3", "-huffman", "default",
           "-map_metadata", "0", "-id3v2_version", "3", "-write_id3v1", "0",
           "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)",
           "-disposition:v:0", "attached_pic", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit("ffmpeg failed: " + r.stderr[-400:])
    print("written:", out)


if __name__ == "__main__":
    main()
