#!/usr/bin/env python3
"""
MinIO ugs-* bucket GC 脚本（auto-server，/data/minio/data）

安全约束（硬编码，不可绕过）：
  1. 只允许清理名字以 "ugs-" 开头的 bucket，其他 bucket 直接拒绝
  2. manifest_*.json 永远不删（本脚本没有任何删除 manifest 的代码路径）
  3. 被「RETENTION_DAYS 天内的 manifest」引用的 blob 永远不删；
     execute 阶段会重新解析近期 manifest 再过滤一次待删清单，
     防止 dry-run 之后新 manifest 引用了清单里的旧 blob（内容寻址去重场景）
  4. mtime 在 GRACE_DAYS 天内的 blob 一律不删（防上传中途半成品）
  5. execute 只删 delete_list.csv 里的条目，且逐条校验 key 形态必须是 <2hex>/<62hex>

用法：
  python3 ugs_gc.py dry-run  --bucket ugs-binaries            # 分析，产出 delete_list.csv + summary.txt
  python3 ugs_gc.py execute  --bucket ugs-binaries            # 按清单经 S3 API 删除（重校验 + 断点续删）
  python3 ugs_gc.py execute  --bucket ugs-binaries --limit N  # 只删前 N 个（小批量验证）

MinIO 对象存储格式备忘（本机实测，2026-10-30）：
  - blob 的 S3 key = "<2hex>/<62hex>"，盘上路径 /data/minio/data/<bucket>/<key>/<uuid>/part.*
  - manifest payload 每 1MiB 数据前有 32 字节二进制头（分片步长 1048608），解析 JSON 前必须剥掉
  - 根凭证从 `docker inspect minio` 的 MINIO_ROOT_USER/MINIO_ROOT_PASSWORD 读取，不落盘
"""
import os, sys, json, csv, re, argparse, datetime, subprocess, time

DATA_ROOT = "/data/minio/data"
ENDPOINT = "127.0.0.1:9000"
RETENTION_DAYS = 90          # 90 天内 manifest 引用的 blob 不允许删除（硬约束）
GRACE_DAYS = 7
STRIDE = 1048608             # 1MiB payload + 32B header
GB = 1073741824.0
BLOB_KEY_RE = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{62}$")

def check_bucket(bucket):
    if not bucket.startswith("ugs-"):
        print(f"拒绝: bucket {bucket!r} 不匹配 ugs-* 前缀，本工具只清理 ugs-* 仓库")
        sys.exit(2)
    fs_root = os.path.join(DATA_ROOT, bucket)
    if not os.path.isdir(fs_root):
        print(f"拒绝: {fs_root} 不存在")
        sys.exit(2)
    return fs_root

def fmt_ts(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

def read_object_payload(objdir):
    """读 standalone MinIO 对象内容并剥掉每 1MiB 的 32 字节头"""
    parts = []
    for sub in os.listdir(objdir):
        p = os.path.join(objdir, sub)
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                if f.startswith("part."):
                    parts.append(os.path.join(p, f))
    raw = b"".join(open(fp, "rb").read() for fp in parts)
    return b"".join(raw[i + 32:i + STRIDE] for i in range(0, len(raw), STRIDE))

def parse_manifest_hashes(objdir):
    j = json.loads(read_object_payload(objdir))
    return set(v["hash"] for v in j.get("files", {}).values()
               if isinstance(v, dict) and "hash" in v)

def scan_manifests(fs_root):
    out = []
    for n in os.listdir(fs_root):
        if n.startswith("manifest_") and n.endswith(".json"):
            out.append((n, os.stat(os.path.join(fs_root, n)).st_mtime))
    out.sort(key=lambda x: x[1])
    return out

def scan_blobs(fs_root):
    for pre in os.listdir(fs_root):
        pd = os.path.join(fs_root, pre)
        if not (os.path.isdir(pd) and len(pre) == 2):
            continue
        for h62 in os.listdir(pd):
            od = os.path.join(pd, h62)
            if not os.path.isdir(od):
                continue
            size, mt = 0, 0.0
            for sub in os.listdir(od):
                sp = os.path.join(od, sub)
                if os.path.isdir(sp):
                    for f in os.listdir(sp):
                        st = os.stat(os.path.join(sp, f))
                        size += st.st_size
                        mt = max(mt, st.st_mtime)
            yield pre + h62, size, mt

def build_recent_refset(fs_root, manifests, cutoff):
    """解析 cutoff 之后的全部 manifest，返回被引用的 hash 集合。有解析失败就中止。"""
    recent = [m for m in manifests if m[1] >= cutoff]
    ref, bad = set(), []
    for i, (n, mt) in enumerate(recent):
        try:
            ref |= parse_manifest_hashes(os.path.join(fs_root, n))
        except Exception as e:
            bad.append((n, str(e)))
        if (i + 1) % 500 == 0:
            print(f"  parsed recent {i+1}/{len(recent)}", flush=True)
    if bad:
        print(f"!! {len(bad)} 个近期 manifest 解析失败，为安全起见中止（它们引用的 blob 无法计入保护集）:")
        for n, e in bad[:10]:
            print("   ", n, e)
        sys.exit(2)
    return ref, len(recent)

def dry_run(fs_root, bucket, work_dir):
    os.makedirs(work_dir, exist_ok=True)
    now = datetime.datetime.now().timestamp()
    cutoff, grace = now - RETENTION_DAYS * 86400, now - GRACE_DAYS * 86400
    print(f"[dry-run] bucket={bucket} retention={RETENTION_DAYS}d cutoff={fmt_ts(cutoff)} grace={GRACE_DAYS}d")

    manifests = scan_manifests(fs_root)
    ref, n_recent = build_recent_refset(fs_root, manifests, cutoff)
    # 旧 manifest 的引用集仅用于报告（区分纯孤儿 vs 仅旧引用）
    ref_old, bad_old = set(), 0
    for n, mt in manifests:
        if mt < cutoff:
            try:
                ref_old |= parse_manifest_hashes(os.path.join(fs_root, n))
            except Exception:
                bad_old += 1
    print(f"[dry-run] manifests={len(manifests)} recent={n_recent} ref={len(ref)} "
          f"old_only={len(ref_old - ref)} old_parse_failed={bad_old}(仅影响报告细分)")

    n_blob = sz_blob = n_cand = sz_cand = n_grace = sz_grace = n_orphan = sz_orphan = 0
    list_path = os.path.join(work_dir, "delete_list.csv")
    with open(list_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hash", "size_bytes", "mtime", "object_name"])
        for h, size, mt in scan_blobs(fs_root):
            n_blob += 1; sz_blob += size
            if h in ref:
                continue
            if mt >= grace:
                n_grace += 1; sz_grace += size; continue
            n_cand += 1; sz_cand += size
            if h not in ref_old:
                n_orphan += 1; sz_orphan += size
            w.writerow([h, size, int(mt), f"{h[:2]}/{h[2:]}"])
    summary = f"""{bucket} GC dry-run  {datetime.datetime.now():%Y-%m-%d %H:%M:%S}
============================================================
策略: 保留全部 manifest；删除未被最近 {RETENTION_DAYS} 天 manifest 引用的 blob
cutoff={fmt_ts(cutoff)}  grace={GRACE_DAYS}d
manifests={len(manifests)} recent={n_recent} 引用hash={len(ref)}
blob 总数={n_blob} ({sz_blob/GB:.1f} GB 逻辑)
------------------------------------------------------------
待删 blob={n_cand} ({sz_cand/GB:.1f} GB 逻辑, 物理约 {sz_cand/GB*0.417:.0f} GB)
  其中纯孤儿={n_orphan} ({sz_orphan/GB:.1f} GB)
  仅旧manifest引用={n_cand - n_orphan} (删除后 >{RETENTION_DAYS}d 旧 manifest 悬空, 预期行为)
grace 跳过={n_grace}  保留={n_blob - n_cand - n_grace}
清单: {list_path}
"""
    open(os.path.join(work_dir, "summary.txt"), "w").write(summary)
    print(summary)

def get_creds():
    out = subprocess.check_output(["docker", "inspect", "minio", "--format", "{{json .Config.Env}}"])
    kv = dict(e.split("=", 1) for e in json.loads(out))
    return kv["MINIO_ROOT_USER"], kv["MINIO_ROOT_PASSWORD"]

def execute(fs_root, bucket, work_dir, limit):
    from minio import Minio
    from minio.deleteobjects import DeleteObject
    list_path = os.path.join(work_dir, "delete_list.csv")
    done_path = os.path.join(work_dir, "deleted.log")
    if not os.path.exists(list_path):
        print("delete_list.csv 不存在，先跑 dry-run"); sys.exit(1)

    # 执行前重校验：重新解析近期 manifest，dry-run 后新被引用的 blob 从清单剔除
    now = datetime.datetime.now().timestamp()
    cutoff = now - RETENTION_DAYS * 86400
    print("[execute] 重新解析近期 manifest 做执行前校验 ...")
    ref, n_recent = build_recent_refset(fs_root, scan_manifests(fs_root), cutoff)
    print(f"[execute] 保护集 {len(ref)} hash（来自 {n_recent} 个近期 manifest）")

    done = set()
    if os.path.exists(done_path):
        done = set(l.strip() for l in open(done_path) if l.strip())

    todo, skipped_referenced, skipped_badkey = [], 0, 0
    for row in csv.DictReader(open(list_path)):
        h, key = row["hash"], row["object_name"]
        if h in done:
            continue
        if h in ref:                      # 90 天内 manifest 引用的 blob 不允许删除
            skipped_referenced += 1; continue
        if not BLOB_KEY_RE.match(key):    # 只删 blob 形态的 key，永不删 manifest
            skipped_badkey += 1; continue
        todo.append((h, key))
    if limit:
        todo = todo[:limit]
    print(f"[execute] 待删 {len(todo)}（已完成 {len(done)}，重校验剔除 {skipped_referenced}，非法key剔除 {skipped_badkey}）")
    if not todo:
        return

    user, pw = get_creds()
    client = Minio(ENDPOINT, access_key=user, secret_key=pw, secure=False)
    print("[execute] versioning:", client.get_bucket_versioning(bucket))

    log = open(done_path, "a")
    t0, B = time.time(), 1000
    for i in range(0, len(todo), B):
        batch = todo[i:i + B]
        errs = list(client.remove_objects(bucket, [DeleteObject(k) for _, k in batch]))
        for e in errs:
            print("  DELETE-ERROR:", e)
        for h, _ in batch:
            log.write(h + "\n")
        log.flush()
        if (i // B) % 20 == 0 or i + B >= len(todo):
            print(f"  progress {min(i+B, len(todo))}/{len(todo)} ({time.time()-t0:.0f}s)", flush=True)
    log.close()
    print(f"[execute] 完成，用时 {time.time()-t0:.0f}s")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dry-run", "execute"])
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--work-dir", default=None)
    a = ap.parse_args()
    fs_root = check_bucket(a.bucket)
    work_dir = a.work_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "runs",
        f"{a.bucket}-{datetime.datetime.now():%Y%m%d}")
    os.makedirs(work_dir, exist_ok=True)
    print(f"work_dir = {work_dir}")
    if a.mode == "dry-run":
        dry_run(fs_root, a.bucket, work_dir)
    else:
        execute(fs_root, a.bucket, work_dir, a.limit)
