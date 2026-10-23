"""Reproducibly chunk a complete source-only SQLite into CI artifact-safe pieces.

Chunks are not production deployment. They must be reassembled and validated
against exact original index/official-source checksums on the private host.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

BLOCK=1024*1024
CHUNK_BYTES=750_000_000

def filehash(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(BLOCK),b""):
            digest.update(chunk)
    return digest.hexdigest()

def pack(index_path,index_manifest,out_dir,chunk_bytes=CHUNK_BYTES):
    source=Path(index_path);manifest=json.loads(Path(index_manifest).read_text())
    out=Path(out_dir)
    if not source.is_file() or manifest.get("index_bytes")!=source.stat().st_size:
        raise ValueError("Source index missing or size differs from ingestion manifest")
    expected=manifest.get("index_sha256")
    if not expected or len(expected)!=64 or filehash(source)!=expected:
        raise ValueError("Source SQLite SHA256 disagrees with ingestion manifest")
    if out.exists() and list(out.iterdir()):
        raise FileExistsError("Refusing to overwrite existing chunk bundle")
    out.mkdir(parents=True,exist_ok=True)
    if chunk_bytes<1024:raise ValueError("Invalid chunk byte limit")
    compressed=out/"source-index.sqlite.gz"
    entries=[]
    try:
        with source.open("rb") as stream,compressed.open("wb") as destination:
            with gzip.GzipFile(fileobj=destination,mode="wb",filename="",mtime=0,compresslevel=1) as gz:
                shutil.copyfileobj(stream,gz,length=BLOCK)
        compressed_sha=filehash(compressed)
        with compressed.open("rb") as stream:
            number=0
            while True:
                path=out/f"source-index.part-{number:03d}"
                digest=hashlib.sha256()
                n=0
                with path.open("wb") as dst:
                    while n<chunk_bytes:
                        block=stream.read(min(BLOCK,chunk_bytes-n))
                        if not block:break
                        digest.update(block);dst.write(block);n+=len(block)
                if not n:
                    path.unlink()
                    break
                entries.append(dict(file=path.name,bytes=n,sha256=digest.hexdigest()))
                number+=1
        if sum(x["bytes"] for x in entries)!=compressed.stat().st_size:
            raise AssertionError("Chunk count does not reconcile")
        result={
            "format":"Lane B immutable indexed SQLite gzip chunks/v1",
            "source":manifest.get("source"),"source_url":manifest.get("source_url"),
            "source_archive_sha256":manifest.get("archive_sha256"),
            "indexed_rows":manifest.get("indexed_rows"),
            "rejected_rows":manifest.get("rejected_rows"),
            "sqlite_bytes":source.stat().st_size,"sqlite_sha256":expected,
            "compressed_bytes":compressed.stat().st_size,
            "compressed_sha256":compressed_sha,
            "chunk_bytes_limit":chunk_bytes,
            "chunks":entries,"deployment_state":"NOT_DEPLOYED",
            "notice":"Short-lived source-only staging. Verify original official source & signed-off private hosting before release"
        }
        (out/"chunk-manifest.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        compressed.unlink()
        return result
    except Exception:
        for p in out.glob("source-index.part-*"):p.unlink()
        compressed.unlink(missing_ok=True)
        raise

def restore(manifest_path,parts_dir,output_file):
    meta=json.loads(Path(manifest_path).read_text())
    if meta.get("format")!="Lane B immutable indexed SQLite gzip chunks/v1":
        raise ValueError("Unrecognized source index staging format")
    out=Path(output_file)
    if out.exists():raise FileExistsError("Refusing to overwrite index")
    parts=Path(parts_dir)
    chunks=meta.get("chunks",[])
    if not chunks or not isinstance(chunks,list):raise ValueError("No staged source parts")
    expected=[f"source-index.part-{i:03d}" for i in range(len(chunks))]
    if [c.get("file") for c in chunks]!=expected:
        raise ValueError("Incomplete or out-of-order source manifest")
    if sum(c.get("bytes",0) for c in chunks)!=meta.get("compressed_bytes"):
        raise ValueError("Compressed size mismatch in manifest")
    if [p.name for p in parts.glob("source-index.part-*") if p.is_file()] and sorted(
            p.name for p in parts.glob("source-index.part-*") if p.is_file())!=expected:
        raise ValueError("Part-directory includes missing or unexpected source chunks")
    out.parent.mkdir(parents=True,exist_ok=True)
    tmpgz=out.with_name(out.name+".transit.gz")
    dig=hashlib.sha256()
    try:
        with tmpgz.open("wb") as aggregate:
            for chunk in chunks:
                path=parts/chunk["file"]
                if not path.is_file() or path.stat().st_size!=chunk["bytes"] or filehash(path)!=chunk["sha256"]:
                    raise ValueError("Missing/corrupted source-index part "+chunk["file"])
                with path.open("rb") as source:
                    for piece in iter(lambda:source.read(BLOCK),b""):
                        dig.update(piece);aggregate.write(piece)
        if dig.hexdigest()!=meta["compressed_sha256"]:
            raise ValueError("Reassembled compressed data digest mismatch")
        with gzip.open(tmpgz,"rb") as compressed,out.open("wb") as restored:
            shutil.copyfileobj(compressed,restored,length=BLOCK)
        if out.stat().st_size!=meta["sqlite_bytes"] or filehash(out)!=meta["sqlite_sha256"]:
            raise ValueError("Reassembled source index mismatches original SQLite")
        return dict(index_file=str(out),sqlite_bytes=out.stat().st_size,
                    sqlite_sha256=meta["sqlite_sha256"],
                    source=meta["source"],indexed_rows=meta["indexed_rows"],
                    deployment_state="NOT_DEPLOYED")
    except Exception:
        out.unlink(missing_ok=True)
        raise
    finally:
        tmpgz.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="mode",required=True)
    a=sub.add_parser("pack")
    a.add_argument("--index",required=True);a.add_argument("--manifest",required=True)
    a.add_argument("--out",required=True);a.add_argument("--chunk-bytes",type=int,default=CHUNK_BYTES)
    b=sub.add_parser("restore")
    b.add_argument("--chunks-manifest",required=True);b.add_argument("--parts",required=True)
    b.add_argument("--output",required=True)
    x=p.parse_args()
    result=(pack(x.index,x.manifest,x.out,x.chunk_bytes) if x.mode=="pack" else
            restore(x.chunks_manifest,x.parts,x.output))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
