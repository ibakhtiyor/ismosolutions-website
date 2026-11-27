"""Shared paths and a headless-Chrome helper for the tools (run from WSL)."""
import os, subprocess, tempfile

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE = os.path.dirname(SRC)                      # the built site = the repo root
WORK = os.path.join(os.path.dirname(SITE), ".work")  # scratch on a Windows drive, outside the repo
PREVIEW = os.path.join(os.path.dirname(SITE), "preview")
CHROME = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"


def win(path):
    return subprocess.check_output(["wslpath", "-w", path], text=True).strip()


def file_url(path):
    return "file:///" + win(path).replace("\\", "/")


def chrome(*args, timeout=180):
    # Chrome is a Windows program: its profile and work files must be on a Windows drive.
    os.makedirs(WORK, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="chrome-", dir=WORK)
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
           "--allow-file-access-from-files", "--user-data-dir=" + win(tmp), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
