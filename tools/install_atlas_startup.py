"""Install current-user shortcuts for the existing local Atlas launcher."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))


def shortcut_script(root=ROOT):
    root = Path(root).resolve()
    python = root / ".venv/Scripts/pythonw.exe"
    launcher = root / "atlas_fullstack_startup.pyw"
    if not python.is_file() or not launcher.is_file():
        raise FileNotFoundError("Local Python environment or Atlas launcher missing")
    def literal(value): return "'" + str(value).replace("'", "''") + "'"
    arguments = subprocess.list2cmdline([str(launcher)])
    return (
        "$ErrorActionPreference='Stop'; $shell=New-Object -ComObject WScript.Shell; "
        "$links=@(@{folder='Desktop';name='Start Atlas.lnk'},@{folder='Startup';name='Atlas Full System.lnk'}); "
        "$created=@(); foreach($item in $links) { "
        "$folder=[Environment]::GetFolderPath($item.folder); if (!$folder) { throw 'Windows folder unavailable' }; "
        "$path=Join-Path $folder $item.name; $link=$shell.CreateShortcut($path); "
        "$link.TargetPath=" + literal(python) + "; $link.Arguments=" + literal(arguments) + "; "
        "$link.WorkingDirectory=" + literal(root) + "; $link.WindowStyle=7; "
        "$link.Description='Start Atlas locally using its existing guarded configuration; no Codex required'; "
        "$link.Save(); $created+=$path }; ConvertTo-Json -InputObject $created -Compress"
    )


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    script = shortcut_script()
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            capture_output=True, text=True, check=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print(json.dumps({"state": "installed", "shortcuts": json.loads(result.stdout),
                      "launcher": str(ROOT / "atlas_fullstack_startup.pyw"), "orders_sent": 0}, indent=2))


if __name__ == "__main__": main()
