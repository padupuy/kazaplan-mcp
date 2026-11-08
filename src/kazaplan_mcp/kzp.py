#!/usr/bin/env python3
"""Lecture / écriture des fichiers Kazaplan .kzp (conteneur "WPRJ", ex-Wanaplan/Obsidian).

Format (tiré du bundle Kazaplan, classe "ObsidianProjectFile", entiers big-endian) :

  off  taille  champ
   0    4      magic "WPRJ"
   4    2      version (uint16) = 1
   6   10      type ASCII, complété par des espaces ("WANAPLAN  ")
  16    1      metadataFormat   (0 = JSON brut, 1 = JSON + deflate brut niveau 6)
  17    4      metadataOffset   (= 51)
  21    4      metadataLength
  25    1      projectFormat
  26    4      projectOffset    (= 51 + metadataLength)
  30    4      projectLength
  34    1      blobIndexFormat
  35    4      blobIndexOffset  (= projectOffset + projectLength)
  39    4      blobIndexLength
  43    4      blobsOffset      (= blobIndexOffset + blobIndexLength)
  47    4      blobsLength
  51    ...    metadata | project | blobIndex | blobs

Contrôle à l'ouverture : taille du fichier == 51 + metadataLength + projectLength
+ blobIndexLength + blobsLength.

blobIndex = {nom: {offset, length, mime, metadata}}, offsets relatifs à blobsOffset.

Usage :
  python3 -m kazaplan_mcp.kzp unpack plan.kzp dossier/     -> metadata.json, project.json, blobs/
  python3 -m kazaplan_mcp.kzp pack   dossier/ nouveau.kzp  -> reconstruit le .kzp
  python3 -m kazaplan_mcp.kzp check  plan.kzp              -> affiche l'en-tête et vérifie les tailles
"""

import json
import struct
import sys
import zlib
from pathlib import Path

HEADER_SIZE = 51
FMT_JSON, FMT_JSON_DEFLATE = 0, 1


def _json_bytes(obj) -> bytes:
    # Équivalent de JSON.stringify (compact, UTF-8).
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def encode(obj, fmt: int) -> bytes:
    raw = _json_bytes(obj)
    if fmt == FMT_JSON:
        return raw
    c = zlib.compressobj(6, zlib.DEFLATED, -15)  # deflateRawSync({level: 6})
    return c.compress(raw) + c.flush()


def decode(buf: bytes, fmt: int):
    if fmt == FMT_JSON_DEFLATE:
        buf = zlib.decompress(buf, -15)
    return json.loads(buf.decode("utf-8"))


def read_header(data: bytes) -> dict:
    if len(data) < HEADER_SIZE or data[:4] != b"WPRJ":
        raise ValueError("Pas un fichier WPRJ")
    (version,) = struct.unpack_from(">H", data, 4)
    h = {
        "magic": data[:4].decode(),
        "version": version,
        "type": data[6:16].decode("ascii").strip(),
    }
    h["metadataFormat"], h["metadataOffset"], h["metadataLength"] = struct.unpack_from(">BII", data, 16)
    h["projectFormat"], h["projectOffset"], h["projectLength"] = struct.unpack_from(">BII", data, 25)
    h["blobIndexFormat"], h["blobIndexOffset"], h["blobIndexLength"] = struct.unpack_from(">BII", data, 34)
    h["blobsOffset"], h["blobsLength"] = struct.unpack_from(">II", data, 43)
    return h


def load(data: bytes):
    h = read_header(data)
    expected = (
        HEADER_SIZE + h["metadataLength"] + h["projectLength"] + h["blobIndexLength"] + h["blobsLength"]
    )
    if len(data) != expected:
        raise ValueError(f"Taille incohérente : {len(data)} au lieu de {expected}")
    sl = lambda off, length: data[off : off + length]
    metadata = decode(sl(h["metadataOffset"], h["metadataLength"]), h["metadataFormat"])
    project = decode(sl(h["projectOffset"], h["projectLength"]), h["projectFormat"])
    index = decode(sl(h["blobIndexOffset"], h["blobIndexLength"]), h["blobIndexFormat"])
    blobs = {}
    for name, rec in index.items():
        start = h["blobsOffset"] + rec["offset"]
        blobs[name] = {
            "data": data[start : start + rec["length"]],
            "mime": rec.get("mime", "application/octet-stream"),
            "metadata": rec.get("metadata", {}),
        }
    return h, metadata, project, blobs


def dump(metadata, project, blobs=None, type_="WANAPLAN", version=1, fmt=FMT_JSON_DEFLATE) -> bytes:
    blobs = blobs or {}
    meta_b = encode(metadata, fmt)
    proj_b = encode(project, fmt)
    index, chunks, off = {}, [], 0
    for name, b in blobs.items():
        index[name] = {
            "offset": off,
            "length": len(b["data"]),
            "mime": b.get("mime", "application/octet-stream"),
            "metadata": b.get("metadata", {}),
        }
        chunks.append(b["data"])
        off += len(b["data"])
    idx_b = encode(index, fmt)
    blobs_b = b"".join(chunks)

    hdr = bytearray(HEADER_SIZE)
    hdr[0:4] = b"WPRJ"
    struct.pack_into(">H", hdr, 4, version)
    hdr[6:16] = type_.upper()[:10].ljust(10).encode("ascii")
    p_off = HEADER_SIZE + len(meta_b)
    i_off = p_off + len(proj_b)
    b_off = i_off + len(idx_b)
    struct.pack_into(">BII", hdr, 16, fmt, HEADER_SIZE, len(meta_b))
    struct.pack_into(">BII", hdr, 25, fmt, p_off, len(proj_b))
    struct.pack_into(">BII", hdr, 34, fmt, i_off, len(idx_b))
    struct.pack_into(">II", hdr, 43, b_off, len(blobs_b))
    return bytes(hdr) + meta_b + proj_b + idx_b + blobs_b


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "check":
        data = Path(sys.argv[2]).read_bytes()
        print(json.dumps(read_header(data), indent=2))
        load(data)
        print("OK : tailles cohérentes, blocs décodés.")
    elif cmd == "unpack":
        src, out = Path(sys.argv[2]), Path(sys.argv[3])
        out.mkdir(parents=True, exist_ok=True)
        h, metadata, project, blobs = load(src.read_bytes())
        (out / "header.json").write_text(json.dumps(h, indent=2), encoding="utf-8")
        dump = lambda obj: json.dumps(obj, indent=2, ensure_ascii=False)
        (out / "metadata.json").write_text(dump(metadata), encoding="utf-8")
        (out / "project.json").write_text(dump(project), encoding="utf-8")
        if blobs:
            (out / "blobs").mkdir(exist_ok=True)
            meta = {}
            for name, b in blobs.items():
                safe = name.replace("/", "_")
                (out / "blobs" / safe).write_bytes(b["data"])
                meta[name] = {
                    "file": safe,
                    "mime": b["mime"],
                    "metadata": b["metadata"],
                }
            (out / "blobs.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"Décompressé dans {out} ({len(blobs)} blob(s))")
    elif cmd == "pack":
        src, dst = Path(sys.argv[2]), Path(sys.argv[3])
        header = src / "header.json"
        h = json.loads(header.read_text(encoding="utf-8")) if header.exists() else {}
        metadata = json.loads((src / "metadata.json").read_text(encoding="utf-8"))
        project = json.loads((src / "project.json").read_text(encoding="utf-8"))
        blobs = {}
        if (src / "blobs.json").exists():
            for name, m in json.loads((src / "blobs.json").read_text(encoding="utf-8")).items():
                blobs[name] = {
                    "data": (src / "blobs" / m["file"]).read_bytes(),
                    "mime": m["mime"],
                    "metadata": m["metadata"],
                }
        data = dump(
            metadata,
            project,
            blobs,
            type_=h.get("type", "WANAPLAN"),
            version=h.get("version", 1),
        )
        dst.write_bytes(data)
        load(data)  # auto-vérification
        print(f"Écrit {dst} ({len(data)} octets)")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
