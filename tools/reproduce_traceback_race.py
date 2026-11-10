"""Bounded subprocess-only test of CPython's asynchronous traceback race.

WARNING: timer-mode children may crash intentionally during diagnosis. They
import no Atlas/broker modules. Never enable this sampler in a live process.
Related upstream reports: python/cpython#116008 and #131580.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys

CHILD=r'''
import ctypes,faulthandler,json,os,sys,threading,time
mode,duration,path=sys.argv[1],float(sys.argv[2]),sys.argv[3]
if os.name=="nt":
    ctypes.windll.kernel32.SetErrorMode(0x0001|0x0002)
stop=threading.Event()
stream=open(path,"w",buffering=1)
stream.write(json.dumps({"pid":os.getpid(),"mode":mode,"python":sys.version.split()[0]})+"\n")
stream.flush()
faulthandler.enable(file=stream,all_threads=True)
worker_errors=[]
successful_workers=0
def on_error(args):
    worker_errors.append(args.exc_type.__name__)
threading.excepthook=on_error
def churn(depth):
    if depth:return churn(depth-1)
    code=compile("def transient(x):\n return (x+1)*2\ntransient(42)","transient_frame","exec")
    exec(code,{})
def work():
    global successful_workers
    for _ in range(80):churn(16)
    successful_workers+=1
def cooperative():
    while not stop.wait(.005):
        faulthandler.dump_traceback(file=stream,all_threads=True)
sampler=None
if mode=="timer":
    faulthandler.dump_traceback_later(.005,repeat=True,file=stream)
elif mode=="cooperative":
    sampler=threading.Thread(target=cooperative)
    sampler.start()
end=time.monotonic()+duration
iterations=0
while time.monotonic()<end:
    workers=[threading.Thread(target=work) for _ in range(4)]
    for worker in workers:worker.start()
    for worker in workers:worker.join()
    iterations+=1
stop.set()
if sampler:sampler.join()
if mode=="timer":faulthandler.cancel_dump_traceback_later()
stream.close()
print(json.dumps({"pid":os.getpid(),"mode":mode,"iterations":iterations,"python":sys.version.split()[0],
    "successful_workers":successful_workers,"worker_errors":worker_errors,
    "atlas_or_broker_imported":any(name.startswith(("atlas_ai","MetaTrader5")) for name in sys.modules)}))
if worker_errors or not successful_workers:sys.exit(2)
'''


def run(output,repetitions=3,seconds=5):
    output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for mode in ("plain","timer","cooperative"):
        for attempt in range(repetitions):
            trace=output/f"{mode}_{attempt}.trace.log"
            stdout=output/f"{mode}_{attempt}.stdout.log";stderr=output/f"{mode}_{attempt}.stderr.log"
            env=os.environ.copy()
            for key in ("GEMINI_API_KEY","OPENAI_API_KEY"):env.pop(key,None)
            started=datetime.now(timezone.utc).isoformat()
            with stdout.open("w") as out,stderr.open("w") as err:
                proc=subprocess.Popen([sys.executable,"-I","-S","-c",CHILD,mode,str(seconds),str(trace.resolve())],
                    cwd=output,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                timed_out=False
                try:code=proc.wait(timeout=seconds+15)
                except subprocess.TimeoutExpired:
                    proc.kill();code=proc.wait();timed_out=True
            row={"mode":mode,"attempt":attempt,"pid":proc.pid,"started_at":started,"returncode":code,
                "windows_status_hex":hex(code & 0xffffffff),"timed_out":timed_out,
                "trace_bytes":trace.stat().st_size if trace.exists() else 0}
            if trace.exists():
                try:row["worker_pid"]=json.loads(trace.open(encoding="utf-8").readline())["pid"]
                except (ValueError,KeyError):pass
            rows.append(row);print(json.dumps(row),flush=True)
    result={"python":sys.version.split()[0],"workload":"Python frame allocation and thread creation/destruction only; no Atlas or broker imports",
        "results":rows,"timer_failures":sum(r["returncode"]!=0 for r in rows if r["mode"]=="timer"),
        "control_failures":sum(r["returncode"]!=0 for r in rows if r["mode"]!="timer"),
        "causal_scope":"Reproduction identifies a diagnostic failure mechanism; historical crash attribution still requires matching evidence."}
    (output/"results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--repetitions",type=int,default=3);parser.add_argument("--seconds",type=float,default=5)
    args=parser.parse_args()
    if not 1<=args.repetitions<=3 or not 1<=args.seconds<=10:parser.error("Bounded subprocess stress only: 1-3 trials, 1-10 seconds each")
    run(args.output_dir,args.repetitions,args.seconds)
