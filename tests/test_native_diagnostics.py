from atlas_ai import native_diagnostics


def test_existing_fault_handler_is_preserved(monkeypatch,tmp_path):
    monkeypatch.setattr(native_diagnostics.faulthandler,"is_enabled",lambda:True)
    assert native_diagnostics.enable_native_diagnostics(tmp_path,"live")["existing_handler"]
    assert not (tmp_path/"native_crashes").exists()


def test_native_trace_uses_durable_process_specific_file(monkeypatch,tmp_path):
    monkeypatch.setattr(native_diagnostics.faulthandler,"is_enabled",lambda:False)
    seen={}
    monkeypatch.setattr(native_diagnostics.faulthandler,"enable",lambda **kw:seen.update(kw))
    monkeypatch.setattr(native_diagnostics,"_TRACE_STREAM",None)
    result=native_diagnostics.enable_native_diagnostics(tmp_path,"live")
    stream=seen["file"]
    assert result["enabled"] and seen["all_threads"]
    assert not stream.closed
    assert '"mode": "live"' in open(result["path"],encoding="utf-8").read()
    stream.close()
