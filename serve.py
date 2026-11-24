"""Start a local desktop session or a hosted Python service."""
import os
import secrets
import sys
from pathlib import Path
import subprocess
from urllib.parse import quote
from threading import Timer
import webbrowser
from waitress import serve
from app import app

def open_local_map(url):
    if sys.platform=="win32":
        for key in ("ProgramFiles","ProgramFiles(x86)","LOCALAPPDATA"):
            base=os.environ.get(key)
            if base:
                brave=Path(base)/"BraveSoftware"/"Brave-Browser"/"Application"/"brave.exe"
                if brave.is_file():
                    subprocess.Popen([str(brave),url])
                    return
    webbrowser.open(url)

if __name__ == "__main__":
    local="--desktop" in sys.argv
    port=int(os.environ.get("PORT","8434"))
    if local:
        os.environ.setdefault("YALOVA_ADMIN_TOKEN",secrets.token_urlsafe(24))
        print("Administrator key for the Data tab:",os.environ["YALOVA_ADMIN_TOKEN"],flush=True)
        session=quote(os.environ["YALOVA_ADMIN_TOKEN"],safe="")
        Timer(1.5,lambda:open_local_map(f"http://127.0.0.1:{port}/#session={session}")).start()
    host="127.0.0.1" if local else os.environ.get("YALOVA_HOST","0.0.0.0")
    print(f"Serving Yalova GIS on {host}:{port}",flush=True)
    serve(app,host=host,port=port,threads=6,channel_timeout=1800)

