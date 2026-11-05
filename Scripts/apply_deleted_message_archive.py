#!/usr/bin/env python3
"""Install a reversible, pre-delete message archive hook into a Swiftgram checkout.

The hook snapshots message text/metadata and copies media resources that are already
complete in MediaBox BEFORE Telegram removes the message. It does not change manual
Save, Telegram deletion semantics, or attempt to reinsert messages into Telegram.
"""
from pathlib import Path
import argparse

CORE_RELATIVE_PATH = Path("submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift")

HELPER = r'''
private func ayuGramDeletedMessageArchiveDirectory() -> URL? {
    return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
        .appendingPathComponent("AyuGramDeletedMessageArchive", isDirectory: true)
}

private func ayuGramDeletedMessageArchiveStem(_ messageId: MessageId) -> String {
    let peerValue = messageId.peerId.id._internalGetInt64Value()
    return "peer-\(messageId.peerId.namespace)-\(peerValue)-message-\(messageId.id)"
}

/// Copies the message snapshot before Postbox removes it and before cached media can be purged.
/// Text/metadata are retained even when one or more media resources are not cached locally.
private func ayuGramArchiveMessageBeforeDeletion(_ message: Message, mediaBox: MediaBox) {
    guard let root = ayuGramDeletedMessageArchiveDirectory() else {
        return
    }

    let destination = root.appendingPathComponent(ayuGramDeletedMessageArchiveStem(message.id), isDirectory: true)
    guard !FileManager.default.fileExists(atPath: destination.path) else {
        return
    }

    let temporary = root.appendingPathComponent(".\(UUID().uuidString).deleted-message-tmp", isDirectory: true)
    do {
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)

        var mediaRecords: [[String: Any]] = []
        var mediaIndex = 0
        for item in message.media {
            var resources: [(MediaResource, String)] = []
            if let image = item as? TelegramMediaImage {
                for representation in image.representations {
                    resources.append((representation.resource, "photo"))
                }
            } else if let file = item as? TelegramMediaFile {
                let kind = file.isVideo ? "video" : "file"
                resources.append((file.resource, kind))
            }

            for (resource, kind) in resources {
                let sourcePath = mediaBox.completedResourcePath(resource)
                let originalName: String?
                if let file = item as? TelegramMediaFile {
                    originalName = file.fileName
                } else {
                    originalName = nil
                }
                let ext = ((originalName ?? "") as NSString).pathExtension
                let safeExtension = ext.range(of: "^[A-Za-z0-9]{1,8}$", options: .regularExpression) != nil
                    ? ext.lowercased()
                    : (kind == "photo" ? "jpg" : (kind == "video" ? "mp4" : "bin"))
                let archivedName = "media-\(mediaIndex).\(safeExtension)"
                var copied = false
                if let sourcePath {
                    do {
                        try FileManager.default.copyItem(
                            at: URL(fileURLWithPath: sourcePath),
                            to: temporary.appendingPathComponent(archivedName)
                        )
                        copied = true
                    } catch {
                        copied = false
                    }
                }
                mediaRecords.append([
                    "kind": kind,
                    "fileName": originalName ?? NSNull(),
                    "archiveFile": copied ? archivedName : NSNull(),
                    "cachedAtDeletion": copied
                ])
                mediaIndex += 1
            }
        }

        let manifest: [String: Any] = [
            "version": 1,
            "peerNamespace": Int(message.id.peerId.namespace),
            "peerId": message.id.peerId.id._internalGetInt64Value(),
            "messageId": Int(message.id.id),
            "timestamp": Int(message.timestamp),
            "text": message.text,
            "media": mediaRecords,
            "mediaComplete": mediaRecords.allSatisfy { ($0["cachedAtDeletion"] as? Bool) == true }
        ]
        let data = try JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: temporary.appendingPathComponent("message.json"), options: .atomic)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try FileManager.default.moveItem(at: temporary, to: destination)
    } catch {
        try? FileManager.default.removeItem(at: temporary)
        return
    }
}

'''

ANCHOR = "func replayFinalState(\n"
DELETE_ANCHOR = """            case let .DeleteMessages(ids):
                _internal_deleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, manualAddMessageThreadStatsDifference: { id, add, remove in
"""

DELETE_REPLACEMENT = """            case let .DeleteMessages(ids):
                // Snapshot before deletion: after _internal_deleteMessages, Postbox may no longer
                // expose the message and Telegram may purge its cached media resources.
                for id in ids {
                    if let message = transaction.getMessage(id) {
                        ayuGramArchiveMessageBeforeDeletion(message, mediaBox: mediaBox)
                    }
                }
                _internal_deleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, manualAddMessageThreadStatsDifference: { id, add, remove in
"""

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"FAIL: {label}: expected exactly one anchor, found {count}")
    return source.replace(old, new, 1)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    core_path = args.upstream / CORE_RELATIVE_PATH
    if not core_path.is_file():
        raise SystemExit(f"FAIL: missing TelegramCore source: {core_path}")
    source = core_path.read_text(encoding="utf-8")

    if "ayuGramArchiveMessageBeforeDeletion" in source:
        raise SystemExit("FAIL: deleted-message archive hook already exists; refusing duplicate patch")

    source = replace_once(source, "func replayFinalState(\n", HELPER + "\nfunc replayFinalState(\n", "archive helper insertion")
    source = replace_once(source, DELETE_ANCHOR, DELETE_REPLACEMENT, "pre-delete snapshot hook")
    core_path.write_text(source, encoding="utf-8")
    print("PASS: deleted-message snapshot runs before Telegram's DeleteMessages operation.")
    print("NOTE: media not present in MediaBox at deletion time is marked unavailable; no network fetch is attempted.")

if __name__ == "__main__":
    main()
