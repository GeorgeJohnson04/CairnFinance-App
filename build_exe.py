"""Build the Cairn test .exe with PyInstaller.

Run:  python build_exe.py
Output:  dist\Cairn.exe  (single file, double-click to run)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SEP = ";" if os.name == "nt" else ":"


def main():
    # Build in a LOCAL temp dir (not OneDrive) so the sync client / AV can't
    # lock PyInstaller's scratch files mid-build, then copy the exe back.
    work = os.path.join(tempfile.gettempdir(), "cairn_build")
    dist = os.path.join(work, "dist")
    build = os.path.join(work, "build")
    for d in (build, dist):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    # bundle templates + static under "app/..." inside the exe
    add_data = [
        (os.path.join(ROOT, "app", "templates"), "app/templates"),
        (os.path.join(ROOT, "app", "static"), "app/static"),
    ]
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "Cairn",
        "--onefile",
        "--noconfirm",
        "--console",  # keep a console so testers see the local URL
        "--icon", "NONE",
        "--distpath", dist,
        "--workpath", build,
        "--specpath", work,
        # argon2 / cffi backends sometimes need explicit collection
        "--collect-submodules", "argon2",
        "--hidden-import", "argon2",
    ]
    for src, dest in add_data:
        cmd += ["--add-data", f"{src}{SEP}{dest}"]
    cmd.append(os.path.join(ROOT, "launcher.py"))

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=work)
    if result.returncode != 0:
        sys.exit(result.returncode)

    built = os.path.join(dist, "Cairn.exe")
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    exe = os.path.join(out_dir, "Cairn.exe")
    shutil.copy2(built, exe)

    size = os.path.getsize(exe) / (1024 * 1024)
    print(f"\nBuild complete.\n  {exe}  ({size:.1f} MB)")
    print("  Double-click it (or run it) to launch the app in your browser.")


if __name__ == "__main__":
    main()
