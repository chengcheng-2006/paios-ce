#!/usr/bin/env python3
"""Local equivalent of .github/workflows/package.yml — build wheel/sdist, inspect metadata, fresh-install smoke.

Usage: python tools/package_local_validate.py [--outdir DIR]
Requires: build package (or pip wheel fallback). Offline; never uploads.
"""
import argparse
import os
import subprocess
import sys
import zipfile
import tarfile


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="dist")
    args = ap.parse_args(argv[1:])
    os.makedirs(args.outdir, exist_ok=True)

    # 1. build
    r = subprocess.run([sys.executable, "-m", "build", "--outdir", args.outdir],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # fallback: pip wheel
        r2 = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", args.outdir, "."],
                            capture_output=True, text=True)
        if r2.returncode != 0:
            print("PACKAGE_BUILD_FAILED")
            print(r2.stdout[-500:])
            print(r2.stderr[-500:])
            return 1

    artifacts = sorted(os.listdir(args.outdir))
    wheels = [a for a in artifacts if a.endswith(".whl")]
    sdists = [a for a in artifacts if a.endswith(".tar.gz")]
    print(f"BUILD_OK wheels={wheels} sdists={sdists}")

    # 2. inspect wheel metadata
    if wheels:
        wp = os.path.join(args.outdir, wheels[0])
        with zipfile.ZipFile(wp) as z:
            meta = [n for n in z.namelist() if n.endswith("METADATA")][0]
            text = z.read(meta).decode("utf-8", errors="replace")
        checks = {
            "Apache-2.0 license expr": "Apache-2.0" in text,
            "entry point": "paios_ce.cli.main:main" in text or any(n.endswith("entry_points.txt") for n in (lambda zz: zz.namelist())(zipfile.ZipFile(wp))),
            "requires-python>=3.11": ">=3.11" in text,
        }
        for k, v in checks.items():
            print(f"  wheel {k}: {'PASS' if v else 'FAIL'}")
        if not all(checks.values()):
            return 1

    # 3. sdist sanity
    if sdists:
        sp = os.path.join(args.outdir, sdists[0])
        with tarfile.open(sp, "r:gz") as t:
            names = t.getnames()
        if not any(n.endswith("permissions/policy.py") for n in names):
            print("SDIST_MISSING_POLICY")
            return 1
        print("  sdist policy.py present: PASS")

    # 4. fresh install smoke into temp venv
    import tempfile
    tmp = tempfile.mkdtemp(prefix="pkg_smoke_")
    venv = os.path.join(tmp, "venv")
    r = subprocess.run([sys.executable, "-m", "venv", venv], capture_output=True, text=True)
    if r.returncode != 0:
        print("SMOKE_VENV_CREATE_FAILED")
        return 1
    pip = os.path.join(venv, "Scripts", "pip.exe") if os.name == "nt" else os.path.join(venv, "bin", "pip")
    if wheels:
        r = subprocess.run([pip, "install", os.path.join(args.outdir, wheels[0])], capture_output=True, text=True)
        if r.returncode != 0:
            print("SMOKE_INSTALL_FAILED")
            print(r.stdout[-500:]); print(r.stderr[-500:])
            return 1
    exe = os.path.join(venv, "Scripts", "paios-ce.exe") if os.name == "nt" else os.path.join(venv, "bin", "paios-ce")
    if os.path.exists(exe):
        for cmd in (["health"], ["--help"]):
            r = subprocess.run([exe] + cmd, capture_output=True, text=True)
            print(f"  smoke {' '.join(cmd)}: {'PASS' if r.returncode == 0 else 'FAIL'}")
            if r.returncode != 0:
                return 1
    print("PACKAGE_LOCAL_VALIDATE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
