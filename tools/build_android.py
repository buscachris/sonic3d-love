#!/usr/bin/env python3
"""Build the ARM64 Sonic 3D Blast LÖVE port as a standalone Android APK."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "org.sonic3dlove.game"
EXE_SHA256 = "2cb33a8629e1de8c4f9688123a35f6c0bffb5ba53f05f75a3e2aae8c1e3a25dd"
ANDROID = "{http://schemas.android.com/apk/res/android}"
ET.register_namespace("android", ANDROID[1:-1])
DOWNLOADS = {
    "love-11.5-android.apk": (
        "https://github.com/love2d/love/releases/download/11.5/love-11.5-android.apk",
        "10a804f84da2cbe1b9c65736bcae0572accc1c7ded46b132c2de73d7e35b1f00"),
    "apktool_2.9.3.jar": (
        "https://github.com/iBotPeaches/Apktool/releases/download/v2.9.3/apktool_2.9.3.jar",
        "7956eb04194300ce0d0a84ad18771eebc94b89fb8d1ddcce8ea4c056818646f4"),
}
# The translated engine uses __int128, so the Android build requires ARM64.
ABIS = {"arm64-v8a": "aarch64-linux-android21"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True, **kwargs)


def write_icons(stage):
    """Use the same Sonic artwork for legacy and Android adaptive launchers."""
    art = stage / "res/drawable-nodpi/sonic_art.png"
    art.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "game/icons/sonic.png", art)
    resources = {
        "values/sonic_icon.xml": '<resources><color name="sonic_icon_background">#FFE7A5</color></resources>',
        "mipmap-anydpi/sonic_icon.xml": '''<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
  <item android:drawable="@color/sonic_icon_background" />
  <item><bitmap android:src="@drawable/sonic_art" android:gravity="fill" android:filter="true" /></item>
</layer-list>''',
        "drawable/sonic_foreground.xml": '''<inset xmlns:android="http://schemas.android.com/apk/res/android"
    android:inset="8%" android:drawable="@drawable/sonic_art" />''',
        "mipmap-anydpi-v26/sonic_icon.xml": '''<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
  <background android:drawable="@color/sonic_icon_background" />
  <foreground android:drawable="@drawable/sonic_foreground" />
</adaptive-icon>''',
    }
    for name, text in resources.items():
        path = stage / "res" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n")


def copy_game(stage):
    """Embed game code and a hashed manifest for the native engine's stdio data."""
    source = ROOT / "source"
    if digest(source / "PCSONIC.EXE") != EXE_SHA256:
        raise RuntimeError("PCSONIC.EXE does not match the statically recompiled engine")
    for required in (source / "PCSONIC/CDDATA", source / "Music", ROOT / "game/movies"):
        if not required.is_dir() or not any(required.iterdir()):
            raise RuntimeError(f"Required game data is missing: {required}")

    assets = stage / "assets"
    files = sorted((ROOT / "game").glob("*.lua"))
    files += sorted(p for p in (ROOT / "game/movies").rglob("*") if p.is_file())
    files += [ROOT / "game/icons/sonic.png"]
    hashes = {}
    for path in files:
        relative = path.relative_to(ROOT / "game").as_posix()
        destination = assets / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        hashes[relative] = digest(destination)
    # Include all original PC game resources, music and executable. Never include
    # the developer's saves, native desktop libraries, generated C or build files.
    originals = [source / "PCSONIC.EXE"]
    for directory in ("PCSONIC", "Music"):
        originals += sorted(p for p in (source / directory).rglob("*") if p.is_file())
    entries = []
    for path in originals:
        relative = path.relative_to(source).as_posix()
        destination = assets / "original" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        sha = digest(destination)
        entries.append({"path": relative, "size": destination.stat().st_size, "sha256": sha})
        hashes["original/" + relative] = sha
    version = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    byte_count = sum(entry["size"] for entry in entries)
    lines = [f'return {{version = "{version}", bytes = {byte_count}, files = {{']
    for entry in entries:
        lines.append('  {path = %s, size = %d, sha256 = "%s"},' % (
            json.dumps(entry["path"], ensure_ascii=False), entry["size"], entry["sha256"]))
    lines.append("}}")
    manifest = assets / "android-assets.lua"
    manifest.write_text("\n".join(lines) + "\n")
    hashes["android-assets.lua"] = digest(manifest)
    return hashes, {"version": version, "bytes": byte_count, "files": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=Path(os.environ.get(
        "ANDROID_SDK_ROOT", str(Path.home() / "Android/Sdk"))))
    parser.add_argument("--ndk", type=Path, default=os.environ.get("ANDROID_NDK_HOME"))
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--version-code", type=int, default=1)
    parser.add_argument("--version-name", default="0.1")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.version_code < 1 or not re.fullmatch(r"[A-Za-z0-9.+-]+", args.version_name):
        parser.error("Use a positive version code and a simple version name")
    build_tools = sorted((args.sdk / "build-tools").glob("*"),
                         key=lambda p: [int(n) for n in re.findall(r"\d+", p.name)])
    if not build_tools:
        parser.error("Android SDK build-tools are required; pass --sdk")
    sdk_bin = build_tools[-1]
    ndks = sorted((args.sdk / "ndk").glob("*")) + sorted(
        (Path.home() / "Unity/Editors").glob("*/Editor/Data/PlaybackEngines/AndroidPlayer/NDK"))
    ndk = args.ndk or (ndks[-1] if ndks else None)
    if not ndk:
        parser.error("An Android NDK is required; pass --ndk")
    compiler_bin = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    for tool in ("java", "keytool", "make", "curl"):
        if not shutil.which(tool):
            parser.error(f"Missing build tool: {tool}")
    for path in [sdk_bin / t for t in ("aapt", "apksigner", "zipalign")] + [
            compiler_bin / (target + "-clang") for target in ABIS.values()]:
        if not path.is_file():
            parser.error(f"Missing Android tool: {path}")

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    output = (args.output_dir or ROOT / "builds/android" / stamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cache = ROOT / "build/android-tools"
    cache.mkdir(parents=True, exist_ok=True)
    for name, (url, sha) in DOWNLOADS.items():
        path = cache / name
        if not path.exists():
            part = path.with_suffix(path.suffix + ".part")
            run("curl", "--fail", "--location", "--retry", "2", "--output", part, url)
            if digest(part) != sha:
                raise RuntimeError(f"Download checksum mismatch: {name}")
            part.replace(path)
        if digest(path) != sha:
            raise RuntimeError(f"Cached download checksum mismatch: {name}")

    stage = output / "package"
    framework = cache / "framework"
    run("java", "-jar", cache / "apktool_2.9.3.jar", "d", "--no-src",
        "--frame-path", framework, "-o", stage, cache / "love-11.5-android.apk")
    for directory in (stage / "lib").iterdir():
        if directory.is_dir() and directory.name not in ABIS:
            shutil.rmtree(directory)
    for abi, target in ABIS.items():
        build = ROOT / "build/android" / abi
        with (output / (abi + "-build.log")).open("w") as log:
            run("make", f"-j{args.jobs}", f"BUILD={build}",
                f"CC={compiler_bin / (target + '-clang')}",
                "LDFLAGS=-Wl,-soname,libsonic3d.so,-z,max-page-size=16384",
                build / "libsonic3d.so",
                stdout=log, stderr=subprocess.STDOUT)
        library = stage / "lib" / abi / "libsonic3d.so"
        shutil.copy2(build / "libsonic3d.so", library)
        run(compiler_bin / "llvm-strip", "--strip-unneeded", library)
        elf = library.read_bytes()
        assert elf[:6] == b"\x7fELF\x02\x01" and int.from_bytes(elf[18:20], "little") == 183
        with (output / (abi + "-elf.txt")).open("w") as log:
            run(compiler_bin / "llvm-readelf", "-h", "-l", "-d", library, stdout=log)
    game_hashes, asset_manifest = copy_game(stage)
    write_icons(stage)

    manifest = stage / "AndroidManifest.xml"
    tree = ET.parse(manifest)
    root = tree.getroot()
    old_package = root.get("package")
    root.set("package", PACKAGE)
    # This embedded game needs no network, storage or microphone permission.
    for element in list(root):
        if element.tag == "uses-permission" and element.get(ANDROID + "name") in {
                "android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE",
                "android.permission.INTERNET", "android.permission.RECORD_AUDIO"}:
            root.remove(element)
    for element in root.iter():
        for attr in ("name", "authorities"):
            value = element.get(ANDROID + attr, "")
            if value in {old_package + ".DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION",
                         old_package + ".androidx-startup"}:
                element.set(ANDROID + attr, value.replace(old_package, PACKAGE, 1))
    app = root.find("application")
    app.set(ANDROID + "label", "Sonic 3D Blast")
    app.set(ANDROID + "icon", "@mipmap/sonic_icon")
    app.set(ANDROID + "roundIcon", "@mipmap/sonic_icon")
    app.set(ANDROID + "appCategory", "game")
    app.set(ANDROID + "usesCleartextTraffic", "false")
    for element in list(app):
        name = element.get(ANDROID + "name")
        if name in {old_package + ".DownloadService", old_package + ".DownloadActivity",
                    old_package + ".SelectorActivity"}:
            app.remove(element)
        elif name == old_package + ".GameActivity":
            element.set(ANDROID + "label", "Sonic 3D Blast")
            element.set(ANDROID + "icon", "@mipmap/sonic_icon")
            element.set(ANDROID + "screenOrientation", "sensorLandscape")
            for intent in list(element.findall("intent-filter")):
                actions = [a.get(ANDROID + "name") for a in intent.findall("action")]
                if "android.intent.action.MAIN" not in actions:
                    element.remove(intent)
    tree.write(manifest, encoding="utf-8", xml_declaration=True)
    bools = stage / "res/values/bools.xml"
    tree = ET.parse(bools)
    for element in tree.getroot():
        if element.get("name") == "embed":
            element.text = "true"
    tree.write(bools, encoding="utf-8", xml_declaration=True)
    config = stage / "apktool.yml"
    contents = config.read_text()
    for key, value in {"minSdkVersion": 21, "versionCode": args.version_code,
                       "versionName": args.version_name}.items():
        contents = re.sub(rf"(?m)^(  {key}:).*$", rf"\g<1> {value}", contents)
    config.write_text(contents)
    unsigned = output / "unsigned.apk"
    run("java", "-jar", cache / "apktool_2.9.3.jar", "b", "--no-crunch", "--frame-path", framework,
        "-o", unsigned, stage)
    aligned = output / "aligned.apk"
    run(sdk_bin / "zipalign", "-p", "4", unsigned, aligned)

    # Keep the same private local signing key so later APKs can update this one.
    signing = ROOT / "build/android-signing"
    signing.mkdir(parents=True, exist_ok=True, mode=0o700)
    keystore, password = signing / "sonic.p12", signing / "store.pass"
    if keystore.exists() and not password.exists():
        raise RuntimeError("Existing signing key is missing its password file")
    if not password.exists():
        fd = os.open(password, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_urlsafe(32))
    if not keystore.exists():
        run("keytool", "-genkeypair", "-keystore", keystore, "-storetype", "PKCS12",
            "-storepass:file", password, "-alias", "sonic", "-keyalg", "RSA", "-keysize", "2048",
            "-validity", "10000", "-dname", "CN=Sonic 3D Blast Local Build", "-noprompt")
        keystore.chmod(0o600)
    apk = output / "Sonic-3D-Blast-Love-Android.apk"
    run(sdk_bin / "apksigner", "sign", "--ks", keystore, "--ks-key-alias", "sonic",
        "--ks-pass", "file:" + str(password), "--out", apk, aligned)
    with (output / "signature-verification.txt").open("w") as log:
        run(sdk_bin / "apksigner", "verify", "--verbose", "--print-certs", apk, stdout=log)
    run(sdk_bin / "zipalign", "-c", "4", apk)
    with (output / "apk-badging.txt").open("w") as log:
        run(sdk_bin / "aapt", "dump", "badging", apk, stdout=log)
    with zipfile.ZipFile(apk) as archive:
        for relative, sha in game_hashes.items():
            assert hashlib.sha256(archive.read("assets/" + relative)).hexdigest() == sha, relative
        assert not any(name.startswith("lib/armeabi-v7a/") for name in archive.namelist())
        assert not any(name.startswith("assets/saves/") for name in archive.namelist())
        icon = next(name for name in archive.namelist() if name.endswith("/sonic_art.png"))
        assert archive.read(icon) == (ROOT / "game/icons/sonic.png").read_bytes()
        for abi in ABIS:
            relative = "lib/" + abi + "/libsonic3d.so"
            assert archive.read(relative) == (stage / relative).read_bytes()
    info = {"built_utc": stamp, "package": PACKAGE, "version_code": args.version_code,
            "version_name": args.version_name, "apk": apk.name, "apk_sha256": digest(apk),
            "abis": list(ABIS), "sdk_build_tools": str(sdk_bin), "ndk": str(ndk),
            "runtime_sha256": DOWNLOADS["love-11.5-android.apk"][1],
            "game_files_sha256": game_hashes,
            "original_assets": asset_manifest,
            "native_source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sorted(
                (ROOT / "game/native").rglob("*")) if p.is_file() and p.suffix in {".c", ".h"}},
            "makefile_sha256": digest(ROOT / "Makefile"),
            "builder_sha256": digest(Path(__file__))}
    (output / "BUILD_INFO.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"Verified APK: {apk}")
    print(f"SHA-256: {info['apk_sha256']}")


if __name__ == "__main__":
    main()
