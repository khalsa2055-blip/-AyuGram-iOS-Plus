#!/usr/bin/env python3
"""Prevent manual-save filename collisions between accounts and Telegram dialogs."""
from pathlib import Path

archive = Path("telegram-ios/submodules/AyuGramIOS/Sources/AyuGramMediaArchive.swift")
if not archive.is_file():
    raise SystemExit(f"Missing AyuGram media archive source: {archive}")

source = archive.read_text(encoding="utf-8")
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
    'let savedStem = "account-\\(message.userID)-dialog-\\(message.dialogID)-message-\\(message.messageID)"',
    '"\\(savedStem)-media-\\(index + 1).\\(ext)"',
    '"\\(savedStem)-media.\\(ext)"',
    '"\\(savedStem).txt"',
    '"\\(savedStem).json"',
]
for marker in required:
    if marker not in source:
        raise SystemExit(f"Dialog-safe saved filename missing: {marker}")

archive.write_text(source, encoding="utf-8")
print("PASS: saved media/text/metadata filenames are isolated by account and dialog.")
