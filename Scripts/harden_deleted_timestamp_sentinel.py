#!/usr/bin/env python3
"""Keep AyuGram's internal deleted-message sentinel out of Telegram timestamp arithmetic."""
from pathlib import Path


ROOT = Path("telegram-ios") if Path("telegram-ios").is_dir() else Path(".")

# Telegram treats EditedMessageAttribute.date as a real Unix timestamp in these
# paths. AyuGram uses Int32.min only as a local deleted-message marker, so each
# timestamp consumer must ignore that marker before doing date math or UInt64
# hashing. Keep this guard narrow: ordinary edited timestamps are unchanged.
SPECS = (
    (
        ROOT / "submodules/TelegramCore/Sources/State/HistoryViewStateValidation.swift",
        7,
        "history-state hash and validation timestamp readers",
    ),
    (
        ROOT / "submodules/TelegramCore/Sources/TelegramEngine/Messages/QuickReplyMessages.swift",
        1,
        "quick-reply hash timestamp reader",
    ),
    (
        ROOT / "submodules/LocationUI/Sources/LocationLiveListItem.swift",
        1,
        "live-location list timestamp reader",
    ),
    (
        ROOT / "submodules/LocationUI/Sources/LocationViewControllerNode.swift",
        1,
        "live-location controller timestamp reader",
    ),
    (
        ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageMapBubbleContentNode/Sources/ChatMessageMapBubbleContentNode.swift",
        2,
        "map-bubble edited/live-location timestamp readers",
    ),
)

OLD = "if let attribute = attribute as? EditedMessageAttribute {"
NEW = (
    "if let attribute = attribute as? EditedMessageAttribute, "
    "attribute.date != Int32.min {"
)

for path, expected, label in SPECS:
    if not path.is_file():
        raise SystemExit(f"{label}: required Telegram source file is missing: {path}")

    source = path.read_text(encoding="utf-8")
    old_count = source.count(OLD)
    new_count = source.count(NEW)

    if old_count == expected and new_count == 0:
        source = source.replace(OLD, NEW)
        path.write_text(source, encoding="utf-8")
    elif old_count == 0 and new_count == expected:
        # Idempotent when the workflow is re-run against already-hardened source.
        pass
    else:
        raise SystemExit(
            f"{label}: expected {expected} unguarded timestamp readers "
            f"or {expected} already-guarded readers; found {old_count} unguarded "
            f"and {new_count} guarded"
        )

    verified = path.read_text(encoding="utf-8")
    if verified.count(NEW) != expected or verified.count(OLD) != 0:
        raise SystemExit(f"{label}: sentinel guard verification failed")

print("PASS: deleted-message Int32.min sentinel is excluded from all Telegram timestamp/hash readers.")
print("PASS: ordinary EditedMessageAttribute timestamps retain their original behavior.")
