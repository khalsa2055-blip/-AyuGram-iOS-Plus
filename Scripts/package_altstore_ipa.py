#!/usr/bin/env python3
"""Create the AltStore-friendly IPA from a freshly compiled, unsigned device IPA.

Only optional app extensions are omitted. The main app executable, bundle ID,
app-group entitlements, notification extensions, and all application resources
are preserved byte-for-byte. AltStore must re-sign the IPA for the user's team.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import sys
import zipfile
from pathlib import PurePosixPath


REMOVE = {
    "BroadcastUploadExtension.appex",
    "IntentsExtension.appex",
    "ShareExtension.appex",
    "WidgetExtension.appex",
}
KEEP = {
    "NotificationContentExtension.appex",
    "NotificationServiceExtensionv1.appex",
}
EXPECTED_APP_ID_COUNT = 3


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="Freshly built unsigned arm64 device IPA")
    parser.add_argument("output", help="AltStore IPA destination")
    args = parser.parse_args()

    with zipfile.ZipFile(args.source, "r") as src:
        bad = src.testzip()
        if bad:
            raise SystemExit(f"Input IPA ZIP integrity failed at {bad}")

        names = src.namelist()
        app_plists = [
            n for n in names
            if n.startswith("Payload/") and n.endswith(".app/Info.plist")
            and "/PlugIns/" not in n
        ]
        if len(app_plists) != 1:
            raise SystemExit(f"Expected one main app Info.plist, found {app_plists}")
        app_plist = app_plists[0]
        app_root = app_plist[:-len("/Info.plist")]
        app_info = plistlib.loads(src.read(app_plist))
        if app_info.get("CFBundleIdentifier") != "org.ayugram.iosplus":
            raise SystemExit(f"Unexpected bundle ID: {app_info.get('CFBundleIdentifier')}")

        ext_info_paths = [
            n for n in names
            if n.startswith(app_root + "/PlugIns/") and n.endswith(".appex/Info.plist")
        ]
        extensions: dict[str, str] = {}
        for path in ext_info_paths:
            parts = PurePosixPath(path).parts
            name = parts[-2]
            info = plistlib.loads(src.read(path))
            extensions[name] = str(info.get("CFBundleIdentifier", ""))

        present = set(extensions)
        if present != REMOVE | KEEP:
            raise SystemExit(
                "Unexpected source extension set; refusing to silently drop features. "
                f"Expected {sorted(REMOVE | KEEP)}, found {sorted(present)}"
            )

        retained_ids = {"org.ayugram.iosplus"} | {extensions[name] for name in KEEP}
        if len(retained_ids) != EXPECTED_APP_ID_COUNT or "" in retained_ids:
            raise SystemExit(f"Unexpected retained App ID set: {sorted(retained_ids)}")

        executable = app_info.get("CFBundleExecutable")
        executable_path = f"{app_root}/{executable}"
        if executable_path not in names:
            raise SystemExit(f"Main executable is missing: {executable_path}")
        executable_hash = sha256(src.read(executable_path))

        signatures = [n for n in names if "/_CodeSignature/" in n or n.endswith("embedded.mobileprovision")]
        if signatures:
            raise SystemExit(
                "Expected an unsigned IPA for AltStore re-signing; found embedded signatures/profiles: "
                + ", ".join(signatures[:12])
            )

        with zipfile.ZipFile(args.output, "w", allowZip64=True) as dst:
            dst.comment = src.comment
            for item in src.infolist():
                parts = PurePosixPath(item.filename).parts
                if (
                    len(parts) >= 4
                    and parts[0] == "Payload"
                    and parts[1].endswith(".app")
                    and parts[2] == "PlugIns"
                    and parts[3] in REMOVE
                ):
                    continue
                data = b"" if item.is_dir() else src.read(item.filename)
                dst.writestr(item, data)

    with zipfile.ZipFile(args.output, "r") as check:
        bad = check.testzip()
        if bad:
            raise SystemExit(f"Output IPA ZIP integrity failed at {bad}")
        output_names = check.namelist()
        output_extensions = {
            PurePosixPath(n).parts[-2]
            for n in output_names
            if n.startswith(app_root + "/PlugIns/") and n.endswith(".appex/Info.plist")
        }
        if output_extensions != KEEP:
            raise SystemExit(f"Output extensions incorrect: {sorted(output_extensions)}")
        output_info = plistlib.loads(check.read(app_plist))
        if output_info.get("CFBundleIdentifier") != "org.ayugram.iosplus":
            raise SystemExit("Output main app bundle ID changed")
        if sha256(check.read(executable_path)) != executable_hash:
            raise SystemExit("Main executable changed during AltStore packaging")
        if any("/_CodeSignature/" in n or n.endswith("embedded.mobileprovision") for n in output_names):
            raise SystemExit("Output unexpectedly contains a code signature or provisioning profile")

    report = {
        "source": args.source,
        "output": args.output,
        "bundle_id": "org.ayugram.iosplus",
        "retained_extensions": sorted(KEEP),
        "removed_optional_extensions": sorted(REMOVE),
        "estimated_registered_app_ids": EXPECTED_APP_ID_COUNT,
        "main_executable_sha256": executable_hash,
        "ipa_sha256": sha256(open(args.output, "rb").read()),
    }
    with open(args.output + ".json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
