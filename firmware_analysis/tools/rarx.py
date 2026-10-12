#!/usr/bin/env python3
"""List or extract an archive through the system libarchive (ctypes).

usage: rarx.py list ARCHIVE
       rarx.py extract ARCHIVE DESTDIR [REGEX]
"""
import ctypes
import ctypes.util
import locale
import os
import re
import sys

locale.setlocale(locale.LC_ALL, "")
la = ctypes.CDLL(ctypes.util.find_library("archive") or "libarchive.so.13")

la.archive_read_new.restype = ctypes.c_void_p
la.archive_read_support_filter_all.argtypes = [ctypes.c_void_p]
la.archive_read_support_format_all.argtypes = [ctypes.c_void_p]
la.archive_read_open_filename.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
la.archive_read_next_header.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
la.archive_entry_pathname_w.argtypes = [ctypes.c_void_p]
la.archive_entry_pathname_w.restype = ctypes.c_wchar_p
la.archive_entry_size.argtypes = [ctypes.c_void_p]
la.archive_entry_size.restype = ctypes.c_int64
la.archive_entry_filetype.argtypes = [ctypes.c_void_p]
la.archive_entry_filetype.restype = ctypes.c_uint
la.archive_entry_mtime.argtypes = [ctypes.c_void_p]
la.archive_entry_mtime.restype = ctypes.c_int64
la.archive_read_data.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
la.archive_read_data.restype = ctypes.c_ssize_t
la.archive_read_data_skip.argtypes = [ctypes.c_void_p]
la.archive_error_string.argtypes = [ctypes.c_void_p]
la.archive_error_string.restype = ctypes.c_char_p
la.archive_read_free.argtypes = [ctypes.c_void_p]

AE_IFREG = 0o100000
AE_IFDIR = 0o040000


def entries(path):
    a = la.archive_read_new()
    la.archive_read_support_filter_all(a)
    la.archive_read_support_format_all(a)
    if la.archive_read_open_filename(a, os.fsencode(path), 1 << 20) != 0:
        sys.exit("open failed: %r" % la.archive_error_string(a))
    entry = ctypes.c_void_p()
    while True:
        r = la.archive_read_next_header(a, ctypes.byref(entry))
        if r == 1:
            break
        if r < 0:
            print("header error:", la.archive_error_string(a), file=sys.stderr)
            if r <= -25:
                break
        yield a, entry
    la.archive_read_free(a)


def main():
    mode, arc = sys.argv[1], sys.argv[2]
    if mode == "list":
        import time
        for a, e in entries(arc):
            ft = la.archive_entry_filetype(e)
            kind = "d" if ft == AE_IFDIR else "-"
            mt = time.strftime("%Y-%m-%d", time.gmtime(la.archive_entry_mtime(e)))
            print("%s %12d %s %s" % (kind, la.archive_entry_size(e), mt, la.archive_entry_pathname_w(e)))
            la.archive_read_data_skip(a)
        return
    dest = os.path.realpath(sys.argv[3])
    pat = re.compile(sys.argv[4], re.I) if len(sys.argv) > 4 else None
    buf = ctypes.create_string_buffer(1 << 20)
    for a, e in entries(arc):
        name = la.archive_entry_pathname_w(e)
        ft = la.archive_entry_filetype(e)
        if ft != AE_IFREG or (pat and not pat.search(name)):
            la.archive_read_data_skip(a)
            continue
        out = os.path.realpath(os.path.join(dest, name.replace("\\", "/").lstrip("/")))
        if not out.startswith(dest + os.sep):
            print("skip unsafe path:", name, file=sys.stderr)
            la.archive_read_data_skip(a)
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        total = 0
        with open(out, "wb") as f:
            while True:
                n = la.archive_read_data(a, buf, len(buf))
                if n < 0:
                    print("read error on", name, la.archive_error_string(a), file=sys.stderr)
                    break
                if n == 0:
                    break
                f.write(buf.raw[:n])
                total += n
        os.chmod(out, 0o644)
        print("extracted %12d %s" % (total, name))


if __name__ == "__main__":
    main()
