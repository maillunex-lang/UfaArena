"""Content release CLI.

    python -m app.content.admin publish  <package.zip> [--channel dev] [--notes "..."]
    python -m app.content.admin build    <src_dir> <out.zip>       # build a package from a folder
    python -m app.content.admin list     [--channel dev]           # manifest history
    python -m app.content.admin activate <version> [--channel dev] # rollback / roll-forward
    python -m app.content.admin remove   <package_id> [--channel dev]
    python -m app.content.admin kill     on|off [--channel dev]
    python -m app.content.admin promote  <from> <to>               # e.g. dev beta
    python -m app.content.admin min-client <x.y.z> [--channel dev]
    python -m app.content.admin keygen                              # create signing key (beta/prod)
    python -m app.content.admin set-vip  <uralia_id> <level>       # test helper for VIP speeds

In Docker: docker compose exec api python -m app.content.admin list
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.db import get_engine, init_engine
from . import pack, service


def build_from_dir(src: Path) -> bytes:
    meta = json.loads((src / "package.json").read_text(encoding="utf-8"))
    files = {}
    for f in sorted(src.rglob("*")):
        if f.is_file() and f.name != "package.json":
            files[f.relative_to(src).as_posix()] = f.read_bytes()
    data = pack.build(meta, files)
    pack.validate(data)
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="content-admin")
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--channel", default="dev")
    ap.add_argument("--notes", default="")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        data = build_from_dir(Path(a.args[0]))
        Path(a.args[1]).write_bytes(data)
        info = pack.validate(data)
        print(f"built {info.package_id} v{info.version}: {len(data)} bytes, {len(info.files)} files")
        return 0
    if a.cmd == "keygen":
        from ..core import signing
        print(signing.public_key_pem())
        return 0
    init_engine()
    with Session(get_engine()) as db:
        try:
            if a.cmd == "publish":
                data = Path(a.args[0]).read_bytes() if a.args[0].endswith(".zip") else build_from_dir(Path(a.args[0]))
                m = service.publish(db, data, a.channel, notes=a.notes)
                print(f"published -> {a.channel} manifest v{m.version}")
            elif a.cmd == "list":
                for m in service.history(db, a.channel):
                    flag = "*" if m.is_active else " "
                    pk = ", ".join(f"{p['package_id']}@{p['version']}" for p in m.packages)
                    ks = " KILL" if m.kill_switch else ""
                    print(f"{flag} v{m.version:<4} min={m.minimum_client_version:<8}{ks} [{pk}] {m.notes}")
            elif a.cmd == "activate":
                m = service.activate(db, a.channel, int(a.args[0]))
                print(f"activated {a.channel} v{m.version}")
            elif a.cmd == "remove":
                m = service.remove(db, a.args[0], a.channel)
                print(f"removed -> v{m.version}")
            elif a.cmd == "kill":
                service.kill_switch(db, a.channel, a.args[0] == "on")
                print(f"kill switch {a.args[0]} for {a.channel}")
            elif a.cmd == "promote":
                m = service.promote(db, a.args[0], a.args[1])
                print(f"promoted {a.args[0]} -> {a.args[1]} v{m.version}")
            elif a.cmd == "min-client":
                m = service.set_min_client(db, a.channel, a.args[0])
                print(f"min client {a.args[0]} -> v{m.version}")
            elif a.cmd == "set-vip":
                from sqlalchemy import select
                from ..models import PlayerProfile
                p = db.scalar(select(PlayerProfile).where(PlayerProfile.uralia_id == a.args[0]))
                if p is None:
                    raise service.ReleaseError("player not found")
                p.vip_level = int(a.args[1])
                db.commit()
                print(f"{a.args[0]} vip={p.vip_level}")
            else:
                ap.print_help()
                return 2
        except (service.ReleaseError, pack.PackageError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
