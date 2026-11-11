"""Resume the existing read-only observation plan at user sign-in; never start trading."""
import argparse
from datetime import datetime, timezone
import base64
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from atlas_ai.atomic_files import atomic_json
from tools import supervise_acceptance as supervisor

NAME="Atlas Acceptance Observation.lnk"


def shortcut_script(action,plan,*,root=ROOT,python=None):
    """Use the current user's OS-known Startup folder, without elevation or a shell."""
    if action not in {"install","remove"}:raise ValueError("invalid_startup_action")
    python=Path(python or sys.executable).with_name("pythonw.exe")
    if not python.is_file():raise FileNotFoundError("pythonw_required")
    def literal(value):return "'"+str(value).replace("'","''")+"'"
    prefix="$ErrorActionPreference='Stop'; $folder=[Environment]::GetFolderPath('Startup'); if (!$folder) { throw 'startup_folder_missing' }; "
    prefix+="$path=Join-Path $folder "+literal(NAME)+"; "
    if action=="remove":return prefix+"if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }; Write-Output $path"
    arguments=subprocess.list2cmdline([str(root/"tools/acceptance_startup.py"),"resume","--plan",str(Path(plan).resolve())])
    return prefix+"$link=(New-Object -ComObject WScript.Shell).CreateShortcut($path); "+\
        "$link.TargetPath="+literal(python)+"; $link.Arguments="+literal(arguments)+"; "+\
        "$link.WorkingDirectory="+literal(root)+"; $link.WindowStyle=7; $link.Save(); Write-Output $path"


def checked_plan(path):
    path=Path(path).resolve()
    if supervisor.digest(path)!=path.with_suffix(".sha256").read_text().strip():
        raise ValueError("acceptance_plan_changed")
    plan=supervisor.read(path)
    if Path(plan["project_root"]).resolve()!=ROOT:raise ValueError("startup_project_mismatch")
    supervisor.validate(plan,supervisor.load_settings())
    return plan


def resume(path,*,now=None,start=subprocess.Popen):
    plan=checked_plan(path);now=now or datetime.now(timezone.utc)
    if now>=datetime.fromisoformat(plan["deadline"]):return {"state":"deadline_reached","orders_sent":0}
    if supervisor.busy("natural",Path(path).with_suffix(".lock")):
        return {"state":"supervisor_already_running","orders_sent":0}
    folder=Path(plan["storage_dir"])/"acceptance_supervision";folder.mkdir(parents=True,exist_ok=True)
    with (folder/"supervisor.stdout.log").open("a") as out,(folder/"supervisor.stderr.log").open("a") as err:
        child=start([plan["python"],str(ROOT/"tools/supervise_acceptance.py"),"watch","--plan",str(Path(path).resolve())],
            cwd=ROOT,stdout=out,stderr=err,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    return {"state":"supervisor_launched","pid":child.pid,"orders_sent":0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("install","remove","resume"))
    parser.add_argument("--plan",type=Path,default=ROOT/"storage/acceptance_plan.json")
    args=parser.parse_args()
    try:
        if args.action=="resume":result=resume(args.plan)
        else:
            if args.action=="install":checked_plan(args.plan)
            code=shortcut_script(args.action,args.plan)
            encoded=base64.b64encode(code.encode("utf-16le")).decode("ascii")
            completed=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-EncodedCommand",encoded],
                capture_output=True,text=True,check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            result={"state":"installed" if args.action=="install" else "removed","shortcut":completed.stdout.strip(),"orders_sent":0}
    except Exception as exc:
        result={"state":"startup_failed","error":type(exc).__name__,"reason":str(exc),"orders_sent":0}
    result["checked_at"]=datetime.now(timezone.utc).isoformat()
    atomic_json(ROOT/"storage/acceptance_supervision/startup.status.json",result)
    if sys.stdout is not None:print(json.dumps(result))
    return 1 if result["state"]=="startup_failed" else 0


if __name__=="__main__":raise SystemExit(main())
