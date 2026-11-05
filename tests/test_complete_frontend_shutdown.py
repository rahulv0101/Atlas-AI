from types import SimpleNamespace
from unittest.mock import Mock

from atlas_ai import atlas_full_shutdown as shutdown
from atlas_ai import runtime_processes


def test_shutdown_stops_desktop_then_api_and_verifies_all_are_gone(monkeypatch,tmp_path):
    alive={10,20};stopped=[]
    def inventory(mode,*,project_root):
        assert project_root==str(tmp_path)
        pid=10 if mode=="ui" else 20 if mode=="ui-server" else None
        return [{"ProcessId":pid}] if pid in alive else []
    monkeypatch.setattr(shutdown,"atlas_mode_processes",inventory)
    monkeypatch.setattr(shutdown,"process_exists",lambda pid:pid in alive)
    def stop(pid,force=False):
        stopped.append(pid);alive.remove(pid);return True
    monkeypatch.setattr(shutdown,"stop_process",stop)
    monkeypatch.setattr(shutdown,"wait_for",lambda check,**kw:(check(),None))
    result=shutdown._stop_frontend(SimpleNamespace(project_root=str(tmp_path)))
    assert stopped==[10,20]
    assert result["stopped"] and result["remaining_pids"]==[]


def test_unavailable_inventory_never_claims_clean_shutdown(monkeypatch,tmp_path):
    monkeypatch.setattr(shutdown,"atlas_mode_processes",lambda *a,**kw:None)
    stop=Mock();monkeypatch.setattr(shutdown,"stop_process",stop)
    assert not shutdown._stop_frontend(SimpleNamespace(project_root=str(tmp_path)))["stopped"]
    stop.assert_not_called()


def test_inventory_excludes_another_project_even_with_identical_mode(monkeypatch,tmp_path):
    class Process:
        def __init__(self,pid,root):self.pid=pid;self.root=root;self.info={"name":"python.exe"}
        def cmdline(self):return ["python.exe","-m","atlas_ai.main","ui"]
        def cwd(self):return self.root
        def ppid(self):return 1
    processes=[Process(10,str(tmp_path)),Process(20,str(tmp_path/"other"))]
    monkeypatch.setattr(runtime_processes,"psutil",SimpleNamespace(process_iter=lambda fields:processes,NoSuchProcess=type("Gone",(Exception,),{})))
    assert [row["ProcessId"] for row in runtime_processes.atlas_mode_processes("ui",project_root=tmp_path)]==[10]
