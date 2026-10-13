#!/usr/bin/env python3
"""X91 firmware tool: a terminal interface for two jobs on the ODEJOI X91 player.

  Dump            read the firmware from the player into a file (nothing is written to the player) and check it
  Flash a theme   write one of the theme images, the firmware the last write replaced, or the original
                  firmware to the player; what is on the player is saved first, and the result is read back
                  and compared

The procedure itself lives in x91_dump/x91_flash.py; this tool chooses files, switches the player into
upgrade mode, runs the procedure and explains the outcome. Talking to the player needs root, so the tool
restarts itself through sudo.

usage: x91_tool.py            the tool
       x91_tool.py --demo     the same screens with a simulated player; touches no device
"""
import curses
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DUMP = ROOT / "x91_dump"
FLASH = DUMP / "x91_flash.py"
ACTIONS_DUMP = ROOT / "actions_flash" / "actions_dump"
THEMES = DUMP / "themes"
BACKUPS = DUMP / "backups"
WORK = DUMP / "flash_work"
STOCK = DUMP / "x91_lfi_verified.bin"
USB_IDS = {("10d6", "1101"): "disk", ("10d6", "10d6"): "upgrade"}
PER_DEVICE = [(0x28, 0x38), (0x4F, 0x80), (0x1FE, 0x200)]      # header fields a write keeps from the player, and their checksum
RESTART = ["Unplug the player, hold its power key for 10 to 15 seconds, release,",
           "then switch it on normally."]
DEMO = "--demo" in sys.argv

sys.path.insert(0, str(DUMP))


# ------------------------------------------------------------------ the player and the firmware files

def usb_state():
    """'disk' (normal USB mode), 'upgrade' or 'none'."""
    if DEMO:
        return Demo.state
    found = "none"
    for d in Path("/sys/bus/usb/devices").glob("*"):
        try:
            key = ((d / "idVendor").read_text().strip(), (d / "idProduct").read_text().strip())
        except OSError:
            continue
        if key in USB_IDS:
            found = USB_IDS[key]
            if found == "upgrade":
                break
    return found


def player_mounts():
    """Where the player's drive is mounted, if anywhere."""
    r = subprocess.run(["lsblk", "-J", "-o", "NAME,TRAN,VENDOR,MOUNTPOINTS"], capture_output=True, text=True)
    found = []
    try:
        for dev in json.loads(r.stdout).get("blockdevices", []):
            if dev.get("tran") == "usb" and (dev.get("vendor") or "").strip() == "ACTIONS":
                for node in [dev] + dev.get("children", []):
                    found += [m for m in node.get("mountpoints") or [] if m]
    except ValueError:
        pass
    return found


def core_hash(data):
    """Hash of an image without the few header fields that belong to the individual player."""
    b = bytearray(data)
    for s, e in PER_DEVICE:
        b[s:e] = bytes(e - s)
    return hashlib.sha256(b).hexdigest()


def firmwares():
    """The images that can be written: the themes built by design/build_theme.py, what the last write replaced
    (the way back if a new stage misbehaves), and the original firmware."""
    items = []
    listing = THEMES / "themes.json"
    if listing.exists():
        for t in json.loads(listing.read_text()):
            p = THEMES / t["file"]
            if p.exists():
                items.append(dict(key=t["id"], name=t["name"] + " theme", accent=t.get("accent"), path=p,
                                  note="design stage %s, built %s" % (t.get("stage", "?"), t.get("built", "?"))))
    saved = sorted(BACKUPS.glob("before_*.bin"), key=lambda p: p.stat().st_mtime) if BACKUPS.exists() and not DEMO else []
    if saved:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(saved[-1].stat().st_mtime))
        items.append(dict(key="previous", name="Previous firmware", accent=None, path=saved[-1],
                          note="what the last write replaced, saved %s" % when))
    if STOCK.exists():
        items.append(dict(key="stock", name="Original firmware", accent=None, path=STOCK,
                          note="as first read from this player"))
    return items


class Known:
    """Recognise an image as one of the known firmwares (hashing 20 MB files takes a moment, so results are kept)."""
    cache = {}

    @classmethod
    def of(cls, path):
        p = Path(path)
        try:
            key = (str(p), p.stat().st_mtime_ns, p.stat().st_size)
        except OSError:
            return None
        if key not in cls.cache:
            cls.cache[key] = core_hash(p.read_bytes())
        return cls.cache[key]

    @classmethod
    def name(cls, path, items):
        h = cls.of(path)
        for it in items:
            if h and cls.of(it["path"]) == h:
                return it["name"]
        return None


def image_problems(path):
    import x91_flash
    data = Path(path).read_bytes()
    size = STOCK.stat().st_size if STOCK.exists() else len(data)
    if len(data) != size:
        return ["it is %d bytes; the player needs exactly %d" % (len(data), size)]
    return x91_flash.lfi_problems(data)


# ------------------------------------------------------------------ helper jobs, run as child processes

def helper_upgrade():
    """Unmount the player's drive and switch it from USB mode into upgrade mode."""
    for mp in player_mounts():
        print("unmounting %s" % mp, flush=True)
        if subprocess.run(["umount", mp]).returncode:
            print("STOP: could not unmount the player's drive; close whatever is using it and try again", flush=True)
            return 1
    print("== switching the player into upgrade mode", flush=True)
    r = subprocess.run([str(ACTIONS_DUMP), "--id", "10d6:1101", "adfu_reboot"], cwd=ACTIONS_DUMP.parent,
                       capture_output=True, text=True, timeout=60)
    for line in (r.stdout + r.stderr).strip().splitlines()[-4:]:
        print("   " + line, flush=True)
    for _ in range(60):
        if usb_state() == "upgrade":
            print("the player is in upgrade mode", flush=True)
            return 0
        time.sleep(0.5)
    print("STOP: the player did not show up in upgrade mode", flush=True)
    return 1


class Demo:
    """A pretend player for --demo."""
    state = "disk"
    dir = None

    @staticmethod
    def job(kind, target=None):
        say = lambda s, t=0.35: (print(s, flush=True), time.sleep(t))
        if kind == "upgrade":
            say("unmounting /media/demo/PLAYER")
            say("== switching the player into upgrade mode", 1.2)
            say("the player is in upgrade mode")
            return 0
        say("cross-checks passed" + ("; using the READ-ONLY driver (erase and program are disabled)" if kind == "dump" else ""))
        for step in ("loader (adfus)", "hardware scan (vendor nandhwsc)", "flash driver + chip record"):
            say("\n== " + step, 0.5)
        say("   hardware scan ok: NAND 8984643ca50c, chip-record slot 0x125400")
        if kind == "dump":
            say("\n== read the whole firmware through the driver", 2.5)
            src = (THEMES / "x91_lfi_amber.bin") if (THEMES / "x91_lfi_amber.bin").exists() else STOCK
            shutil.copyfile(src, target)
            say("   saved: %s" % target)
            say("   19871232 bytes, sha256 " + hashlib.sha256(Path(target).read_bytes()).hexdigest())
            say("   checksums: all ok")
            say("\nDUMP COMPLETE: the image passes all its checksums.")
        else:
            say("\n== read the current header", 0.4)
            say("\n== back up the current firmware", 2.0)
            say("   saved: %s" % target)
            say("   checksums: all ok")
            say("\n== WRITE the firmware area", 3.0)
            say("\n== finalize", 0.5)
            say("\n== read back", 2.0)
            say("\nVERIFIED: all 38811 sectors read back identical.")
        say("Now unplug and hold the power key 10 to 15 s, then switch on normally.")
        return 0


# ------------------------------------------------------------------ the interface

def nearest_256(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    step = lambda v: 0 if v < 48 else 1 if v < 115 else (v - 35) // 40
    return 16 + 36 * step(r) + 6 * step(g) + step(b)


class UI:
    SPIN = "|/-\\"

    def __init__(self, scr):
        self.scr = scr
        try:
            curses.curs_set(0)
        except curses.error:                 # a terminal that cannot hide its cursor
            pass
        self.colour = {}
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            for n, (name, c8, c256) in enumerate([("accent", curses.COLOR_YELLOW, 214), ("good", curses.COLOR_GREEN, 78),
                                                  ("bad", curses.COLOR_RED, 203), ("info", curses.COLOR_CYAN, 75)], 1):
                curses.init_pair(n, c256 if curses.COLORS >= 256 else c8, -1)
                self.colour[name] = curses.color_pair(n)
            self.next_pair = 10
        self.swatches = {}

    def attr(self, name):
        return self.colour.get(name, curses.A_BOLD if name in ("accent", "bad") else 0)

    def swatch(self, hex_colour):
        """Attribute for a small block in a theme's accent colour (bold text on terminals without enough colours)."""
        if not hex_colour or not curses.has_colors() or curses.COLORS < 256:
            return curses.A_BOLD
        if hex_colour not in self.swatches:
            curses.init_pair(self.next_pair, nearest_256(hex_colour), -1)
            self.swatches[hex_colour] = curses.color_pair(self.next_pair)
            self.next_pair += 1
        return self.swatches[hex_colour]

    def put(self, y, x, text, attr=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and 0 <= x < w - 1:
            try:
                self.scr.addnstr(y, x, text, w - 1 - x, attr)
            except curses.error:
                pass

    def frame(self, title, hint):
        """Clear the screen and draw title, player status and key hints. Returns the first free row and the width."""
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        self.put(0, 2, "X91 firmware tool", curses.A_BOLD | self.attr("accent"))
        self.put(0, 21, "- " + title, curses.A_BOLD)
        state = usb_state()
        label, colour = {"none": ("player: not connected", "bad"), "disk": ("player: connected (USB mode)", "good"),
                         "upgrade": ("player: connected (upgrade mode)", "info")}[state]
        self.put(1, 2, label, self.attr(colour))
        if DEMO:
            self.put(1, max(2, w - 26), "demo: simulated player", curses.A_DIM)
        self.put(2, 1, "-" * (w - 3), curses.A_DIM)
        self.put(h - 2, 1, "-" * (w - 3), curses.A_DIM)
        self.put(h - 1, 2, hint, curses.A_DIM)
        return 4, w

    def key(self, wait_ms=250):
        self.scr.timeout(wait_ms)
        return self.scr.getch()

    def menu(self, title, rows, intro=(), hint="Up/Down move   Enter choose   q back"):
        """rows: (label, note, accent colour or None, extra). Returns the chosen index or None."""
        sel = 0
        while True:
            y, w = self.frame(title, hint)
            for line in intro:
                self.put(y, 2, line)
                y += 1
            y += 1 if intro else 0
            for i, (label, note, accent, extra) in enumerate(rows):
                mark = ">" if i == sel else " "
                self.put(y, 2, mark, curses.A_BOLD | self.attr("accent"))
                if accent is not False:
                    self.put(y, 4, "##" if accent else "..", self.swatch(accent) if accent else curses.A_DIM)
                x = 7 if accent is not False else 4
                self.put(y, x, label, curses.A_BOLD if i == sel else 0)
                if extra:
                    self.put(y, x + len(label) + 2, extra, self.attr("good"))
                if note:
                    self.put(y + 1, x, note, curses.A_DIM)
                y += 3 if note else 2
            k = self.key()
            if k in (curses.KEY_UP, ord("k")):
                sel = (sel - 1) % len(rows)
            elif k in (curses.KEY_DOWN, ord("j")):
                sel = (sel + 1) % len(rows)
            elif k in (10, 13, curses.KEY_ENTER):
                return sel
            elif k in (ord("q"), 27):
                return None

    def message(self, title, lines, hint="Enter continue"):
        """lines: text, or (text, colour name)."""
        while True:
            y, w = self.frame(title, hint)
            for line in lines:
                text, colour = line if isinstance(line, tuple) else (line, None)
                self.put(y, 2, text, self.attr(colour) | (curses.A_BOLD if colour else 0) if colour else 0)
                y += 1
            if self.key() in (10, 13, curses.KEY_ENTER, ord("q"), 27):
                return

    def confirm(self, title, lines, word="YES"):
        """The user has to type the word and press Enter. Esc cancels."""
        typed = ""
        while True:
            y, w = self.frame(title, "type %s and press Enter to go ahead   Esc cancel" % word)
            for line in lines:
                text, colour = line if isinstance(line, tuple) else (line, None)
                self.put(y, 2, text, self.attr(colour) | curses.A_BOLD if colour else 0)
                y += 1
            self.put(y + 1, 2, "> " + typed + "_", curses.A_BOLD)
            k = self.key()
            if k == 27:
                return False
            if k in (10, 13, curses.KEY_ENTER):
                if typed == word:
                    return True
                typed = ""
            elif k in (curses.KEY_BACKSPACE, 127, 8):
                typed = typed[:-1]
            elif 32 <= k < 127 and len(typed) < 12:
                typed += chr(k).upper()

    def wait_for(self, title, lines, done):
        """Show instructions until done() is true. Esc gives up."""
        t0 = time.time()
        while not done():
            y, w = self.frame(title, "waiting...   Esc cancel")
            for line in lines:
                self.put(y, 2, line)
                y += 1
            self.put(y + 1, 2, self.SPIN[int((time.time() - t0) * 4) % 4] + " waiting for the player", self.attr("info"))
            if self.key() == 27:
                return False
        return True

    def run(self, title, argv):
        """Run a child process and show its output while it works. Returns (exit code, lines)."""
        lines, q, t0 = [], queue.Queue(), time.time()
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=lambda: [q.put(l.rstrip("\n")) for l in proc.stdout] and None, daemon=True).start()
        step = "starting"
        while True:
            try:
                while True:
                    line = q.get_nowait()
                    lines.append(line)
                    if line.startswith("== "):
                        step = line[3:]
            except queue.Empty:
                pass
            finished = proc.poll() is not None and q.empty()
            y, w = self.frame(title, "working - do not unplug the player" if not finished else "Enter continue")
            h = self.scr.getmaxyx()[0]
            if not finished:
                self.put(y, 2, "%s %s   (%d s)" % (self.SPIN[int((time.time() - t0) * 4) % 4], step, time.time() - t0),
                         curses.A_BOLD | self.attr("accent"))
            else:
                ok = proc.returncode == 0
                self.put(y, 2, "finished" if ok else "stopped (exit code %d)" % proc.returncode,
                         curses.A_BOLD | self.attr("good" if ok else "bad"))
            shown = [l for l in lines if l.strip()][-(h - y - 5):]
            for i, l in enumerate(shown):
                colour = "bad" if l.startswith(("STOP", "REFUSED", "VERIFY FAILED", "NOT identical")) else \
                    "good" if l.startswith(("VERIFIED", "DUMP COMPLETE")) else "accent" if l.startswith("== ") else None
                self.put(y + 2 + i, 2, l, self.attr(colour) if colour else curses.A_DIM)
            k = self.key(150)
            if finished and k in (10, 13, curses.KEY_ENTER):
                return proc.returncode, lines


# ------------------------------------------------------------------ the two jobs

class Session:
    used = False            # one run of the procedure per stay in upgrade mode; then the player has to be restarted


def python(*args):
    return [sys.executable, "-u"] + [str(a) for a in args]


def to_upgrade(ui):
    """Get the player into a fresh upgrade mode. False if the user gave up."""
    while True:
        state = usb_state()
        if state == "none":
            if not ui.wait_for("Connect the player", ["Switch the player on and plug it in with the USB cable.",
                                                      "Its screen should show the USB connection picture."],
                               lambda: usb_state() != "none"):
                return False
        elif state == "upgrade" and Session.used:
            if DEMO:
                Demo.state, Session.used = "disk", False
                continue
            if not ui.wait_for("Restart the player", ["The player has to be restarted before the next job:", ""] + RESTART +
                               ["", "Then plug it in again."], lambda: usb_state() == "disk"):
                return False
            Session.used = False
        elif state == "upgrade":
            return True
        else:
            rc, _ = ui.run("Preparing the player", python(__file__, "--helper", "upgrade") + (["--demo"] if DEMO else []))
            if DEMO and rc == 0:
                Demo.state = "upgrade"
            if rc != 0:
                ui.message("Preparing the player", [("The player did not go into upgrade mode.", "bad"), "",
                                                   "Unplug it, switch it on, plug it in again and retry."])
                return False


def restart_note(extra=()):
    return list(extra) + [""] + RESTART


def job_dump(ui):
    items = firmwares()
    if not to_upgrade(ui):
        return
    out = (Path(Demo.dir) if DEMO else BACKUPS) / time.strftime("x91_firmware_%Y-%m-%d_%H%M%S.bin")
    argv = python(__file__, "--helper", "fake-dump", out, "--demo") if DEMO else python(FLASH, "dump", "--out", out)
    rc, lines = ui.run("Dumping the firmware", argv)
    Session.used = True
    if out.exists():
        which = Known.name(out, items)
        size, digest = out.stat().st_size, hashlib.sha256(out.read_bytes()).hexdigest()
        head = ("The firmware was read and passes all its checksums.", "good") if rc == 0 else \
               ("The firmware was read, but it fails its checksums.", "bad")
        ui.message("Dump finished", [head, "", "file    %s" % out, "size    %d bytes" % size, "sha256  %s" % digest,
                                     "it is   %s" % (which or "none of the known images"), ""] + RESTART)
    else:
        ui.message("Dump failed", [("Nothing was saved.", "bad"), ""] + [l for l in lines if l.strip()][-4:] + restart_note())


def job_flash(ui):
    items = firmwares()
    if not items:
        ui.message("Flash a theme", [("No images found.", "bad"), "", "Build them with: python3 design/build_theme.py"])
        return
    last = Known.name(WORK / "readback.bin", items) if (WORK / "readback.bin").exists() else None
    rows = [(it["name"], it["note"], it["accent"], "<- last written to the player" if it["name"] == last else "") for it in items]
    pick = ui.menu("Flash a theme", rows, intro=["Choose what to write to the player."])
    if pick is None:
        return
    it = items[pick]
    problems = image_problems(it["path"])
    if problems:
        ui.message("Flash a theme", [("This image cannot be used:", "bad"), ""] + ["  " + p for p in problems[:6]])
        return
    if not DEMO and not (WORK / "rehearsal_ok").exists():
        ui.message("Flash a theme", [("Writing is locked.", "bad"), "",
                                     "The one-time read check (x91_flash.py rehearse) has not been passed on this computer.",
                                     "See reports/X91 write procedure.md."])
        return
    if not ui.confirm("Flash a theme", [("Write '%s' to the player?" % it["name"], "accent"), "",
                                        "file    %s" % it["path"],
                                        "sha256  %s" % hashlib.sha256(it["path"].read_bytes()).hexdigest(), "",
                                        "The firmware on the player is replaced. What is on it now is saved first.",
                                        "Music, playlists and other files are not touched; settings may be reset.",
                                        "Keep the player plugged in until the tool says it is finished."]):
        return
    if not to_upgrade(ui):
        return
    backup = (Path(Demo.dir) if DEMO else BACKUPS) / time.strftime("before_%%s_%Y-%m-%d_%H%M%S.bin") .replace("%s", it["key"])
    first = True
    while True:
        if DEMO:
            argv = python(__file__, "--helper", "fake-write", backup, "--demo")
        else:
            argv = python(FLASH, "write", "--image", it["path"], "--yes-write-flash") + (["--backup", str(backup)] if first else [])
        rc, lines = ui.run("Writing %s" % it["name"], argv)
        Session.used = True
        text = "\n".join(lines)
        if rc == 0 and "VERIFIED" in text:
            ui.message("Finished", [("'%s' is on the player and was read back identical." % it["name"], "good"), "",
                                    "saved before writing: %s" % backup, ""] + RESTART)
            return
        if "VERIFY FAILED" in text:
            if ui.confirm("Verification failed", [("The player's firmware does not match what was written.", "bad"), "",
                                                  "Leave the player plugged in and do NOT restart it.",
                                                  "Writing again usually fixes this."], word="RETRY"):
                first = False
                continue
            ui.message("Verification failed", [("The player may not start in this state.", "bad"), "",
                                               "Keep it plugged in and run the tool again to write an image."])
            return
        wrote = "WRITE the firmware area" in text
        ui.message("Stopped", [("The job stopped before it finished.", "bad"), ""] + [l for l in lines if l.strip()][-5:] + [""] +
                   (["The write had already started: write an image again before restarting the player."] if wrote
                    else ["Nothing was written to the player."] + restart_note()))
        return


def main_screen(scr):
    ui = UI(scr)
    while True:
        items = firmwares()
        last = Known.name(WORK / "readback.bin", items) if (WORK / "readback.bin").exists() else None
        intro = ["Themes available: %s" % (", ".join(i["name"].replace(" theme", "") for i in items if i["key"] != "stock") or "none"),
                 "Last written with this computer: %s" % (last or "unknown")]
        pick = ui.menu("Main menu", [("Dump the firmware", "Read it from the player into a file. Nothing is written to the player.", False, ""),
                                     ("Flash a theme", "Write a theme or the original firmware. The current one is saved first.", False, ""),
                                     ("Quit", "", False, "")], intro=intro, hint="Up/Down move   Enter choose   q quit")
        if pick == 0:
            job_dump(ui)
        elif pick == 1:
            job_flash(ui)
        else:
            return


def main():
    if "--helper" in sys.argv:
        kind = sys.argv[sys.argv.index("--helper") + 1]
        if kind == "upgrade":
            sys.exit(Demo.job("upgrade") if DEMO else helper_upgrade())
        if kind in ("fake-dump", "fake-write") and DEMO:
            sys.exit(Demo.job(kind.replace("fake-", ""), sys.argv[sys.argv.index("--helper") + 2]))
        sys.exit("unknown helper")
    for needed in (FLASH, STOCK):
        if not needed.exists():
            sys.exit("missing %s - run this tool from the project folder" % needed)
    if DEMO:
        with tempfile.TemporaryDirectory() as Demo.dir:
            curses.wrapper(main_screen)
        return
    if not ACTIONS_DUMP.exists():
        sys.exit("missing %s (see reports/X91 write procedure.md)" % ACTIONS_DUMP)
    if os.geteuid() != 0:
        print("Talking to the player needs root; restarting through sudo.")
        os.execvp("sudo", ["sudo", sys.executable, str(Path(__file__).resolve())] + sys.argv[1:])
    curses.wrapper(main_screen)


if __name__ == "__main__":
    main()
