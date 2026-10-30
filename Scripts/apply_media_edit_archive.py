#!/usr/bin/env python3
"""Apply the media-edit archive integration to a freshly checked-out Swiftgram tree.

The upstream repository is deliberately kept as a separate checkout. This script
is idempotent and fails closed if upstream changes the integration anchors.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "upstream")
CORE = ROOT / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
UI = ROOT / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"

CORE_HELPER = r'''
private struct AyuGramEditableMediaCandidate {
    let kind: String
    let resources: [MediaResource]
    let fileExtension: String
}

private func ayuGramEditableMediaCandidate(_ media: [Media]) -> AyuGramEditableMediaCandidate? {
    for item in media {
        if let image = item as? TelegramMediaImage {
            let representations = image.representations.sorted {
                Int64($0.dimensions.width) * Int64($0.dimensions.height) >
                Int64($1.dimensions.width) * Int64($1.dimensions.height)
            }
            if !representations.isEmpty {
                return AyuGramEditableMediaCandidate(
                    kind: "photo",
                    resources: representations.map { $0.resource },
                    fileExtension: "jpg"
                )
            }
        } else if let file = item as? TelegramMediaFile, file.isVideo {
            let allowedExtensions = Set(["mp4", "mov", "m4v", "webm", "mkv"])
            let candidateExtension = file.fileName.map { ($0 as NSString).pathExtension.lowercased() } ?? ""
            return AyuGramEditableMediaCandidate(
                kind: "video",
                resources: [file.resource],
                fileExtension: allowedExtensions.contains(candidateExtension) ? candidateExtension : "mp4"
            )
        }
    }
    return nil
}

private func ayuGramMediaEditArchiveDirectory() -> URL? {
    return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
        .appendingPathComponent("AyuGramMediaEditArchive", isDirectory: true)
}

private func ayuGramMediaEditArchiveStem(_ messageId: MessageId) -> String {
    let peerValue = messageId.peerId.id._internalGetInt64Value()
    return "peer-\(messageId.peerId.namespace)-\(peerValue)-message-\(messageId.id)"
}

/// Returns the locally archived pre-edit media file for a message, if one exists.
public func archivedOriginalMediaURL(for messageId: MessageId) -> URL? {
    guard let directory = ayuGramMediaEditArchiveDirectory() else {
        return nil
    }
    let prefix = ayuGramMediaEditArchiveStem(messageId) + "."
    guard let files = try? FileManager.default.contentsOfDirectory(
        at: directory,
        includingPropertiesForKeys: nil,
        options: [.skipsHiddenFiles]
    ) else {
        return nil
    }
    return files.first(where: { $0.lastPathComponent.hasPrefix(prefix) })
}

private func ayuGramArchiveOriginalMediaBeforeEdit(
    previousMessage: Message,
    replacementMessage: StoreMessage,
    mediaBox: MediaBox
) {
    guard
        let original = ayuGramEditableMediaCandidate(previousMessage.media),
        let replacement = ayuGramEditableMediaCandidate(replacementMessage.media),
        original.kind != replacement.kind || original.resources.first?.id != replacement.resources.first?.id,
        let sourcePath = original.resources.compactMap({ mediaBox.completedResourcePath($0) }).first,
        let directory = ayuGramMediaEditArchiveDirectory()
    else {
        return
    }

    let destination = directory
        .appendingPathComponent(ayuGramMediaEditArchiveStem(previousMessage.id))
        .appendingPathExtension(original.fileExtension)

    // Keep the first original forever; further edits must not replace it.
    guard !FileManager.default.fileExists(atPath: destination.path) else {
        return
    }

    do {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let temporary = directory.appendingPathComponent(".\(UUID().uuidString).media-tmp")
        try FileManager.default.copyItem(at: URL(fileURLWithPath: sourcePath), to: temporary)
        try FileManager.default.moveItem(at: temporary, to: destination)
    } catch {
        // An unavailable or incomplete cache entry is not treated as an original.
        return
    }
}
'''

CORE_ANCHOR = "func replayFinalState(\n"
CORE_HOOK_OLD = """            case let .EditMessage(id, message):
                var generatedEvent: (reactionAuthor: Peer, reaction: MessageReaction.Reaction, message: Message, timestamp: Int32)?
                transaction.updateMessage(id, update: { previousMessage in
                    let peers: [PeerId:Peer] = previousMessage.peers.reduce([:], { current, value in
"""
CORE_HOOK_NEW = """            case let .EditMessage(id, message):
                var generatedEvent: (reactionAuthor: Peer, reaction: MessageReaction.Reaction, message: Message, timestamp: Int32)?
                transaction.updateMessage(id, update: { previousMessage in
                    ayuGramArchiveOriginalMediaBeforeEdit(previousMessage: previousMessage, replacementMessage: message, mediaBox: mediaBox)
                    let peers: [PeerId:Peer] = previousMessage.peers.reduce([:], { current, value in
"""

UI_IMPORT_ANCHOR = "import TelegramCore\n"
UI_CLASS_ANCHOR = "private struct MessageContextMenuData {\n"
UI_CLASS = r'''
private final class AyuGramMediaEditOriginalPreviewItem: NSObject, QLPreviewItem {
    private let url: URL

    init(url: URL) {
        self.url = url
    }

    var previewItemURL: URL? {
        return self.url
    }

    var previewItemTitle: String? {
        return "Original media"
    }
}

private final class AyuGramMediaEditOriginalPreviewController: QLPreviewController, QLPreviewControllerDataSource {
    private let item: AyuGramMediaEditOriginalPreviewItem

    init(url: URL) {
        self.item = AyuGramMediaEditOriginalPreviewItem(url: url)
        super.init(nibName: nil, bundle: nil)
        self.dataSource = self
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func numberOfPreviewItems(in controller: QLPreviewController) -> Int {
        return 1
    }

    func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem {
        return self.item
    }
}

'''
UI_ACTION_ANCHOR = "        var downloadableMediaResourceInfos: [String] = []\n"
UI_ACTION = r'''        if !message.containsSecretMedia && !isCopyProtected,
           let originalURL = archivedOriginalMediaURL(for: message.id) {
            actions.append(.action(ContextMenuActionItem(text: "View Original", icon: { theme in
                return generateTintedImage(image: UIImage(bundleImageName: "Chat/Context Menu/Message"), color: theme.actionSheet.primaryTextColor)
            }, action: { _, f in
                let preview = AyuGramMediaEditOriginalPreviewController(url: originalURL)
                controllerInteraction.navigationController()?.present(preview, animated: true, completion: nil)
                f(.default)
            })))
        }

'''

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return source.replace(old, new, 1)

def main() -> None:
    if not CORE.is_file() or not UI.is_file():
        raise SystemExit("Swiftgram source tree is missing required TelegramCore/TelegramUI files")

    core = CORE.read_text()
    ui = UI.read_text()

    if "ayuGramArchiveOriginalMediaBeforeEdit" in core or "AyuGramMediaEditOriginalPreviewController" in ui:
        raise SystemExit("Media-edit archive integration already appears to be applied; refusing duplicate patch")

    core = replace_once(core, CORE_ANCHOR, CORE_HELPER + "\n" + CORE_ANCHOR, "TelegramCore helper insertion")
    core = replace_once(core, CORE_HOOK_OLD, CORE_HOOK_NEW, "incoming message edit hook")

    ui = replace_once(ui, UI_IMPORT_ANCHOR, UI_IMPORT_ANCHOR + "import QuickLook\n", "QuickLook import")
    ui = replace_once(ui, UI_CLASS_ANCHOR, UI_CLASS + UI_CLASS_ANCHOR, "original preview controller")
    ui = replace_once(ui, UI_ACTION_ANCHOR, UI_ACTION + UI_ACTION_ANCHOR, "View Original context menu action")

    CORE.write_text(core)
    UI.write_text(ui)
    print("Media edit archive integration applied:")
    print(f"  {CORE.relative_to(ROOT)}")
    print(f"  {UI.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
