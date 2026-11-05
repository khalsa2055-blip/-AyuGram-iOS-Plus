#!/usr/bin/env python3
"""Connect Before to the existing AyuGram deleted/edited media archive.

This patch deliberately does not add another archive, alter captureDeleted,
captureEdited, the deleted-message retention UI, or manual Save.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "upstream")
ARCHIVE = ROOT / "submodules/AyuGramIOS/Sources/AyuGramMediaArchive.swift"
UI = ROOT / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"

ARCHIVE_LOOKUP = r'''
    /// Resolve the already-captured media for Before. Edited revisions are
    /// preferred (the first edit folder contains the pre-edit original); if
    /// there is no edit snapshot, fall back to the existing deleted-message
    /// archive. No media is copied or recaptured by this lookup.
    public static func archivedOriginalMediaURL(
        accountID: Int64,
        dialogID: Int64,
        messageID: Int32
    ) -> URL? {
        guard let messageRoot = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first?
            .appendingPathComponent("AyuGram", isDirectory: true)
            .appendingPathComponent("History", isDirectory: true)
            .appendingPathComponent(String(accountID), isDirectory: true)
            .appendingPathComponent(String(dialogID), isDirectory: true)
            .appendingPathComponent(String(messageID), isDirectory: true) else {
            return nil
        }

        let directories = ((try? FileManager.default.contentsOfDirectory(
            at: messageRoot,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        )) ?? []).filter {
            $0.lastPathComponent.hasPrefix("edit-") &&
            ((try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true)
        }.sorted {
            $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending
        }

        // Preserve the first pre-edit version across multiple edits.
        var candidates = directories
        let deletedDirectory = messageRoot.appendingPathComponent("deleted", isDirectory: true)
        if FileManager.default.fileExists(atPath: deletedDirectory.path) {
            candidates.append(deletedDirectory)
        }

        for directory in candidates {
            let files = ((try? FileManager.default.contentsOfDirectory(
                at: directory,
                includingPropertiesForKeys: [.isRegularFileKey],
                options: [.skipsHiddenFiles]
            )) ?? []).filter {
                $0.pathExtension.lowercased() != "json" &&
                ((try? $0.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true)
            }.sorted {
                $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending
            }
            if let firstFile = files.first {
                return firstFile
            }
        }
        return nil
    }
'''

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

UI_ACTION = r'''        if !message.containsSecretMedia && !isCopyProtected,
           let originalURL = AyuGramMediaArchive.archivedOriginalMediaURL(
               accountID: context.account.peerId.toInt64(),
               dialogID: message.id.peerId.toInt64(),
               messageID: message.id.id
           ) {
            actions.append(.action(ContextMenuActionItem(text: "Before", icon: { theme in
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
    if not ARCHIVE.is_file() or not UI.is_file():
        raise SystemExit("Missing existing AyuGram media archive or TelegramUI context-menu source")

    archive = ARCHIVE.read_text(encoding="utf-8")
    ui = UI.read_text(encoding="utf-8")

    if "public enum AyuGramMediaArchive {" not in archive:
        raise SystemExit("Existing AyuGramMediaArchive API was not found")
    if "AyuGramMediaArchive.archivedOriginalMediaURL" in ui:
        raise SystemExit("Before already uses the existing AyuGram media archive")

    if "public static func archivedOriginalMediaURL(" not in archive:
        archive = replace_once(
            archive,
            "public enum AyuGramMediaArchive {",
            "public enum AyuGramMediaArchive {\n" + ARCHIVE_LOOKUP,
            "existing archive lookup insertion"
        )

    if "import QuickLook\n" not in ui:
        ui = replace_once(ui, "import TelegramCore\n", "import TelegramCore\nimport QuickLook\n", "QuickLook import")
    if "import AyuGramIOS\n" not in ui:
        ui = replace_once(ui, "import TelegramCore\n", "import TelegramCore\nimport AyuGramIOS\n", "AyuGram archive import")
    if "AyuGramMediaEditOriginalPreviewController" not in ui:
        ui = replace_once(ui, "private struct MessageContextMenuData {\n", UI_CLASS + "private struct MessageContextMenuData {\n", "Before preview controller")
    ui = replace_once(
        ui,
        "        var downloadableMediaResourceInfos: [String] = []\n",
        UI_ACTION + "        var downloadableMediaResourceInfos: [String] = []\n",
        "Before context-menu action"
    )

    ARCHIVE.write_text(archive, encoding="utf-8")
    UI.write_text(ui, encoding="utf-8")
    print("Before now reads the existing AyuGram edit/deleted media archive.")
    print("No deleted-message capture, retention UI, or manual Save code was changed.")

if __name__ == "__main__":
    main()
