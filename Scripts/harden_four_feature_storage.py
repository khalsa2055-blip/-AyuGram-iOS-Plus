#!/usr/bin/env python3
"""Keep manual-save media together in king and avoid filename collisions."""
from pathlib import Path
import re

project_root = Path("telegram-ios") if Path("telegram-ios").is_dir() else Path(".")
base = project_root / "submodules/AyuGramIOS/Sources"
archive = base / "AyuGramMediaArchive.swift"
capture = base / "AyuGramCaptureService.swift"
if not archive.is_file():
    raise SystemExit(f"Missing AyuGram media archive source: {archive}")
if not capture.is_file():
    raise SystemExit(f"Missing AyuGram capture service source: {capture}")

source = archive.read_text(encoding="utf-8")
signature = "    public static func saveToSaved(message: AyuMessage) -> Bool {"
updated_signature = '    public static func saveToSaved(message: AyuMessage, folderName: String = "Media") -> Bool {'
if signature in source:
    if source.count(signature) != 1:
        raise SystemExit("Expected one saveToSaved declaration")
    source = source.replace(signature, updated_signature, 1)
elif updated_signature not in source:
    raise SystemExit("Could not locate saveToSaved declaration")

media_root = '        let mediaRoot = root.appendingPathComponent("Media", isDirectory: true)'
updated_media_root = '        let mediaRoot = root.appendingPathComponent(folderName, isDirectory: true)'
if media_root in source:
    if source.count(media_root) != 1:
        raise SystemExit("Expected one Saved media folder declaration")
    source = source.replace(media_root, updated_media_root, 1)
elif updated_media_root not in source:
    raise SystemExit("Could not locate Saved media folder declaration")

anchor = '        let messagesRoot = root.appendingPathComponent("Messages", isDirectory: true)\n'
stem = '        let messagesRoot = root.appendingPathComponent("Messages", isDirectory: true)\n        let savedStem = "account-\\(message.userID)-dialog-\\(message.dialogID)-message-\\(message.messageID)"\n'
if "let savedStem = " not in source:
    if source.count(anchor) != 1:
        raise SystemExit("Could not uniquely locate Saved Messages directory setup")
    source = source.replace(anchor, stem, 1)

replacements = {
    '"message-\\(message.messageID)-media-\\(index + 1).\\(ext)"': '"\\(savedStem)-media-\\(index + 1).\\(ext)"',
    '"message-\\(message.messageID)-media.\\(ext)"': '"\\(savedStem)-media.\\(ext)"',
    '"message-\\(message.messageID).txt"': '"\\(savedStem).txt"',
    '"message-\\(message.messageID).json"': '"\\(savedStem).json"',
}
for old, new in replacements.items():
    if old in source:
        if source.count(old) != 1:
            raise SystemExit(f"Expected one saved filename anchor, found {source.count(old)}: {old}")
        source = source.replace(old, new, 1)
    elif new not in source:
        raise SystemExit(f"Saved filename anchor missing: {old}")

required = [
    updated_signature,
    updated_media_root,
    'let savedStem = "account-\\(message.userID)-dialog-\\(message.dialogID)-message-\\(message.messageID)"',
    '"\\(savedStem)-media-\\(index + 1).\\(ext)"',
    '"\\(savedStem)-media.\\(ext)"',
    '"\\(savedStem).txt"',
    '"\\(savedStem).json"',
]
for marker in required:
    if marker not in source:
        raise SystemExit(f"Saved archive invariant missing: {marker}")
archive.write_text(source, encoding="utf-8")

capture_source = capture.read_text(encoding="utf-8")
manual_call = "        return AyuGramMediaArchive.saveToSaved(message: savedSnapshot)"
king_call = '        return AyuGramMediaArchive.saveToSaved(message: savedSnapshot, folderName: "king")'
if manual_call in capture_source:
    if capture_source.count(manual_call) != 1:
        raise SystemExit("Expected one manual Save call site")
    capture_source = capture_source.replace(manual_call, king_call, 1)
elif king_call not in capture_source:
    raise SystemExit("Could not uniquely locate manual Save call site")
capture.write_text(capture_source, encoding="utf-8")

smoke = base / "AyuGramSmokeTest.swift"
if smoke.is_file():
    smoke_text = smoke.read_text(encoding="utf-8")
    # Build each fixture name from its local identifiers; do not introduce a
    # savedStem local whose declaration can land outside the fixture's closure.
    smoke_replacements = {
        r'"message-\(messageID)-media-1.jpg"': r'"account-\(accountID)-dialog-\(dialogID)-message-\(messageID)-media-1.jpg"',
        r'"message-\(messageID)-media-2.mp4"': r'"account-\(accountID)-dialog-\(dialogID)-message-\(messageID)-media-2.mp4"',
        r'"message-\(messageID)-media.jpg"': r'"account-\(accountID)-dialog-\(dialogID)-message-\(messageID)-media.jpg"',
        r'"message-\(messageID).json"': r'"account-\(accountID)-dialog-\(dialogID)-message-\(messageID).json"',
    }
    for old, new in smoke_replacements.items():
        smoke_text = smoke_text.replace(old, new, 1)
    # Remove the previous intermediate variable and inline its stable identity
    # in every filename interpolation, including fixtures added by older patches.
    smoke_text = re.sub(r"(?m)^[ \t]*let savedStem\s*=.*(?:\n|$)", "", smoke_text)
    smoke_text = smoke_text.replace(
        r"\(savedStem)",
        r"account-\(accountID)-dialog-\(dialogID)-message-\(messageID)",
    )
    if "savedStem" in smoke_text:
        raise SystemExit("Smoke-test fixture still references savedStem after normalization")
    smoke.write_text(smoke_text, encoding="utf-8")

print("PASS: manual Save stores photos and videos together in saved/king; History keeps its separate Media folder.")
