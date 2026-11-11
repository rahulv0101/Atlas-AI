"""Bounded, read-only publication evidence. Never a trading input or approval.

Sidecar observations are not atomic pre-decision checkpoints. A valid archive
proves what was captured, not full replay parity or strategy profitability.
"""
from datetime import datetime,timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re

from atlas_ai.atomic_files import atomic_json,replace_with_retry
from atlas_ai.learning.observation_checkpoint import observation_lock

STATUS_FIELDS=("symbol","timeframe","updated_at","action","message","chosen","signals","signals_active",
    "regime","higher_timeframe","chart_features","market","market_data_clock","freshness_runtime",
    "context_snapshot","visual_chart_read","setup_quality_observation","decision_analysis","timing_discipline",
    "timing_readiness","learning_critic","loss_to_win_playbook","winner_playbook","atlas_conviction",
    "confidence_diagnostics","min_confidence_threshold","min_confidence_threshold_raw","thresholds","drift",
    "contextual_ranking","risk","safety_layer","guarded_demo_auto_approval","execution","intraday_exit",
    "same_side_support","meta_model","learning_mode","mode_label")
LEARNING_FIELDS=("allocator","loss_memory","win_memory","best_evolved_strategy","evolved_strategy_pool",
    "meta_model","model_registry","online_learning","trade_outcome_intelligence")
RUNTIME_FIELDS=("execute_trades","gemini_influence_enabled","risk_guard_state","startup_verification",
    "automation_enabled","automation_paused","sleep_mode_active","active_automation_policy_id")
BLOCKERS=["observer_sampling_can_miss_publications","pre_decision_in_memory_state_unavailable",
    "saved_files_not_an_atomic_decision_checkpoint","running_code_not_bound_to_disk_version",
    "immutable_decision_pixels_not_guaranteed","intrabar_quotes_and_broker_protection_require_separate_evidence"]


def encoded(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def sha(data):return hashlib.sha256(data).hexdigest()


def sanitize(value,secrets=()):
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            normalized=re.sub(r"[^a-z0-9]","",str(key).lower())
            if (any(word in normalized for word in ("password","apikey","authorization","accesstoken","refreshtoken"))
                    or normalized.endswith(("accountlogin","hfmserver","hfmterminalpath","secret","token"))
                    or normalized in {"login","hfmlogin","accountid","accountnumber","username","user"}):continue
            result[str(key)]=sanitize(item,secrets)
        return result
    if isinstance(value,list):return [sanitize(item,secrets) for item in value]
    if isinstance(value,float) and not math.isfinite(value):return {"nonfinite_observation":str(value)}
    if isinstance(value,str):
        for secret in secrets:
            if secret and len(secret)>=4:value=value.replace(secret,"[redacted]")
        value=re.sub(r"([?&](?:key|api_key|token)=)[^&\s]+",r"\1[redacted]",value,flags=re.I)
        return re.sub(r"Bearer\s+\S+","Bearer [redacted]",value,flags=re.I)
    return value


def read_input(path,maximum=8*1024*1024):
    try:
        stat=path.stat()
        if stat.st_size>maximum:return None,{"state":"oversized_not_captured","bytes":stat.st_size}
        raw=path.read_bytes();after=path.stat()
        if (stat.st_size,stat.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            return None,{"state":"changed_during_read"}
        value=json.loads(raw.decode("utf-8-sig"))
        return value,{"state":"observed","source_sha256":sha(raw),"bytes":len(raw)}
    except (OSError,ValueError) as exc:return None,{"state":"unavailable","error":type(exc).__name__}


def index_rows(folder):
    path=folder/"index.jsonl"
    if not path.exists():return []
    rows=[];previous="0"*64
    for line in path.read_text(encoding="utf-8").splitlines():
        row=json.loads(line);body={k:v for k,v in row.items() if k!="chain_sha256"}
        if row["previous_chain"]!=previous or sha(encoded(body))!=row["chain_sha256"]:
            raise ValueError("archive_index_integrity_failed")
        if not re.fullmatch(r"[0-9a-f]{64}",row["record_id"]):raise ValueError("invalid_archive_record_id")
        previous=row["chain_sha256"];rows.append(row)
    return rows


def observed_image(storage,status,folder,remaining):
    visual=status.get("visual_chart_read") or {}
    image=visual.get("image") or {};capture=visual.get("capture") or {}
    image=image if isinstance(image,dict) else {"path":image}
    capture=capture if isinstance(capture,dict) else {}
    raw=image.get("path") or capture.get("path")
    if not raw:return {"state":"no_referenced_pixel_file"},{}
    try:
        path=Path(raw).resolve()
        try:path.relative_to(storage.resolve())
        except ValueError:
            path=(storage/raw).resolve();path.relative_to(storage.resolve())
        before=path.stat()
        if before.st_size>8*1024*1024:return {"state":"pixel_file_oversized"},{}
        data=path.read_bytes();after=path.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):return {"state":"pixel_file_changed_during_read"},{}
        suffix=".png" if data.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg" if data.startswith(b"\xff\xd8\xff") else ".webp" if data.startswith(b"RIFF") and data[8:12]==b"WEBP" else None
        if suffix is None:return {"state":"referenced_file_not_a_supported_image"},{}
        identity=sha(data);target=folder/"assets"/(identity+suffix)
        if target.exists() and sha(target.read_bytes())!=identity:raise RuntimeError("archived_pixels_changed")
        if not target.exists():
            used=sum(p.stat().st_size for p in (folder/"assets").glob("*") if p.is_file())
            if used+len(data)>256*1024*1024 or len(data)>remaining:return {"state":"pixel_budget_reached_metadata_retained"},{}
        expected=image.get("sha256") or capture.get("sha256")
        return {"state":"pixels_captured_as_observed","blob_id":identity,"suffix":suffix,
            "bytes":len(data),"decision_image_identity_verified":bool(expected and expected==identity),
            "source_captured_at":visual.get("captured_at"),
            "note":"Observed file bytes; absence of an original decision hash prevents exact image binding."},{} if target.exists() else {target:data}
    except (OSError,TypeError,ValueError):
        return {"state":"pixel_reference_unavailable_or_outside_storage"},{}


def _verify(folder):
    rows=index_rows(Path(folder));errors=[]
    checked_states=set()
    for row in rows:
        path=Path(folder)/"records"/(row["record_id"]+".json.gz")
        try:
            raw=path.read_bytes()
            if sha(raw)!=row["blob_sha256"]:raise ValueError("blob_changed")
            record=json.loads(gzip.decompress(raw))
            identity={k:v for k,v in record.items() if k!="observed_at"}
            if sha(encoded(identity))!=row["record_id"]:raise ValueError("record_identity_changed")
            if record["broker_eligible"] is not False or record["replay_ready"] is not False:
                raise ValueError("archive_cannot_grant_authority")
            for reference in record["saved_state"].values():
                blob_id=reference["blob_id"]
                if not re.fullmatch(r"[0-9a-f]{64}",blob_id):raise ValueError("invalid_state_blob_id")
                state_key=(blob_id,reference["blob_sha256"])
                if state_key not in checked_states:
                    blob=(Path(folder)/"state_blobs"/(blob_id+".json.gz")).read_bytes()
                    if sha(blob)!=reference["blob_sha256"] or sha(gzip.decompress(blob))!=blob_id:
                        raise ValueError("state_blob_changed")
                    checked_states.add(state_key)
            image=record.get("image_asset") or {}
            if image.get("state")=="pixels_captured_as_observed":
                if not re.fullmatch(r"[0-9a-f]{64}",image["blob_id"]) or image["suffix"] not in {".png",".jpg",".webp"}:
                    raise ValueError("invalid_pixel_reference")
                pixels=(Path(folder)/"assets"/(image["blob_id"]+image["suffix"])).read_bytes()
                if sha(pixels)!=image["blob_id"]:raise ValueError("archived_pixels_changed")
        except (OSError,ValueError,KeyError) as exc:errors.append({"record_id":row["record_id"],"error":type(exc).__name__})
    return {"records":len(rows),"valid":not errors,"errors":errors,"replay_ready":False,"broker_eligible":False}


def verify(folder):
    folder=Path(folder)
    if not folder.exists():return {"state":"archive_missing","records":0,"valid":False,"replay_ready":False}
    try:
        with observation_lock(folder/"archive.lock"):return _verify(folder)
    except RuntimeError:
        return {"state":"writer_busy_retry","valid":None,"replay_ready":False,"broker_eligible":False}


def publish_blob(path,raw):
    if path.exists():return
    path.parent.mkdir(exist_ok=True)
    temporary=path.with_suffix(".tmp")
    with temporary.open("xb") as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    replace_with_retry(temporary,path)


def capture(storage,now,*,secrets=(),budget_bytes=1024**3):
    storage=Path(storage);folder=storage/"replay_evidence";folder.mkdir(parents=True,exist_ok=True)
    with observation_lock(folder/"archive.lock"):
        rows=index_rows(folder)
        if rows:
            latest=folder/"records"/(rows[-1]["record_id"]+".json.gz")
            if sha(latest.read_bytes())!=rows[-1]["blob_sha256"]:raise ValueError("latest_archive_blob_changed")
        raw,source=read_input(storage/"status.json")
        if not isinstance(raw,dict):return {"state":"waiting_for_published_status","source":source,"replay_ready":False}
        status=sanitize({key:raw[key] for key in STATUS_FIELDS if key in raw},secrets)
        status_hash=sha(encoded(status))
        if rows and rows[-1]["status_sha256"]==status_hash:
            return {"state":"same_publication_already_captured","records":len(rows),"replay_ready":False,"broker_eligible":False}
        observations={};states={}
        for filename,fields in (("learning_state.json",LEARNING_FIELDS),("runtime_flags.json",RUNTIME_FIELDS)):
            value,meta=read_input(storage/filename);observations[filename]=meta
            if isinstance(value,dict):
                value=value.get("state",value) if filename=="learning_state.json" else value
                if isinstance(value,dict):states[filename]=sanitize({key:value[key] for key in fields if key in value},secrets)
        controls,meta=read_input(storage/"automation_state.json");observations["automation_state.json"]=meta
        if isinstance(controls,dict):
            payload=controls.get("payload",controls)
            if isinstance(payload,dict):states["automation_state.json"]=sanitize({key:payload[key] for key in
                ("sleep_mode_active","automation_enabled","automation_paused","session_control","tiny_live_pilot",
                 "execution_environment","gate_enabled","kill_switch") if key in payload},secrets)
        state_refs={};new_blobs={}
        for filename,state in states.items():
            state_raw=encoded(state);blob_id=sha(state_raw)
            path=folder/"state_blobs"/(blob_id+".json.gz")
            if path.exists():
                compressed=path.read_bytes()
                if sha(gzip.decompress(compressed))!=blob_id:raise ValueError("saved_state_blob_changed")
            else:
                compressed=gzip.compress(state_raw,mtime=0);new_blobs[path]=compressed
            state_refs[filename]={"blob_id":blob_id,"blob_sha256":sha(compressed)}
        again,_=read_input(storage/"status.json")
        if not isinstance(again,dict) or sha(encoded(sanitize({key:again[key] for key in STATUS_FIELDS if key in again},secrets)))!=status_hash:
            return {"state":"waiting_for_consistent_publication","replay_ready":False}
        stamp=None
        try:
            parsed=datetime.fromisoformat(str(status.get("updated_at","")).replace("Z","+00:00"))
            if parsed.tzinfo is not None:stamp=parsed.astimezone(timezone.utc)
        except ValueError:pass
        occupied=sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())
        remaining=budget_bytes-occupied-sum(len(blob) for blob in new_blobs.values())-1024**2
        image,image_blobs=observed_image(storage,status,folder,remaining)
        new_blobs.update(image_blobs)
        record={"schema":"atlas_published_evidence_v1","observed_at":now.isoformat(),"publication":status,"image_asset":image,
            "publication_source":source,"saved_state_observations":observations,"saved_state":state_refs,
            "publication_time_verified":stamp is not None,"publication_fresh":bool(stamp and 0<=(now-stamp).total_seconds()<=180),
            "capture_kind":"post_publication_observer","missing_replay_requirements":BLOCKERS,
            "replay_ready":False,"broker_eligible":False,"orders_sent":0}
        identity={k:v for k,v in record.items() if k!="observed_at"};record_id=sha(encoded(identity))
        compressed=gzip.compress(encoded(record),mtime=0)
        if occupied+len(compressed)+sum(len(blob) for blob in new_blobs.values())+2048>budget_bytes:
            return {"state":"storage_budget_reached_no_deletion","records":len(rows),"replay_ready":False,"broker_eligible":False}
        records=folder/"records";records.mkdir(exist_ok=True)
        for path,blob in new_blobs.items():publish_blob(path,blob)
        target=records/(record_id+".json.gz")
        if target.exists():
            existing=json.loads(gzip.decompress(target.read_bytes()))
            if {k:v for k,v in existing.items() if k!="observed_at"}!=identity:raise ValueError("existing_archive_record_changed")
        else:publish_blob(target,compressed)
        if any(row["record_id"]==record_id for row in rows):
            return {"state":"existing_record_reused","records":len(rows),"replay_ready":False,"broker_eligible":False}
        entry={"record_id":record_id,"blob_sha256":sha(target.read_bytes()),"status_sha256":status_hash,
            "decision_at":status.get("updated_at"),"previous_chain":rows[-1]["chain_sha256"] if rows else "0"*64}
        entry["chain_sha256"]=sha(encoded(entry))
        with (folder/"index.jsonl").open("ab") as stream:stream.write(encoded(entry)+b"\n");stream.flush();os.fsync(stream.fileno())
        result={"state":"publication_captured","records":len(rows)+1,"latest_record_id":record_id,
            "checked_at":now.isoformat(),"replay_ready":False,"broker_eligible":False,
            "image_state":image["state"],
            "coverage":"Sampled publications and saved states; not complete atomic decision inputs."}
        atomic_json(folder/"status.json",result)
        return result
