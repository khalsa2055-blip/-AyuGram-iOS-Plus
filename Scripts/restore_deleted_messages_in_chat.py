#!/usr/bin/env python3
"""Keep server-deleted Telegram messages in their original chat, with a local deleted mark."""
from pathlib import Path
import re


ROOT = Path("telegram-ios") if Path("telegram-ios").is_dir() else Path(".")
DELETE = ROOT / "submodules/TelegramCore/Sources/TelegramEngine/Messages/DeleteMessages.swift"
STATE = ROOT / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
HOLES = ROOT / "submodules/TelegramCore/Sources/State/Holes.swift"
THREAD_HISTORY = ROOT / "submodules/TelegramCore/Sources/TelegramEngine/Messages/ReplyThreadHistory.swift"
LOAD_MESSAGES = ROOT / "submodules/TelegramCore/Sources/TelegramEngine/Messages/LoadMessagesIfNecessary.swift"
BUBBLE = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
TEXT_BUBBLE = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageTextBubbleContentNode/Sources/ChatMessageTextBubbleContentNode.swift"
MEDIA_BUBBLE = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageMediaBubbleContentNode/Sources/ChatMessageMediaBubbleContentNode.swift"
INTERACTIVE_MEDIA = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageInteractiveMediaNode/Sources/ChatMessageInteractiveMediaNode.swift"
DATE_STATUS = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/ChatMessageDateAndStatusNode.swift"
SETTINGS = ROOT / "submodules/TelegramUI/Components/AyuGramSettingsScreen/Sources/AyuGramSettingsScreen.swift"
MESSAGE_MENU = ROOT / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
PEER_MEDIA_MENU = ROOT / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoScreenDisplayMediaGalleryContextMenu.swift"
PEER_HEADER_MENU = ROOT / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoScreenPerformButtonAction.swift"
ENGINE = ROOT / "submodules/TelegramCore/Sources/TelegramEngine/Messages/TelegramEngineMessages.swift"
CAPTURE_SERVICE = ROOT / "submodules/AyuGramIOS/Sources/AyuGramCaptureService.swift"
STORE = ROOT / "submodules/AyuGramIOS/Sources/AyuGramPostboxHistoryStore.swift"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count == 0 and new in source:
        return source
    if count != 1:
        raise SystemExit(f"{label}: expected one source anchor, found {count}")
    return source.replace(old, new, 1)


def ensure_swift_import(source: str, anchor: str, module: str, label: str) -> str:
    lines = source.splitlines()
    if module in lines:
        return source
    matches = [index for index, line in enumerate(lines) if line.strip() == anchor]
    if len(matches) != 1:
        raise SystemExit(f"{label}: expected one {anchor!r} import line, found {len(matches)}")
    lines.insert(matches[0] + 1, module)
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def matching_delimiter(source: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string = escaped = line_comment = block_comment = False
    i = start
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if line_comment:
            if ch == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
        elif ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise SystemExit(f"Could not find matching {closing!r} for Swift block at offset {start}")


def find_case_block(source: str, case_label: str, required: str):
    pattern = re.compile(r"(?m)^(?P<indent> *)" + re.escape(case_label) + r"\n")
    for match in pattern.finditer(source):
        indent = match.group("indent")
        sibling_pattern = re.compile(r"(?m)^" + re.escape(indent) + r"case ")
        sibling = sibling_pattern.search(source, match.end())
        end = sibling.start() if sibling else len(source)
        block = source[match.start():end]
        if required in block:
            return match.start(), end, block
    return None

def remove_swift_action(source: str, marker: str, append_prefix: str, label: str) -> str:
    marker_pos = source.find(marker)
    if marker_pos < 0:
        return source
    start = source.rfind(append_prefix, 0, marker_pos)
    if start < 0:
        raise SystemExit(f"{label}: found marker but not its action wrapper")
    end = matching_delimiter(source, start, "(", ")") + 1
    line_end = source.find("\n", end)
    end = len(source) if line_end < 0 else line_end + 1
    line_start = source.rfind("\n", 0, start) + 1
    previous_line_end = line_start - 1
    if previous_line_end >= 0:
        previous_line_start = source.rfind("\n", 0, previous_line_end) + 1
        previous_line = source[previous_line_start:previous_line_end].strip()
        if previous_line.startswith("//") and "AyuGram History" in previous_line:
            start = previous_line_start
    return source[:start] + source[end:]


def remove_swift_function(source: str, signature: str, label: str) -> str:
    start = source.find(signature)
    if start < 0:
        return source
    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit(f"{label}: function opening brace missing")
    end = matching_delimiter(source, brace, "{", "}") + 1
    if end < len(source) and source[end] == "\n":
        end += 1
    return source[:start] + source[end:]


for path in (DELETE, STATE, HOLES, THREAD_HISTORY, LOAD_MESSAGES, BUBBLE, TEXT_BUBBLE, MEDIA_BUBBLE, INTERACTIVE_MEDIA, DATE_STATUS, SETTINGS, MESSAGE_MENU, PEER_MEDIA_MENU, PEER_HEADER_MENU, ENGINE, CAPTURE_SERVICE, STORE):
    if not path.is_file():
        raise SystemExit(f"Required source file is missing: {path}")


capture_service_text = CAPTURE_SERVICE.read_text(encoding="utf-8")
diagnostic_method = r'''    private static let deletionDiagnosticsQueue = DispatchQueue(
        label: "org.ayugram.deleted-message-diagnostics",
        qos: .utility
    )

    public static func recordDeletedRouteDiagnostic(
        _ route: String,
        received: Int,
        mapped: Int? = nil,
        retained: Int? = nil,
        missing: Int? = nil,
        secretMedia: Int? = nil,
        alreadyRetained: Int? = nil,
        peerNamespace: Int? = nil
    ) {
        let fields: [(String, Int?)] = [
            ("mapped", mapped),
            ("retained", retained),
            ("missing", missing),
            ("secretMedia", secretMedia),
            ("alreadyRetained", alreadyRetained),
            ("peerNamespace", peerNamespace)
        ]
        let extra = fields.compactMap { key, value in value.map { "\\(key)=\\($0)" } }.joined(separator: " ")
        let suffix = extra.isEmpty ? "" : " " + extra
        let line = "\\(Int(Date().timeIntervalSince1970)) \\(route) received=\\(received)\\(suffix)\\n"

        // Diagnostics are intentionally asynchronous: this method is called from
        // Telegram's Postbox transaction path and must never read/write Documents
        // synchronously while a chat is being opened or a delete update is handled.
        deletionDiagnosticsQueue.async {
            guard let documentsURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
                return
            }
            let fileURL = documentsURL.appendingPathComponent("AyuGramDeletedMessageDiagnostics.txt")
            do {
                if !FileManager.default.fileExists(atPath: fileURL.path) {
                    _ = FileManager.default.createFile(atPath: fileURL.path, contents: nil)
                }
                let handle = try FileHandle(forWritingTo: fileURL)
                handle.seekToEndOfFile()
                handle.write(Data(line.utf8))
                handle.closeFile()

                // Keep the diagnostic file bounded without imposing I/O on the
                // caller. Trimming is rare and happens on this serial utility queue.
                if let attributes = try? FileManager.default.attributesOfItem(atPath: fileURL.path),
                   let size = attributes[.size] as? NSNumber,
                   size.intValue > 65536,
                   let data = try? Data(contentsOf: fileURL) {
                    try Data(data.suffix(32768)).write(to: fileURL, options: .atomic)
                }
            } catch {
                // Diagnostics are best-effort and must never affect Telegram deletion.
            }
        }
    }

'''

enum_anchor = "public enum AyuGramCaptureService {\n"
if "public static func recordDeletedRouteDiagnostic(" not in capture_service_text:
    if capture_service_text.count(enum_anchor) != 1:
        raise SystemExit("AyuGramCaptureService enum anchor is not unique")
    capture_service_text = capture_service_text.replace(enum_anchor, enum_anchor + diagnostic_method, 1)

old_capture_guard = """        guard !messages.isEmpty else {
            return
        }
        let settingsStore = try? AyuGramRuntime.makeSettingsStore(accountID: accountID)
        guard settingsStore?.settings.saveDeletedMessages != false else {
            return
        }
"""
new_capture_guard = """        guard !messages.isEmpty else {
            recordDeletedRouteDiagnostic("capture-empty", received: 0)
            return
        }
        recordDeletedRouteDiagnostic("capture-enter", received: messages.count)
        let settingsStore = try? AyuGramRuntime.makeSettingsStore(accountID: accountID)
        guard settingsStore?.settings.saveDeletedMessages != false else {
            recordDeletedRouteDiagnostic("capture-disabled", received: messages.count)
            return
        }
"""
if old_capture_guard in capture_service_text:
    capture_service_text = capture_service_text.replace(old_capture_guard, new_capture_guard, 1)
elif 'recordDeletedRouteDiagnostic("capture-enter"' not in capture_service_text:
    raise SystemExit("AyuGram capture guard anchor not found")

old_append = "        _ = AyuGramPostboxHistoryStore.appendDeleted(transaction: transaction, messages: snapshots)\n"
new_append = "        let stored = AyuGramPostboxHistoryStore.appendDeleted(transaction: transaction, messages: snapshots)\n        recordDeletedRouteDiagnostic(\"capture-append-called\", received: messages.count, mapped: snapshots.count, retained: stored.count)\n"
if old_append in capture_service_text:
    capture_service_text = capture_service_text.replace(old_append, new_append, 1)
elif 'recordDeletedRouteDiagnostic("capture-append-called"' not in capture_service_text:
    raise SystemExit("AyuGram capture append anchor not found")
CAPTURE_SERVICE.write_text(capture_service_text, encoding="utf-8")


# A bounded received-message cache closes the gap where a later server delete
# arrives after Telegram has already removed the Postbox row. This cache is
# separate from edited/deleted History so ordinary received messages never
# appear as revisions in the UI.
store_text = STORE.read_text(encoding="utf-8")
received_state = r'''public struct AyuPostboxReceivedMessageState: Codable, Equatable, Sendable {
    public var messages: [AyuMessage]

    public init(messages: [AyuMessage] = []) {
        self.messages = messages
    }
}

'''
if "public struct AyuPostboxReceivedMessageState" not in store_text:
    store_anchor = "public enum AyuGramPostboxHistoryStore {\n"
    if store_text.count(store_anchor) != 1:
        raise SystemExit("Received-message cache store enum anchor is not unique")
    store_text = store_text.replace(store_anchor, received_state + store_anchor, 1)

if 'private static let receivedKey = ValueBoxKey("ayugram.receivedMessageCache.v1")' not in store_text:
    store_text = replace_once(
        store_text,
        "    private static let maximumEntries = 5000\n",
        "    private static let maximumEntries = 5000\n    private static let receivedKey = ValueBoxKey(\"ayugram.receivedMessageCache.v1\")\n    private static let maximumReceivedEntries = 2500\n",
        "received-message cache preferences key"
    )

received_methods = r'''    @discardableResult
    public static func cacheReceived(transaction: Transaction, messages snapshots: [AyuMessage]) -> Int {
        guard !snapshots.isEmpty else { return 0 }
        var state = readReceived(transaction: transaction)
        var changed = 0

        for snapshot in snapshots {
            if let index = state.messages.firstIndex(where: {
                $0.userID == snapshot.userID
                    && $0.dialogID == snapshot.dialogID
                    && $0.topicID == snapshot.topicID
                    && $0.messageID == snapshot.messageID
            }) {
                if state.messages[index] != snapshot {
                    state.messages.remove(at: index)
                    state.messages.append(snapshot)
                    changed += 1
                }
            } else {
                state.messages.append(snapshot)
                changed += 1
            }
        }

        if state.messages.count > maximumReceivedEntries {
            state.messages = Array(state.messages.suffix(maximumReceivedEntries))
        }
        transaction.setPreferencesEntry(key: receivedKey, value: PreferencesEntry(state))
        return changed
    }

    @discardableResult
    public static func promoteReceivedToDeleted(
        transaction: Transaction,
        userID: Int64,
        ids: [MessageId]
    ) -> [AyuMessage] {
        guard !ids.isEmpty else { return [] }
        let keys = Set(ids.map { "\($0.peerId.toInt64()):\($0.id)" })
        var state = readReceived(transaction: transaction)
        let matches = state.messages.filter {
            $0.userID == userID && keys.contains("\($0.dialogID):\($0.messageID)")
        }
        guard !matches.isEmpty else { return [] }

        state.messages.removeAll {
            $0.userID == userID && keys.contains("\($0.dialogID):\($0.messageID)")
        }
        transaction.setPreferencesEntry(key: receivedKey, value: PreferencesEntry(state))

        let deletedAt = Int32(Date().timeIntervalSince1970)
        let snapshots = matches.map { message in
            AyuMessage(
                fakeID: 0,
                userID: message.userID,
                dialogID: message.dialogID,
                peerID: message.peerID,
                fromID: message.fromID,
                fromName: message.fromName,
                topicID: message.topicID,
                messageID: message.messageID,
                date: message.date,
                editDate: message.editDate,
                text: message.text,
                mediaPath: message.mediaPath,
                mimeType: message.mimeType,
                isDeleted: true,
                deletedAt: deletedAt
            )
        }
        return appendDeleted(transaction: transaction, messages: snapshots)
    }

    @discardableResult
    public static func promoteReceivedGlobalIDsToDeleted(
        transaction: Transaction,
        userID: Int64,
        globalIDs: [Int32],
        excluding resolvedMessageIds: [MessageId],
        allowedPeerNamespaces: Set<Int32>
    ) -> [AyuMessage] {
        guard !globalIDs.isEmpty else { return [] }
        let ids = Set(globalIDs)
        let resolved = Set(resolvedMessageIds.map { "\($0.peerId.toInt64()):\($0.id)" })
        var state = readReceived(transaction: transaction)
        let matches = state.messages.filter { message in
            guard message.userID == userID, ids.contains(message.messageID) else { return false }
            let key = "\(message.dialogID):\(message.messageID)"
            guard !resolved.contains(key) else { return false }
            let peer = PeerId(message.dialogID)
            return allowedPeerNamespaces.contains(peer.namespace._internalGetInt32Value())
        }
        guard !matches.isEmpty else { return [] }

        let matchKeys = Set(matches.map { "\($0.dialogID):\($0.messageID)" })
        state.messages.removeAll {
            $0.userID == userID && matchKeys.contains("\($0.dialogID):\($0.messageID)")
        }
        transaction.setPreferencesEntry(key: receivedKey, value: PreferencesEntry(state))

        let deletedAt = Int32(Date().timeIntervalSince1970)
        let snapshots = matches.map { message in
            AyuMessage(
                fakeID: 0,
                userID: message.userID,
                dialogID: message.dialogID,
                peerID: message.peerID,
                fromID: message.fromID,
                fromName: message.fromName,
                topicID: message.topicID,
                messageID: message.messageID,
                date: message.date,
                editDate: message.editDate,
                text: message.text,
                mediaPath: message.mediaPath,
                mimeType: message.mimeType,
                isDeleted: true,
                deletedAt: deletedAt
            )
        }
        return appendDeleted(transaction: transaction, messages: snapshots)
    }

    public static func removeReceivedGlobalIDs(
        transaction: Transaction,
        userID: Int64,
        globalIDs: [Int32],
        excluding resolvedMessageIds: [MessageId],
        allowedPeerNamespaces: Set<Int32>
    ) {
        guard !globalIDs.isEmpty else { return }
        let ids = Set(globalIDs)
        let resolved = Set(resolvedMessageIds.map { "\($0.peerId.toInt64()):\($0.id)" })
        var state = readReceived(transaction: transaction)
        let originalCount = state.messages.count
        state.messages.removeAll { message in
            guard message.userID == userID, ids.contains(message.messageID) else { return false }
            let key = "\(message.dialogID):\(message.messageID)"
            guard !resolved.contains(key) else { return false }
            let peer = PeerId(message.dialogID)
            return allowedPeerNamespaces.contains(peer.namespace._internalGetInt32Value())
        }
        if state.messages.count != originalCount {
            transaction.setPreferencesEntry(key: receivedKey, value: PreferencesEntry(state))
        }
    }

    public static func removeReceived(transaction: Transaction, userID: Int64, ids: [MessageId]) {
        guard !ids.isEmpty else { return }
        let keys = Set(ids.map { "\($0.peerId.toInt64()):\($0.id)" })
        var state = readReceived(transaction: transaction)
        let originalCount = state.messages.count
        state.messages.removeAll {
            $0.userID == userID && keys.contains("\($0.dialogID):\($0.messageID)")
        }
        if state.messages.count != originalCount {
            transaction.setPreferencesEntry(key: receivedKey, value: PreferencesEntry(state))
        }
    }

'''
if "public static func cacheReceived(transaction:" not in store_text:
    anchor = "    public static func clearDeleted(transaction:"
    if store_text.count(anchor) != 1:
        raise SystemExit("Received-message cache insertion anchor is not unique")
    store_text = store_text.replace(anchor, received_methods + anchor, 1)

if "private static func readReceived(transaction: Transaction)" not in store_text:
    final_close = store_text.rfind("\n}")
    if final_close < 0:
        raise SystemExit("Received-message cache store closing brace not found")
    read_method = r'''
    private static func readReceived(transaction: Transaction) -> AyuPostboxReceivedMessageState {
        return transaction.getPreferencesEntry(key: receivedKey)?.get(AyuPostboxReceivedMessageState.self)
            ?? AyuPostboxReceivedMessageState()
    }
'''
    store_text = store_text[:final_close] + "\n" + read_method + store_text[final_close:]
STORE.write_text(store_text, encoding="utf-8")

capture_service_text = CAPTURE_SERVICE.read_text(encoding="utf-8")
received_capture_methods = r'''    public static func cacheReceived(
        transaction: Transaction,
        mediaBox: MediaBox,
        messages: [Message],
        mediaCaptures: [AyuMessageMediaCapture],
        accountID: Int64,
        senderNames: [Int32: String] = [:],
        editDates: [Int32: Int32] = [:]
    ) {
        guard !messages.isEmpty else { return }
        let settingsStore = try? AyuGramRuntime.makeSettingsStore(accountID: accountID)
        guard settingsStore?.settings.saveDeletedMessages != false else {
            recordDeletedRouteDiagnostic("receive-cache-disabled", received: messages.count)
            return
        }

        var capturesByMessageID: [Int32: [AyuMediaResourceInfo]] = [:]
        for capture in mediaCaptures {
            capturesByMessageID[capture.messageID] = capture.resources
        }

        var snapshots: [AyuMessage] = []
        snapshots.reserveCapacity(messages.count)
        for message in messages {
            let editDate = editDates[message.id.id] ?? 0
            var mediaPath: String?
            var mimeType: String?
            if let resources = capturesByMessageID[message.id.id], !resources.isEmpty {
                let archived = AyuGramMediaArchive.archive(
                    mediaBox: mediaBox,
                    accountID: accountID,
                    dialogID: message.id.peerId.toInt64(),
                    messageID: message.id.id,
                    revisionKey: "received-\(editDate)",
                    resources: resources
                )
                mediaPath = archived.path
                mimeType = archived.mimeType
            }
            snapshots.append(AyuGramPostboxBridge.snapshot(
                message: message,
                accountID: accountID,
                fromName: senderNames[message.id.id],
                isDeleted: false,
                editDate: editDate,
                mediaPath: mediaPath,
                mimeType: mimeType
            ))
        }

        let cachedCount = AyuGramPostboxHistoryStore.cacheReceived(transaction: transaction, messages: snapshots)
        recordDeletedRouteDiagnostic(
            "receive-cache-stored",
            received: messages.count,
            mapped: snapshots.count,
            retained: cachedCount,
        )
    }

    public static func captureMissingDeletedFromCache(
        transaction: Transaction,
        ids: [MessageId],
        resolvedMessageIds: Set<MessageId>,
        accountID: Int64
    ) {
        let missingIds = ids.filter { !resolvedMessageIds.contains($0) }
        let settingsStore = try? AyuGramRuntime.makeSettingsStore(accountID: accountID)
        guard settingsStore?.settings.saveDeletedMessages != false else {
            AyuGramPostboxHistoryStore.removeReceived(transaction: transaction, userID: accountID, ids: ids)
            recordDeletedRouteDiagnostic("capture-cache-disabled", received: missingIds.count)
            return
        }
        let recovered = AyuGramPostboxHistoryStore.promoteReceivedToDeleted(
            transaction: transaction,
            userID: accountID,
            ids: missingIds
        )
        recordDeletedRouteDiagnostic(
            "capture-cache-recovered",
            received: missingIds.count,
            mapped: recovered.count,
            retained: recovered.count,
            missing: max(0, missingIds.count - recovered.count)
        )
        AyuGramPostboxHistoryStore.removeReceived(transaction: transaction, userID: accountID, ids: ids)
    }

    public static func captureGlobalDeletedFromCache(
        transaction: Transaction,
        ids: [Int32],
        excluding resolvedMessageIds: [MessageId],
        accountID: Int64,
        allowedPeerNamespaces: Set<Int32>
    ) {
        let settingsStore = try? AyuGramRuntime.makeSettingsStore(accountID: accountID)
        guard settingsStore?.settings.saveDeletedMessages != false else {
            AyuGramPostboxHistoryStore.removeReceivedGlobalIDs(
                transaction: transaction,
                userID: accountID,
                globalIDs: ids,
                excluding: resolvedMessageIds,
                allowedPeerNamespaces: allowedPeerNamespaces
            )
            recordDeletedRouteDiagnostic("global-cache-disabled", received: ids.count)
            return
        }
        let recovered = AyuGramPostboxHistoryStore.promoteReceivedGlobalIDsToDeleted(
            transaction: transaction,
            userID: accountID,
            globalIDs: ids,
            excluding: resolvedMessageIds,
            allowedPeerNamespaces: allowedPeerNamespaces
        )
        recordDeletedRouteDiagnostic(
            "global-cache-recovered",
            received: ids.count,
            mapped: recovered.count,
            retained: recovered.count,
            missing: max(0, ids.count - recovered.count)
        )
    }

'''
if "public static func cacheReceived(" not in capture_service_text:
    capture_anchor = "    public static func captureDeleted("
    if capture_service_text.count(capture_anchor) != 1:
        raise SystemExit("AyuGram received-capture service anchor is not unique")
    capture_service_text = capture_service_text.replace(capture_anchor, received_capture_methods + capture_anchor, 1)
CAPTURE_SERVICE.write_text(capture_service_text, encoding="utf-8")


# 1) Preserve only server-delivered deleted messages in the local Postbox.
# Interactive deletion from this device keeps Telegram's ordinary delete behavior.
delete_text = DELETE.read_text(encoding="utf-8")
old_signature = (
    "public func _internal_deleteMessages(transaction: Transaction, mediaBox: MediaBox, ids: [MessageId], "
    "deleteMedia: Bool = true, manualAddMessageThreadStatsDifference: ((MessageThreadKey, Int, Int) -> Void)? = nil, "
    "ayuAccountID: Int64? = nil) {"
)
new_signature = (
    "@discardableResult\n"
    "public func _internal_deleteMessages(transaction: Transaction, mediaBox: MediaBox, ids: [MessageId], "
    "deleteMedia: Bool = true, manualAddMessageThreadStatsDifference: ((MessageThreadKey, Int, Int) -> Void)? = nil, "
    "ayuAccountID: Int64? = nil, preserveDeletedMessagesInChat: Bool = false) -> Set<MessageId> {"
)
delete_text = replace_once(delete_text, old_signature, new_signature, "deleted-message helper signature")

retention_block = r'''    var ayuRetainedDeletedMessageIds = Set<MessageId>()
    if preserveDeletedMessagesInChat, let ayuAccountID {
        let settingsAllowRetention = (try? AyuGramRuntime.makeSettingsStore(accountID: ayuAccountID))?.settings.saveDeletedMessages != false
        if settingsAllowRetention {
            var missing = 0
            var secretMedia = 0
            var alreadyRetained = 0

            for id in ids {
                guard let message = transaction.getMessage(id) else {
                    missing += 1
                    continue
                }
                if message.containsSecretMedia {
                    secretMedia += 1
                    continue
                }

                var wasAlreadyRetained = false
                transaction.updateMessage(id, update: { currentMessage in
                    var attributes = currentMessage.attributes
                    if attributes.contains(where: { ($0 as? EditedMessageAttribute)?.date == Int32.min }) {
                        wasAlreadyRetained = true
                        return .skip
                    }
                    // Hidden sentinel: it identifies a local tombstone without changing Telegram's edit date.
                    attributes.append(EditedMessageAttribute(date: Int32.min, isHidden: true))

                    var storeForwardInfo: StoreMessageForwardInfo?
                    if let forwardInfo = currentMessage.forwardInfo {
                        storeForwardInfo = StoreMessageForwardInfo(
                            authorId: forwardInfo.author?.id,
                            sourceId: forwardInfo.source?.id,
                            sourceMessageId: forwardInfo.sourceMessageId,
                            date: forwardInfo.date,
                            authorSignature: forwardInfo.authorSignature,
                            psaType: forwardInfo.psaType,
                            flags: forwardInfo.flags
                        )
                    }
                    return .update(StoreMessage(
                        id: currentMessage.id,
                        customStableId: nil,
                        globallyUniqueId: currentMessage.globallyUniqueId,
                        groupingKey: currentMessage.groupingKey,
                        threadId: currentMessage.threadId,
                        timestamp: currentMessage.timestamp,
                        flags: StoreMessageFlags(currentMessage.flags),
                        tags: currentMessage.tags,
                        globalTags: currentMessage.globalTags,
                        localTags: currentMessage.localTags,
                        forwardInfo: storeForwardInfo,
                        authorId: currentMessage.author?.id,
                        text: currentMessage.text,
                        attributes: attributes,
                        media: currentMessage.media
                    ))
                })
                if wasAlreadyRetained {
                    alreadyRetained += 1
                }
                ayuRetainedDeletedMessageIds.insert(id)
            }

            let peerNamespace = ids.first.map { Int($0.peerId.namespace._internalGetInt32Value()) }
            AyuGramCaptureService.recordDeletedRouteDiagnostic(
                "peer-retention-summary",
                received: ids.count,
                mapped: ids.count - missing,
                retained: ayuRetainedDeletedMessageIds.count,
                missing: missing,
                secretMedia: secretMedia,
                alreadyRetained: alreadyRetained,
                peerNamespace: peerNamespace
            )
        } else {
            AyuGramCaptureService.recordDeletedRouteDiagnostic("peer-retention-disabled", received: ids.count)
        }
    }

'''

delete_function_start = delete_text.find("public func _internal_deleteMessages(")
if delete_function_start < 0:
    raise SystemExit("Target _internal_deleteMessages function was not found")
delete_function_brace = delete_text.find("{", delete_function_start)
if delete_function_brace < 0:
    raise SystemExit("Target _internal_deleteMessages opening brace was not found")
delete_function_end = matching_delimiter(delete_text, delete_function_brace, "{", "}") + 1
delete_function = delete_text[delete_function_start:delete_function_end]
delete_function = replace_once(
    delete_function,
    "    var resourceIds: [MediaResourceId] = []\n",
    retention_block + "    var resourceIds: [MediaResourceId] = []\n",
    "deleted-message local retention block"
)
delete_function = replace_once(
    delete_function,
    "    for id in ids {\n        if id.peerId.namespace == Namespaces.Peer.CloudChannel && id.namespace == Namespaces.Message.Cloud {",
    "    for id in ids where !ayuRetainedDeletedMessageIds.contains(id) {\n        if id.peerId.namespace == Namespaces.Peer.CloudChannel && id.namespace == Namespaces.Message.Cloud {",
    "exclude retained messages from channel thread-stat decrements"
)
delete_text = delete_text[:delete_function_start] + delete_function + delete_text[delete_function_end:]
delete_text = replace_once(
    delete_text,
    "    transaction.deleteMessages(ids, forEachMedia: { _ in\n    })",
    """    let idsToDelete = ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }
    transaction.deleteMessages(idsToDelete, forEachMedia: { _ in
    })
    return ayuRetainedDeletedMessageIds""",
    "filtered Postbox deletion"
)
DELETE.write_text(delete_text, encoding="utf-8")

CACHE_HELPER_SOURCE = r'''public func _internal_cacheAyuGramReceivedMessages(transaction: Transaction, mediaBox: MediaBox, ids: [MessageId], ayuAccountID: Int64) {
    guard !ids.isEmpty else { return }
    let resolvedMessages = ids.compactMap { transaction.getMessage($0) }
    let messages = resolvedMessages.filter { message in
        guard !message.containsSecretMedia else { return false }
        // A locally retained deletion is already archived; do not feed it back
        // into the live receive cache whenever the conversation is loaded.
        return !message.attributes.contains(where: {
            guard let attribute = $0 as? EditedMessageAttribute else { return false }
            return attribute.date == Int32.min && attribute.isHidden
        })
    }
    guard !messages.isEmpty else { return }

    // Message IDs are only unique inside a peer. Keep sender/media maps peer-scoped
    // because chat-list hole batches can contain the same numeric message ID from
    // several different groups.
    let peerMessageGroups = Dictionary(grouping: messages, by: { $0.id.peerId })
    for peerMessages in peerMessageGroups.values {
        var senderNames: [Int32: String] = [:]
        var editDates: [Int32: Int32] = [:]
        var mediaCaptures: [AyuMessageMediaCapture] = []

        for message in peerMessages {
            editDates[message.id.id] = message.attributes.compactMap { ($0 as? EditedMessageAttribute)?.date }.max() ?? 0
            if let author = message.author {
                let name: String?
                if let user = author as? TelegramUser {
                    let parts = [user.firstName, user.lastName].compactMap { $0 }.filter { !$0.isEmpty }
                    name = parts.isEmpty ? nil : parts.joined(separator: " ")
                } else if let channel = author as? TelegramChannel {
                    name = channel.title
                } else if let group = author as? TelegramGroup {
                    name = group.title
                } else {
                    name = nil
                }
                if let name, !name.isEmpty {
                    senderNames[message.id.id] = name
                }
            }

            var resources: [AyuMediaResourceInfo] = []
            for media in message.effectiveMedia {
                if let image = media as? TelegramMediaImage,
                   let representation = image.representations.max(by: {
                       Int64($0.dimensions.width) * Int64($0.dimensions.height)
                           < Int64($1.dimensions.width) * Int64($1.dimensions.height)
                   }) {
                    resources.append(AyuMediaResourceInfo(id: representation.resource.id.stringRepresentation, mimeType: "image/jpeg"))
                } else if let file = media as? TelegramMediaFile {
                    resources.append(AyuMediaResourceInfo(id: file.resource.id.stringRepresentation, mimeType: file.mimeType))
                }
            }
            if !resources.isEmpty {
                var seen: Set<String> = []
                resources = resources.filter { seen.insert($0.id).inserted }
                mediaCaptures.append(AyuMessageMediaCapture(messageID: message.id.id, resources: resources))
            }
        }

        AyuGramCaptureService.cacheReceived(
            transaction: transaction,
            mediaBox: mediaBox,
            messages: peerMessages,
            mediaCaptures: mediaCaptures,
            accountID: ayuAccountID,
            senderNames: senderNames,
            editDates: editDates
        )
    }
}

'''


# Cache eligible group/channel/private messages as they enter Postbox, before any
# later server delete update can refer to an ID whose row is no longer present.
delete_text = DELETE.read_text(encoding="utf-8")
cache_helper_signature = "public func _internal_cacheAyuGramReceivedMessages("
if cache_helper_signature not in delete_text:
    capture_helper_marker = "public func _internal_captureDeletedMessages("
    capture_helper_start = delete_text.find(capture_helper_marker)
    if capture_helper_start < 0:
        raise SystemExit("Deleted-message capture helper missing before receive-cache helper insertion")
    delete_text = delete_text[:capture_helper_start] + CACHE_HELPER_SOURCE + delete_text[capture_helper_start:]

capture_helper_start = delete_text.find("public func _internal_captureDeletedMessages(")
if capture_helper_start < 0:
    raise SystemExit("Deleted-message capture helper missing for cache fallback wiring")
capture_helper_brace = delete_text.find("{", capture_helper_start)
capture_helper_end = matching_delimiter(delete_text, capture_helper_brace, "{", "}") + 1
capture_helper = delete_text[capture_helper_start:capture_helper_end]
resolved_line = "let resolvedMessages = ids.compactMap { transaction.getMessage($0) }"
fallback_call = """    AyuGramCaptureService.captureMissingDeletedFromCache(
        transaction: transaction,
        ids: ids,
        resolvedMessageIds: Set(resolvedMessages.map { $0.id }),
        accountID: ayuAccountID
    )
"""
if "captureMissingDeletedFromCache(" not in capture_helper:
    if resolved_line not in capture_helper:
        raise SystemExit("Capture helper does not expose its original resolved IDs for cache fallback")
    capture_call_marker = "AyuGramCaptureService.captureDeleted("
    capture_call_start = capture_helper.find(capture_call_marker)
    if capture_call_start < 0:
        raise SystemExit("Capture service call missing from deleted-message helper")
    capture_call_open = capture_helper.find("(", capture_call_start)
    capture_call_end = matching_delimiter(capture_helper, capture_call_open, "(", ")") + 1
    after_call = capture_helper.find("\n", capture_call_end)
    if after_call < 0:
        raise SystemExit("Capture service call line ending missing")
    capture_helper = capture_helper[:after_call + 1] + fallback_call + capture_helper[after_call + 1:]
delete_text = delete_text[:capture_helper_start] + capture_helper + delete_text[capture_helper_end:]
DELETE.write_text(delete_text, encoding="utf-8")


state_text = STATE.read_text(encoding="utf-8")
state_text = replace_once(
    state_text,
    "            case let .updateDeleteMessages(updateDeleteMessagesData):\n                updatedState.deleteMessagesWithGlobalIds(updateDeleteMessagesData.messages)",
    "            case let .updateDeleteMessages(updateDeleteMessagesData):\n                AyuGramCaptureService.recordDeletedRouteDiagnostic(\"global-update-arrived\", received: updateDeleteMessagesData.messages.count)\n                updatedState.deleteMessagesWithGlobalIds(updateDeleteMessagesData.messages)",
    "generic global delete update arrival diagnostics"
)
global_helper_signature = "public func _internal_retainDeletedMessagesWithGlobalIds("
if global_helper_signature not in state_text:
    state_import_anchor = "import AyuGramIOS\n"
    if state_import_anchor not in state_text:
        raise SystemExit("AccountStateManagementUtils AyuGramIOS import anchor not found")
    global_retain_helper = r'''public func _internal_retainDeletedMessagesWithGlobalIds(transaction: Transaction, ids: [Int32], accountID: Int64) -> Set<Int32> {
    var retainedGlobalIds = Set<Int32>()
    guard (try? AyuGramRuntime.makeSettingsStore(accountID: accountID))?.settings.saveDeletedMessages != false else {
        AyuGramCaptureService.recordDeletedRouteDiagnostic("global-retention-disabled", received: ids.count)
        return retainedGlobalIds
    }

    var missing = 0
    var secretMedia = 0
    var alreadyRetained = 0

    for globalID in ids {
        guard let messageID = transaction.messageIdsForGlobalIds([globalID]).first,
              let message = transaction.getMessage(messageID) else {
            missing += 1
            continue
        }
        if message.containsSecretMedia {
            secretMedia += 1
            continue
        }

        var wasAlreadyRetained = false
        transaction.updateMessage(messageID, update: { currentMessage in
            var attributes = currentMessage.attributes
            if attributes.contains(where: { ($0 as? EditedMessageAttribute)?.date == Int32.min }) {
                wasAlreadyRetained = true
                return .skip
            }
            attributes.append(EditedMessageAttribute(date: Int32.min, isHidden: true))

            var storeForwardInfo: StoreMessageForwardInfo?
            if let forwardInfo = currentMessage.forwardInfo {
                storeForwardInfo = StoreMessageForwardInfo(
                    authorId: forwardInfo.author?.id,
                    sourceId: forwardInfo.source?.id,
                    sourceMessageId: forwardInfo.sourceMessageId,
                    date: forwardInfo.date,
                    authorSignature: forwardInfo.authorSignature,
                    psaType: forwardInfo.psaType,
                    flags: forwardInfo.flags
                )
            }
            return .update(StoreMessage(
                id: currentMessage.id,
                customStableId: nil,
                globallyUniqueId: currentMessage.globallyUniqueId,
                groupingKey: currentMessage.groupingKey,
                threadId: currentMessage.threadId,
                timestamp: currentMessage.timestamp,
                flags: StoreMessageFlags(currentMessage.flags),
                tags: currentMessage.tags,
                globalTags: currentMessage.globalTags,
                localTags: currentMessage.localTags,
                forwardInfo: storeForwardInfo,
                authorId: currentMessage.author?.id,
                text: currentMessage.text,
                attributes: attributes,
                media: currentMessage.media
            ))
        })
        if wasAlreadyRetained {
            alreadyRetained += 1
        }
        retainedGlobalIds.insert(globalID)
    }

    AyuGramCaptureService.recordDeletedRouteDiagnostic(
        "global-retention-summary",
        received: ids.count,
        mapped: ids.count - missing,
        retained: retainedGlobalIds.count,
        missing: missing,
        secretMedia: secretMedia,
        alreadyRetained: alreadyRetained
    )
    return retainedGlobalIds
}'''
    if "public func _internal_retainDeletedMessagesWithGlobalIds(" not in state_text:
        state_import_anchor = "import AyuGramIOS\n"
        if state_import_anchor not in state_text:
            raise SystemExit("AccountStateManagementUtils AyuGramIOS import anchor not found")
        state_text = state_text.replace(state_import_anchor, state_import_anchor + "\n" + global_retain_helper + "\n", 1)

# Share the exact server-delete operations between replayFinalState and its runtime test.
server_handlers = r"""
public func _internal_applyAyuGramServerDeleteMessages(transaction: Transaction, mediaBox: MediaBox, ids: [MessageId], accountID: Int64, manualAddMessageThreadStatsDifference: ((MessageThreadKey, Int, Int) -> Void)? = nil) -> Set<MessageId> {
    // Record which rows exist before Telegram's deletion pass. The direct peer-ID
    // route needs the same receive-cache fallback as the Global-ID route, but only
    // for rows that were already absent; otherwise we would duplicate snapshots
    // that _internal_deleteMessages captures synchronously below.
    let resolvedMessageIds = Set(ids.compactMap { transaction.getMessage($0)?.id })
    let retained = _internal_deleteMessages(
        transaction: transaction,
        mediaBox: mediaBox,
        ids: ids,
        manualAddMessageThreadStatsDifference: manualAddMessageThreadStatsDifference,
        ayuAccountID: accountID,
        preserveDeletedMessagesInChat: true
    )
    AyuGramCaptureService.captureMissingDeletedFromCache(
        transaction: transaction,
        ids: ids,
        resolvedMessageIds: resolvedMessageIds,
        accountID: accountID
    )
    AyuGramCaptureService.recordDeletedRouteDiagnostic(
        "peer-delete-replay",
        received: ids.count,
        mapped: resolvedMessageIds.count,
        retained: retained.count
    )
    return retained
}

public func _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(transaction: Transaction, mediaBox: MediaBox, ids: [Int32], accountID: Int64) -> Set<Int32> {
    let messageIds = transaction.messageIdsForGlobalIds(ids)
    AyuGramCaptureService.recordDeletedRouteDiagnostic("global-delete-replay", received: ids.count, mapped: messageIds.count)
    _internal_captureDeletedMessages(transaction: transaction, mediaBox: mediaBox, ids: messageIds, ayuAccountID: accountID)
    AyuGramCaptureService.captureGlobalDeletedFromCache(
        transaction: transaction,
        ids: ids,
        excluding: messageIds,
        accountID: accountID,
        allowedPeerNamespaces: Set([
            Namespaces.Peer.CloudUser._internalGetInt32Value(),
            Namespaces.Peer.CloudGroup._internalGetInt32Value()
        ])
    )
    let retained = _internal_retainDeletedMessagesWithGlobalIds(transaction: transaction, ids: ids, accountID: accountID)
    AyuGramCaptureService.recordDeletedRouteDiagnostic("global-delete-retained", received: ids.count, mapped: messageIds.count, retained: retained.count)
    return retained
}
"""
if "_internal_applyAyuGramServerDeleteMessages(" not in state_text:
    helper_start = state_text.find(global_helper_signature)
    if helper_start < 0:
        raise SystemExit("Global-ID retention helper not found before shared server handlers")
    helper_brace = state_text.find("{", helper_start)
    helper_end = matching_delimiter(state_text, helper_brace, "{", "}") + 1
    state_text = state_text[:helper_end] + "\n\n" + server_handlers + state_text[helper_end:]
elif "_internal_applyAyuGramServerDeleteMessagesWithGlobalIds(" not in state_text:
    raise SystemExit("Only one shared server-delete handler exists; refusing partial update")
direct_delete_start = state_text.find("case let .DeleteMessages(ids):")
direct_delete_end = state_text.find("case let .UpdateMinAvailableMessage", direct_delete_start)
if direct_delete_start < 0 or direct_delete_end < 0:
    raise SystemExit("Server DeleteMessages source block boundaries not found")
direct_delete_block = state_text[direct_delete_start:direct_delete_end]
old_direct_delete_call = """                _internal_deleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, manualAddMessageThreadStatsDifference: { id, add, remove in
                    addMessageThreadStatsDifference(threadKey: id, remove: remove, addedMessagePeer: nil, addedMessageId: nil, isOutgoing: false)
                }, ayuAccountID: accountPeerId.toInt64())"""
new_direct_delete_call = """                let ayuRetainedDeletedMessageIds = _internal_applyAyuGramServerDeleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, accountID: accountPeerId.toInt64(), manualAddMessageThreadStatsDifference: { id, add, remove in
                    addMessageThreadStatsDifference(threadKey: id, remove: remove, addedMessagePeer: nil, addedMessageId: nil, isOutgoing: false)
                })"""
direct_delete_block = replace_once(
    direct_delete_block,
    old_direct_delete_call,
    new_direct_delete_call,
    "shared server DeleteMessages handler"
)
direct_delete_block = replace_once(
    direct_delete_block,
    "                deletedMessageIds.append(contentsOf: ids.map { .messageId($0) })",
    "                deletedMessageIds.append(contentsOf: ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }.map { .messageId($0) })",
    "exclude retained rows from removed-message notifications"
)
state_text = state_text[:direct_delete_start] + direct_delete_block + state_text[direct_delete_end:]

global_capture_anchor = "_internal_captureDeletedMessages(transaction: transaction, mediaBox: mediaBox, ids: messageIds, ayuAccountID: accountPeerId.toInt64())\n"
global_handler_call = "                let ayuRetainedGlobalIds = _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(transaction: transaction, mediaBox: mediaBox, ids: ids, accountID: accountPeerId.toInt64())"
if global_capture_anchor in state_text:
    state_text = state_text.replace(global_capture_anchor, global_handler_call + "\n", 1)
elif global_handler_call not in state_text:
    raise SystemExit("Global-ID event is not routed through the shared production handler")
unused_global_lookup = "                let messageIds = transaction.messageIdsForGlobalIds(ids)\n"
if unused_global_lookup in state_text:
    state_text = state_text.replace(unused_global_lookup, "", 1)
old_global_delete_call = "transaction.deleteMessagesWithGlobalIds(ids, forEachMedia: { media in"
new_global_delete_call = """let ayuGlobalIdsToDelete = ids.filter { !ayuRetainedGlobalIds.contains($0) }
                transaction.deleteMessagesWithGlobalIds(ayuGlobalIdsToDelete, forEachMedia: { media in"""
if old_global_delete_call not in state_text:
    raise SystemExit("Global-ID deletion call anchor not found")
state_text = state_text.replace(old_global_delete_call, new_global_delete_call, 1)
state_text = replace_once(
    state_text,
    "deletedMessageIds.append(contentsOf: ids.map { .global($0) })",
    "deletedMessageIds.append(contentsOf: ids.filter { !ayuRetainedGlobalIds.contains($0) }.map { .global($0) })",
    "exclude retained global IDs from removed-message notifications"
)

# Normal channel deletes are retained when PTS is contiguous. Stale events are
# replayed locally for retention without changing PTS; gaps and unknown state
# remain on Telegram's pollChannel path and are handled when the difference returns.
channel_delete_case = find_case_block(
    state_text,
    "case let .updateDeleteChannelMessages(updateDeleteChannelMessagesData):",
    "previousState.pts + ptsCount == pts"
)
if channel_delete_case is None:
    raise SystemExit("Channel/supergroup updateDeleteChannelMessages PTS handler was not found")
channel_delete_start, channel_delete_end, channel_delete_block = channel_delete_case
channel_delete_block = replace_once(
    channel_delete_block,
    "let peerId = PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(channelId))\n",
    "let peerId = PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(channelId))\n                let channelDeletedMessageIds = messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) })\n                AyuGramCaptureService.recordDeletedRouteDiagnostic(\"channel-update-arrived\", received: messages.count, mapped: channelDeletedMessageIds.count)\n",
    "channel deletion message IDs"
)
# A stale update is already reflected in channel PTS. Replay only the local message
# operation: the AyuGram wrapper retains eligible rows, leaves PTS untouched, and
# still applies ordinary Telegram deletion when retention is disabled or restricted.
channel_delete_block = replace_once(
    channel_delete_block,
    "updatedState.deleteMessages(messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) }))",
    "updatedState.deleteMessages(channelDeletedMessageIds)",
    "contiguous channel delete operation"
)
channel_delete_block = replace_once(
    channel_delete_block,
    "if previousState.pts >= pts {\n",
    "if previousState.pts >= pts {\n                        // Channel PTS is already beyond this deletion.\n                        // Replay only local message persistence; do not touch PTS.\n                        AyuGramCaptureService.recordDeletedRouteDiagnostic(\"channel-pts-stale-replay\", received: messages.count, mapped: channelDeletedMessageIds.count)\n                        updatedState.deleteMessages(channelDeletedMessageIds)\n",
    "safe stale-PTS deleted-message retention"
)
stale_delete_log_old = 'Logger.shared.log("State", "channel \\(peerId) (\\((updatedState.peers[peerId] as? TelegramChannel)?.title ?? "nil")) skip old delete update")'
stale_delete_log_new = 'Logger.shared.log("State", "channel \\(peerId) (\\((updatedState.peers[peerId] as? TelegramChannel)?.title ?? "nil")) replay stale delete locally for AyuGram retention")'
channel_delete_block = replace_once(
    channel_delete_block,
    stale_delete_log_old,
    stale_delete_log_new,
    "accurate stale-PTS log message"
)
channel_delete_block = replace_once(
    channel_delete_block,
    "if !missingUpdatesFromChannels.contains(peerId) {\n",
    "AyuGramCaptureService.recordDeletedRouteDiagnostic(\"channel-pts-gap\", received: messages.count, mapped: channelDeletedMessageIds.count)\n                        if !missingUpdatesFromChannels.contains(peerId) {\n",
    "channel PTS gap diagnostics"
)
channel_delete_block = replace_once(
    channel_delete_block,
    "if case .none = channelsToPoll[peerId] {\n",
    "AyuGramCaptureService.recordDeletedRouteDiagnostic(\"channel-pts-unknown\", received: messages.count, mapped: channelDeletedMessageIds.count)\n                    if case .none = channelsToPoll[peerId] {\n",
    "unknown channel PTS diagnostics"
)
# PTS gaps and unknown channel state remain on Telegram's normal poll path.
# The difference response queues the deletion in order, then reaches the
# same shared AyuGram retention handler.
state_text = state_text[:channel_delete_start] + channel_delete_block + state_text[channel_delete_end:]
poll_delete_anchor = """let peerId = peer.id
                        updatedState.deleteMessages(updateDeleteChannelMessagesData.messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) }))"""
poll_delete_replacement = """let peerId = peer.id
                        AyuGramCaptureService.recordDeletedRouteDiagnostic("channel-difference-delete", received: updateDeleteChannelMessagesData.messages.count)
                        updatedState.deleteMessages(updateDeleteChannelMessagesData.messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) }))"""
state_text = replace_once(
    state_text,
    poll_delete_anchor,
    poll_delete_replacement,
    "channel difference delete replay diagnostics"
)

# Capture received messages after Postbox has accepted the AddMessages operation.
# Transaction.addMessages updates the in-transaction history table synchronously,
# so the shared helper can read the just-added rows without an asynchronous race.
replay_start = state_text.find("func replayFinalState(")
if replay_start < 0:
    raise SystemExit("replayFinalState not found for received-message cache wiring")
replay_brace = state_text.find("{", replay_start)
replay_end = matching_delimiter(state_text, replay_brace, "{", "}") + 1
replay_body = state_text[replay_start:replay_end]
add_messages_anchor = "                let _ = transaction.addMessages(messages, location: location)\n"
cache_call = """                let ayuReceivedMessageIds = messages.compactMap { message -> MessageId? in
                    guard case let .Id(id) = message.id, id.namespace == Namespaces.Message.Cloud else {
                        return nil
                    }
                    let peerNamespace = id.peerId.namespace
                    guard peerNamespace == Namespaces.Peer.CloudUser
                        || peerNamespace == Namespaces.Peer.CloudGroup
                        || peerNamespace == Namespaces.Peer.CloudChannel else {
                        return nil
                    }
                    return id
                }
                if !ayuReceivedMessageIds.isEmpty {
                    _internal_cacheAyuGramReceivedMessages(
                        transaction: transaction,
                        mediaBox: mediaBox,
                        ids: ayuReceivedMessageIds,
                        ayuAccountID: accountPeerId.toInt64()
                    )
                }
"""
if "AyuGram pre-delete receive cache" not in replay_body:
    if replay_body.count(add_messages_anchor) != 1:
        raise SystemExit("replayFinalState AddMessages insertion anchor is not unique")
    replay_body = replay_body.replace(
        add_messages_anchor,
        add_messages_anchor + "                // AyuGram pre-delete receive cache\n" + cache_call,
        1
    )
    state_text = state_text[:replay_start] + replay_body + state_text[replay_end:]


# Edited messages replace the Postbox row. Refresh the received-message cache
# only after Telegram's normal edit update has been applied, so a later delete
# archives the newest permitted revision rather than a stale pre-edit snapshot.
edit_case_start = state_text.find("case let .EditMessage(id, message):", replay_start)
if edit_case_start < 0:
    raise SystemExit("replayFinalState EditMessage operation is missing")
edit_case_end = state_text.find("case let .UpdateMessagePoll", edit_case_start)
if edit_case_end < 0:
    raise SystemExit("replayFinalState EditMessage operation end not found")
edit_block = state_text[edit_case_start:edit_case_end]
edit_cache_signature = "_internal_cacheAyuGramReceivedMessages("
if edit_cache_signature not in edit_block:
    update_signature = "transaction.updateMessage(id, update: { previousMessage in"
    update_start = edit_block.find(update_signature)
    if update_start < 0:
        raise SystemExit("EditMessage Postbox update closure not found")
    update_open = edit_block.find("(", update_start)
    update_end = matching_delimiter(edit_block, update_open, "(", ")") + 1
    cache_call = "\n".join([
        "",
        "                // Refresh cached copy after the current Postbox revision is installed.",
        "                if id.namespace == Namespaces.Message.Cloud {",
        "                    let peerNamespace = id.peerId.namespace",
        "                    if peerNamespace == Namespaces.Peer.CloudUser",
        "                        || peerNamespace == Namespaces.Peer.CloudGroup",
        "                        || peerNamespace == Namespaces.Peer.CloudChannel {",
        "                        _internal_cacheAyuGramReceivedMessages(",
        "                            transaction: transaction,",
        "                            mediaBox: mediaBox,",
        "                            ids: [id],",
        "                            ayuAccountID: accountPeerId.toInt64()",
        "                        )",
        "                    }",
        "                }",
    ])
    edit_block = edit_block[:update_end] + cache_call + edit_block[update_end:]
    state_text = state_text[:edit_case_start] + edit_block + state_text[edit_case_end:]


# The ordinary chat timeline is hydrated through fetchMessageHistoryHole rather
# than replayFinalState. Cache the messages on this path too; otherwise a row
# loaded from history could disappear before a later delete update reaches the
# state-manager route above.
holes_text = HOLES.read_text(encoding="utf-8")
if "import AyuGramIOS\n" not in holes_text:
    holes_text = ensure_swift_import(holes_text, "import Postbox", "import AyuGramIOS", "Holes AyuGramIOS import")
history_add_anchor = """                        let _ = transaction.addMessages(storeMessages, location: .Random)
                        let _ = transaction.addMessages(additionalMessages, location: .Random)
"""
history_cache_call = """                        // AyuGram history-hole receive cache: this is the normal loaded chat timeline.
                        let ayuLoadedMessageIds = (storeMessages + additionalMessages).compactMap { message -> MessageId? in
                            guard case let .Id(id) = message.id, id.namespace == Namespaces.Message.Cloud else {
                                return nil
                            }
                            let peerNamespace = id.peerId.namespace
                            guard peerNamespace == Namespaces.Peer.CloudUser
                                || peerNamespace == Namespaces.Peer.CloudGroup
                                || peerNamespace == Namespaces.Peer.CloudChannel else {
                                return nil
                            }
                            return id
                        }
                        if !ayuLoadedMessageIds.isEmpty {
                            _internal_cacheAyuGramReceivedMessages(
                                transaction: transaction,
                                mediaBox: postbox.mediaBox,
                                ids: ayuLoadedMessageIds,
                                ayuAccountID: accountPeerId.toInt64()
                            )
                        }
"""
if "AyuGram history-hole receive cache" not in holes_text:
    if holes_text.count(history_add_anchor) != 1:
        raise SystemExit(f"Expected one normal history-hole addMessages anchor, found {holes_text.count(history_add_anchor)}")
    holes_text = holes_text.replace(history_add_anchor, history_add_anchor + history_cache_call, 1)
    HOLES.write_text(holes_text, encoding="utf-8")

# Chat-list hole pages also carry the newest group/channel message previews.
# Cache those eligible rows before a later delete update can arrive while the
# user has not opened the chat yet.
chat_list_add_anchor = """            let _ = transaction.addMessages(fetchedChats.storeMessages, location: .UpperHistoryBlock)
            let _ = transaction.addMessages(additionalMessages, location: .Random)
"""
if "AyuGram chat-list preview receive cache" not in holes_text:
    if holes_text.count(chat_list_add_anchor) != 1:
        raise SystemExit(f"Expected one chat-list addMessages anchor, found {holes_text.count(chat_list_add_anchor)}")
    chat_list_cache = """            // AyuGram chat-list preview receive cache
            let ayuChatListMessageIds = (fetchedChats.storeMessages + additionalMessages).compactMap { message -> MessageId? in
                guard case let .Id(id) = message.id, id.namespace == Namespaces.Message.Cloud else {
                    return nil
                }
                let peerNamespace = id.peerId.namespace
                guard peerNamespace == Namespaces.Peer.CloudUser
                    || peerNamespace == Namespaces.Peer.CloudGroup
                    || peerNamespace == Namespaces.Peer.CloudChannel else {
                    return nil
                }
                return id
            }
            if !ayuChatListMessageIds.isEmpty {
                _internal_cacheAyuGramReceivedMessages(
                    transaction: transaction,
                    mediaBox: postbox.mediaBox,
                    ids: ayuChatListMessageIds,
                    ayuAccountID: accountPeerId.toInt64()
                )
            }
"""
    holes_text = holes_text.replace(
        chat_list_add_anchor,
        chat_list_add_anchor + chat_list_cache,
        1
    )
    HOLES.write_text(holes_text, encoding="utf-8")




# Explicitly fetched replies and message references are stored outside the
# ordinary history-hole loader. Cache them as well so group-topic and reply
# previews use the same pre-delete safety net.
thread_history_text = THREAD_HISTORY.read_text(encoding="utf-8")
if "import AyuGramIOS\n" not in thread_history_text:
    thread_history_text = ensure_swift_import(thread_history_text, "import Postbox", "import AyuGramIOS", "ReplyThreadHistory AyuGramIOS import")
thread_add_pattern = re.compile(
    r"(?m)^(?P<indent>[ \t]+)let _ = transaction\.addMessages\(parsedMessages, location: \.Random\)[ \t]*$"
)
thread_add_matches = list(thread_add_pattern.finditer(thread_history_text))
if not thread_add_matches:
    raise SystemExit("ReplyThreadHistory parsedMessages addMessages anchors not found")

thread_cache_lines = [
    "// AyuGram reply-thread receive cache",
    "let ayuReplyMessageIds = parsedMessages.compactMap { message -> MessageId? in",
    "    guard case let .Id(id) = message.id, id.namespace == Namespaces.Message.Cloud else {",
    "        return nil",
    "    }",
    "    let peerNamespace = id.peerId.namespace",
    "    guard peerNamespace == Namespaces.Peer.CloudUser",
    "        || peerNamespace == Namespaces.Peer.CloudGroup",
    "        || peerNamespace == Namespaces.Peer.CloudChannel else {",
    "        return nil",
    "    }",
    "    return id",
    "}",
    "if !ayuReplyMessageIds.isEmpty {",
    "    _internal_cacheAyuGramReceivedMessages(",
    "        transaction: transaction,",
    "        mediaBox: account.postbox.mediaBox,",
    "        ids: ayuReplyMessageIds,",
    "        ayuAccountID: accountPeerId.toInt64()",
    "    )",
    "}"
]

# Insert after each parsedMessages write that is actually present in this
# Telegram baseline. Some compatible source snapshots have one loader path,
# others have two; every present path must be cached, but do not invent a
# missing path or fail solely because the baseline has a different count.
for match in reversed(thread_add_matches):
    following = thread_history_text[match.end():]
    next_match = next((candidate for candidate in thread_add_matches if candidate.start() > match.start()), None)
    region = following if next_match is None else thread_history_text[match.end():next_match.start()]
    if "AyuGram reply-thread receive cache" not in region:
        indent = match.group("indent")
        cache = "\n".join(indent + line for line in thread_cache_lines)
        thread_history_text = thread_history_text[:match.end()] + "\n" + cache + thread_history_text[match.end():]

if thread_history_text.count("AyuGram reply-thread receive cache") != len(thread_add_matches):
    raise SystemExit(
        "ReplyThreadHistory cache coverage mismatch: "
        f"{thread_history_text.count('AyuGram reply-thread receive cache')} markers for "
        f"{len(thread_add_matches)} parsedMessages add paths"
    )
THREAD_HISTORY.write_text(thread_history_text, encoding="utf-8")


# Ensure generated Swift imports are real lines, not escaped backslash-n text.
for swift_path, swift_text in (
    (HOLES, holes_text),
    (THREAD_HISTORY, thread_history_text),
):
    if "import AyuGramIOS" not in swift_text.splitlines():
        raise SystemExit(f"{swift_path}: AyuGramIOS import was not inserted as its own Swift line")
    if r"\nimport AyuGramIOS" in swift_text:
        raise SystemExit(f"{swift_path}: literal \\n leaked into Swift import section")

load_messages_text = LOAD_MESSAGES.read_text(encoding="utf-8")
if "import AyuGramIOS\n" not in load_messages_text:
    load_messages_text = ensure_swift_import(load_messages_text, "import Postbox", "import AyuGramIOS", "LoadMessagesIfNecessary AyuGramIOS import")
if r"\nimport AyuGramIOS" in load_messages_text:
    raise SystemExit(f"{LOAD_MESSAGES}: literal \\n leaked into Swift import section")
if "import AyuGramIOS" not in load_messages_text.splitlines():
    raise SystemExit(f"{LOAD_MESSAGES}: AyuGramIOS import was not inserted as its own Swift line")
if "AyuGram history-hole receive cache" not in holes_text:
    raise SystemExit("Normal history-hole loader is missing the received-message cache")
if "AyuGram chat-list preview receive cache" not in holes_text:
    raise SystemExit("Chat-list preview loader is missing the received-message cache")
load_add_anchor = "                            _ = transaction.addMessages(storeMessages, location: .Random)\n"
if "AyuGram load-by-id receive cache" not in load_messages_text:
    if load_messages_text.count(load_add_anchor) != 1:
        raise SystemExit("LoadMessagesIfNecessary addMessages anchor is not unique")
    load_cache = """                            _ = transaction.addMessages(storeMessages, location: .Random)
                            // AyuGram load-by-id receive cache
                            let ayuLoadedByIdMessageIds = storeMessages.compactMap { message -> MessageId? in
                                guard case let .Id(id) = message.id, id.namespace == Namespaces.Message.Cloud else {
                                    return nil
                                }
                                let peerNamespace = id.peerId.namespace
                                guard peerNamespace == Namespaces.Peer.CloudUser
                                    || peerNamespace == Namespaces.Peer.CloudGroup
                                    || peerNamespace == Namespaces.Peer.CloudChannel else {
                                    return nil
                                }
                                return id
                            }
                            if !ayuLoadedByIdMessageIds.isEmpty {
                                _internal_cacheAyuGramReceivedMessages(
                                    transaction: transaction,
                                    mediaBox: postbox.mediaBox,
                                    ids: ayuLoadedByIdMessageIds,
                                    ayuAccountID: accountPeerId.toInt64()
                                )
                            }
"""
    load_messages_text = load_messages_text.replace(load_add_anchor, load_cache, 1)

if "AyuGram load-by-id receive cache" not in load_messages_text:
    raise SystemExit("Load-by-ID loader is missing the received-message cache")
LOAD_MESSAGES.write_text(load_messages_text, encoding="utf-8")
print("Verified load-by-ID receive-cache insertion after the Postbox AddMessages write.")

STATE.write_text(state_text, encoding="utf-8")
print(
    "Verified received-message cache imports and loaders: "
    f"history-hole + chat-list + {len(thread_add_matches)} reply-thread path(s) + load-by-ID."
)

# The engine-facing helper is Void; its call must not return the retained-ID set.
engine_text = ENGINE.read_text(encoding="utf-8")
engine_text = replace_once(
    engine_text,
    "            return _internal_deleteMessages(",
    "            _internal_deleteMessages(",
    "Void TelegramEngineMessages deleteMessages caller"
)
ENGINE.write_text(engine_text, encoding="utf-8")


# 2) Render the local deletion mark beside the original message time.
date_text = DATE_STATUS.read_text(encoding="utf-8")
date_text = replace_once(date_text, "        var edited: Bool\n", "        var edited: Bool\n        var isAyuGramDeleted: Bool\n", "date/status deleted-state argument")
date_text = replace_once(
    date_text,
    "            edited: Bool,\n            impressionCount: Int?,\n",
    "            edited: Bool,\n            isAyuGramDeleted: Bool = false,\n            impressionCount: Int?,\n",
    "date/status deleted-state initializer"
)
date_text = replace_once(
    date_text,
    "            self.edited = edited\n",
    "            self.edited = edited\n            self.isAyuGramDeleted = isAyuGramDeleted\n",
    "date/status deleted-state assignment"
)
date_text = replace_once(
    date_text,
    "            if arguments.edited {\n",
    """            if arguments.isAyuGramDeleted {
                updatedDateText = "🧹 \\(updatedDateText)"
            } else if arguments.edited {
""",
    "date/status broom rendering"
)
DATE_STATUS.write_text(date_text, encoding="utf-8")

bubble_text = BUBBLE.read_text(encoding="utf-8")
bubble_text = replace_once(
    bubble_text,
    """                var edited = false
                if item.content.firstMessageAttributes.updatingMedia != nil {
                    edited = true
                }
""",
    """                var edited = false
                var isAyuGramDeleted = false
                if item.content.firstMessageAttributes.updatingMedia != nil {
                    edited = true
                }
""",
    "chat bubble deleted-state variable"
)
bubble_text = replace_once(
    bubble_text,
    """                    if let attribute = attribute as? EditedMessageAttribute {
                        edited = !attribute.isHidden
""",
    """                    if let attribute = attribute as? EditedMessageAttribute {
                        if attribute.date == Int32.min {
                            isAyuGramDeleted = true
                            edited = false
                        } else {
                            edited = !attribute.isHidden
                        }
""",
    "chat bubble deletion sentinel detection"
)
bubble_text = replace_once(
    bubble_text,
    "                    edited: edited && !item.presentationData.isPreview,\n",
    "                    edited: edited && !item.presentationData.isPreview,\n                    isAyuGramDeleted: isAyuGramDeleted && !item.presentationData.isPreview,\n",
    "chat bubble date/status deleted-state argument"
)
BUBBLE.write_text(bubble_text, encoding="utf-8")

text_bubble_text = TEXT_BUBBLE.read_text(encoding="utf-8")
text_bubble_text = replace_once(
    text_bubble_text,
    """                var edited = false
                if item.attributes.updatingMedia != nil {
                    edited = true
                }
""",
    """                var edited = false
                var isAyuGramDeleted = false
                if item.attributes.updatingMedia != nil {
                    edited = true
                }
""",
    "text bubble deleted-state variable"
)
text_bubble_text = replace_once(
    text_bubble_text,
    """                    if let attribute = attribute as? EditedMessageAttribute {
                        edited = !attribute.isHidden
""",
    """                    if let attribute = attribute as? EditedMessageAttribute {
                        if attribute.date == Int32.min {
                            isAyuGramDeleted = true
                            edited = false
                        } else {
                            edited = !attribute.isHidden
                        }
""",
    "text bubble deletion sentinel detection"
)
text_bubble_text = replace_once(
    text_bubble_text,
    """                        edited: edited && !item.presentationData.isPreview,
""",
    """                        edited: edited && !item.presentationData.isPreview,
                        isAyuGramDeleted: isAyuGramDeleted && !item.presentationData.isPreview,
""",
    "text bubble deleted-state date/status argument"
)
TEXT_BUBBLE.write_text(text_bubble_text, encoding="utf-8")


# Media-only messages use ChatMessageMediaBubbleContentNode and then pass
# ChatMessageDateAndStatus through ChatMessageInteractiveMediaNode. They do
# not use the text-bubble date path above, so explicitly carry the tombstone
# marker through this separate image/video status pipeline.
media_bubble_text = MEDIA_BUBBLE.read_text(encoding="utf-8")
media_bubble_text = replace_once(
    media_bubble_text,
    """            var edited = false
            if item.attributes.updatingMedia != nil {
                edited = true
            }
""",
    """            var edited = false
            var isAyuGramDeleted = false
            if item.attributes.updatingMedia != nil {
                edited = true
            }
""",
    "media-only deleted-state variable"
)
media_bubble_text = replace_once(
    media_bubble_text,
    """                if let attribute = attribute as? EditedMessageAttribute {
                    if case .mosaic = preparePosition {
                    } else {
                        edited = !attribute.isHidden
                    }
""",
    """                if let attribute = attribute as? EditedMessageAttribute {
                    if attribute.date == Int32.min {
                        isAyuGramDeleted = true
                        edited = false
                    } else if case .mosaic = preparePosition {
                    } else {
                        edited = !attribute.isHidden
                    }
""",
    "media-only deleted sentinel detection"
)
media_bubble_text = replace_once(
    media_bubble_text,
    """                    edited: edited,
                    viewCount: viewCount,
""",
    """                    edited: edited,
                    isAyuGramDeleted: isAyuGramDeleted,
                    viewCount: viewCount,
""",
    "media-only status marker handoff"
)
MEDIA_BUBBLE.write_text(media_bubble_text, encoding="utf-8")

interactive_media_text = INTERACTIVE_MEDIA.read_text(encoding="utf-8")
interactive_media_text = replace_once(
    interactive_media_text,
    "    public var edited: Bool\n    public var viewCount: Int?\n",
    "    public var edited: Bool\n    public var isAyuGramDeleted: Bool\n    public var viewCount: Int?\n",
    "interactive media status marker property"
)
interactive_media_text = replace_once(
    interactive_media_text,
    "        edited: Bool,\n        viewCount: Int?,\n",
    "        edited: Bool,\n        isAyuGramDeleted: Bool = false,\n        viewCount: Int?,\n",
    "interactive media status marker initializer"
)
interactive_media_text = replace_once(
    interactive_media_text,
    "        self.edited = edited\n        self.viewCount = viewCount\n",
    "        self.edited = edited\n        self.isAyuGramDeleted = isAyuGramDeleted\n        self.viewCount = viewCount\n",
    "interactive media status marker assignment"
)
interactive_media_text = replace_once(
    interactive_media_text,
    "                    edited: dateAndStatus.edited && !presentationData.isPreview,\n                    impressionCount:",
    "                    edited: dateAndStatus.edited && !presentationData.isPreview,\n                    isAyuGramDeleted: dateAndStatus.isAyuGramDeleted && !presentationData.isPreview,\n                    impressionCount:",
    "interactive media status marker passed to date node"
)
INTERACTIVE_MEDIA.write_text(interactive_media_text, encoding="utf-8")


# 3) Remove the user-facing History list shortcuts. The Postbox store remains
# private and is still used for Before originals and local deleted-message state.
settings_text = SETTINGS.read_text(encoding="utf-8")
entry_start = settings_text.find("private enum AyuSettingsEntry")
entry_end = settings_text.find("private enum AyuHistoryEntry", entry_start)
if entry_start < 0 or entry_end < 0:
    raise SystemExit("AyuGram settings entry enum boundaries were not found")
entry = settings_text[entry_start:entry_end]
entry = entry.replace("    case history\n", "", 1)
# The private-preview row is installed before this cleanup step. Remove the
# History entry without dropping that neighboring preview case.
entry = entry.replace(
    "case .saveDeleted, .saveEdited, .history, .clearDeletedHistory, .privateInvitePreview:",
    "case .saveDeleted, .saveEdited, .clearDeletedHistory, .privateInvitePreview:",
    1
)
entry = entry.replace(
    "case .saveDeleted, .saveEdited, .history, .clearDeletedHistory:",
    "case .saveDeleted, .saveEdited, .clearDeletedHistory:",
    1
)
entry = entry.replace("        case .history: return 103\n", "", 1)
history_case = entry.find("        case .history:\n")
if history_case >= 0:
    next_case = None
    for marker in (
        "        case .privateInvitePreview:\n",
        "        case .clearDeletedHistory:\n",
    ):
        position = entry.find(marker, history_case)
        if position >= 0 and (next_case is None or position < next_case):
            next_case = position
    if next_case is None:
        raise SystemExit("Could not find the next AyuGram settings case after History")
    entry = entry[:history_case] + entry[next_case:]
if "case .privateInvitePreview:" not in entry:
    raise SystemExit("Private group preview action was removed with the History shortcut")
settings_text = settings_text[:entry_start] + entry + settings_text[entry_end:]

entries_start = settings_text.find("private func ayuSettingsEntries")
entries_end = settings_text.find("public func ayuGramSettingsScreen", entries_start)
if entries_start < 0 or entries_end < 0:
    raise SystemExit("AyuGram settings entries array boundaries were not found")
entries_block = settings_text[entries_start:entries_end].replace("        .history,\n", "")
settings_text = settings_text[:entries_start] + entries_block + settings_text[entries_end:]
SETTINGS.write_text(settings_text, encoding="utf-8")

menu_text = MESSAGE_MENU.read_text(encoding="utf-8")
menu_text = remove_swift_action(
    menu_text,
    'text: "AyuGram History"',
    "actions.append(.action(ContextMenuActionItem(",
    "message context-menu History action"
)
MESSAGE_MENU.write_text(menu_text, encoding="utf-8")

peer_media_text = PEER_MEDIA_MENU.read_text(encoding="utf-8")
peer_media_text = remove_swift_function(
    peer_media_text,
    "        func addAyuGramHistoryAction(_ items: inout [ContextMenuItem]) {",
    "PeerInfo media-menu History helper"
)
peer_media_text = peer_media_text.replace("                addAyuGramHistoryAction(&items)\n\n", "")
peer_media_text = peer_media_text.replace("import AyuGramSettingsScreen\n", "")
PEER_MEDIA_MENU.write_text(peer_media_text, encoding="utf-8")

peer_header_text = PEER_HEADER_MENU.read_text(encoding="utf-8")
peer_header_text = remove_swift_action(
    peer_header_text,
    'text: "AyuGram History"',
    "items.append(.action(ContextMenuActionItem(",
    "PeerInfo header More-menu History action"
)
peer_header_text = peer_header_text.replace("import AyuGramSettingsScreen\n", "")
peer_header_text = "\n".join(line.rstrip() for line in peer_header_text.splitlines()) + "\n"
PEER_HEADER_MENU.write_text(peer_header_text, encoding="utf-8")


# 4) Fail closed if a separate History navigation route remains accessible.
for path in (MESSAGE_MENU, PEER_MEDIA_MENU, PEER_HEADER_MENU):
    source = path.read_text(encoding="utf-8")
    if 'text: "AyuGram History"' in source or "ayuGramHistoryScreen(context:" in source:
        raise SystemExit(f"User-facing AyuGram History navigation remains in {path}")

delete_check = DELETE.read_text(encoding="utf-8")
state_check = STATE.read_text(encoding="utf-8")
holes_check = HOLES.read_text(encoding="utf-8")
bubble_check = BUBBLE.read_text(encoding="utf-8")
date_check = DATE_STATUS.read_text(encoding="utf-8")
text_bubble_check = TEXT_BUBBLE.read_text(encoding="utf-8")
media_bubble_check = MEDIA_BUBBLE.read_text(encoding="utf-8")
interactive_media_check = INTERACTIVE_MEDIA.read_text(encoding="utf-8")
assert "preserveDeletedMessagesInChat: Bool = false" in delete_check
assert "public static func recordDeletedRouteDiagnostic(" in CAPTURE_SERVICE.read_text(encoding="utf-8")
assert '"peer-retention-summary"' in delete_check, "Channel/group retention diagnostics must report skip reasons"
assert '"global-retention-summary"' in state_check, "Global-ID retention diagnostics must report skip reasons"
peer_retention = delete_check.split("var ayuRetainedDeletedMessageIds", 1)[1].split("let idsToDelete", 1)[0]
assert "isCopyProtected()" not in peer_retention, "Peer retention must not reject messages by copyProtected"
cache_helper = delete_check.split("public func _internal_cacheAyuGramReceivedMessages(", 1)[1].split("public func _internal_captureDeletedMessages(", 1)[0]
assert "isCopyProtected()" not in cache_helper, "Pre-delete cache must not reject messages by copyProtected"
assert "attribute.date == Int32.min && attribute.isHidden" in cache_helper, "Receive cache must skip locally retained deleted messages"
assert "guard !message.containsSecretMedia else { return false }" in cache_helper, "Receive cache must continue excluding secret media"
assert "return !message.attributes.contains(where:" in cache_helper, "Receive cache tombstone filter is missing"
global_retention = state_check.split("public func _internal_retainDeletedMessagesWithGlobalIds(", 1)[1].split("\n}", 1)[0]
assert "isCopyProtected()" not in global_retention, "Global-ID retention must not reject messages by copyProtected"
direct_delete_capture = delete_check.split("public func _internal_deleteMessages(", 1)[1].split("var resourceIds", 1)[0]
assert "isCopyProtected()" not in direct_delete_capture, "Deleted-message media archival must not reject messages by copyProtected"
assert "guard !message.containsSecretMedia else {" in delete_check, "Deleted-message media archiver must continue excluding secret media"
# [validate-simulator] Exercise this exact branch head; simulator validation only, no device IPA.
assert "AyuGramDeletedMessageDiagnostics.txt" in CAPTURE_SERVICE.read_text(encoding="utf-8")
assert "?.settings.saveDeletedMessages != false" in delete_check
assert "?.settings.saveDeletedMessages != false" in state_check
assert "let idsToDelete = ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }" in delete_check
assert "preserveDeletedMessagesInChat: true" in state_check
peer_handler = state_check.split("public func _internal_applyAyuGramServerDeleteMessages(", 1)[1].split(chr(10) + "}", 1)[0]
assert "let resolvedMessageIds = Set(ids.compactMap { transaction.getMessage($0)?.id })" in peer_handler, "Peer deletion must snapshot rows present before Telegram deletion"
assert "ayuAccountID: accountID" in peer_handler, "Direct peer-ID deletes must pass the active account into TelegramCore capture"
assert "AyuGramCaptureService.captureDeleted(" in delete_check, "Direct peer-ID deletes must snapshot resolved Postbox messages into History"
assert delete_check.index("AyuGramCaptureService.captureDeleted(") < delete_check.index("transaction.deleteMessages(idsToDelete"), "Direct-message History snapshots must be written before Postbox deletion"
assert "AyuGramCaptureService.captureMissingDeletedFromCache(" in peer_handler, "Channel/supergroup deletion must promote cached messages missing from Postbox"
assert "resolvedMessageIds: resolvedMessageIds" in peer_handler, "Peer cache fallback must exclude messages captured before deletion"
assert "ayuRetainedGlobalIds" in state_check
# Basic-group deletion uses Global IDs; supergroup deletion uses channel-scoped local IDs.
channel_delete_case = find_case_block(
    state_check,
    "case let .updateDeleteChannelMessages(updateDeleteChannelMessagesData):",
    "previousState.pts + ptsCount == pts"
)
assert channel_delete_case is not None, "Supergroup/channel delete update handler is missing"
_, _, channel_delete_block = channel_delete_case
assert "let channelDeletedMessageIds = messages.map" in channel_delete_block
assert channel_delete_block.count("updatedState.deleteMessages(channelDeletedMessageIds)") == 2, "Contiguous PTS deletes and stale local replay must both reach the shared handler"
assert "channel-pts-stale-replay" in channel_delete_block, "Stale channel updates must reach local AyuGram retention"
assert "channel-pts-gap" in channel_delete_block and "channel-pts-unknown" in channel_delete_block, "PTS gap and unknown-state paths must remain diagnosed"
assert '"channel-difference-delete"' in state_check, "Channel difference must expose replay of delayed delete updates"
assert "replay stale delete locally for AyuGram retention" in channel_delete_block, "Stale channel deletion logs must describe local retention replay"
assert "queued channel deletion despite stale PTS" not in channel_delete_block
assert "queued channel deletion before PTS repair" not in channel_delete_block
assert "queued channel deletion with unknown PTS state" not in channel_delete_block
assert "missingUpdatesFromChannels.insert(peerId)" in channel_delete_block, "PTS gaps must request a channel difference before deletion replay"
assert "channelsToPoll[peerId] = nil" in channel_delete_block, "Unknown channel PTS must request a channel poll before deletion replay"
assert "manualAddMessageThreadStatsDifference: manualAddMessageThreadStatsDifference" in state_check, "Server deletion wrapper must preserve thread-stat accounting"
assert "for id in ids where !ayuRetainedDeletedMessageIds.contains(id)" in delete_check, "Retained channel messages must not decrement thread statistics"
assert "ayuGlobalIdsToDelete = ids.filter" in state_check
assert "_internal_applyAyuGramServerDeleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, accountID: accountPeerId.toInt64(), manualAddMessageThreadStatsDifference: { id, add, remove in" in state_check
assert "addMessageThreadStatsDifference(threadKey: id, remove: remove, addedMessagePeer: nil, addedMessageId: nil, isOutgoing: false)" in state_check
assert "_internal_applyAyuGramServerDeleteMessagesWithGlobalIds(transaction: transaction, mediaBox: mediaBox, ids: ids, accountID: accountPeerId.toInt64())" in state_check
assert "public static func removeReceivedGlobalIDs(" in store_text
assert '"capture-cache-disabled"' in capture_service_text
assert '"global-cache-disabled"' in capture_service_text
assert "public func _internal_applyAyuGramServerDeleteMessages(" in state_check
assert "public func _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(" in state_check
assert "public func _internal_retainDeletedMessagesWithGlobalIds" in state_check
assert ".global($0)" in state_check
assert "return _internal_deleteMessages(" not in ENGINE.read_text(encoding="utf-8")
assert "-> Set<MessageId>" in delete_check
assert "@discardableResult" in delete_check
assert "ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }.map { .messageId($0) }" in state_check
assert "ids.filter { !ayuRetainedGlobalIds.contains($0) }.map { .global($0) }" in state_check
assert "EditedMessageAttribute(date: Int32.min, isHidden: true)" in delete_check
assert "isAyuGramDeleted: Bool" in date_check
assert 'updatedDateText = "🧹 \\(updatedDateText)"' in date_check
assert "isAyuGramDeleted = true" in bubble_check
assert "isAyuGramDeleted = true" in media_bubble_check
assert "isAyuGramDeleted: isAyuGramDeleted" in media_bubble_check
assert "public var isAyuGramDeleted: Bool" in interactive_media_check
assert "isAyuGramDeleted: dateAndStatus.isAyuGramDeleted && !presentationData.isPreview" in interactive_media_check
assert "Refresh cached copy after the current Postbox revision is installed." in state_check
assert "AyuGram history-hole receive cache" in holes_check
assert "import AyuGramIOS" in holes_check
assert "AyuGram chat-list preview receive cache" in holes_check
thread_history_check = THREAD_HISTORY.read_text(encoding="utf-8")
load_messages_check = LOAD_MESSAGES.read_text(encoding="utf-8")
assert "import AyuGramIOS" in thread_history_check
assert "AyuGram reply-thread receive cache" in thread_history_check
assert "import AyuGramIOS" in load_messages_check
assert "AyuGram load-by-id receive cache" in load_messages_check
live_receive_cache = state_check.split("// AyuGram pre-delete receive cache", 1)[1].split("case let .EditMessage(id, message):", 1)[0]
assert "id.namespace == Namespaces.Message.Cloud" in live_receive_cache
assert "Namespaces.Peer.CloudUser" in live_receive_cache
assert "Namespaces.Peer.CloudGroup" in live_receive_cache
assert "Namespaces.Peer.CloudChannel" in live_receive_cache
assert "_internal_cacheAyuGramReceivedMessages(" in live_receive_cache
capture_service_check = CAPTURE_SERVICE.read_text(encoding="utf-8")
assert "EditedMessageAttribute" not in capture_service_check
assert "isCopyProtected" not in capture_service_check
assert "containsSecretMedia" not in capture_service_check
assert "Namespaces.Peer" not in store_text and "Namespaces.Message" not in store_text
assert "Namespaces.Peer" not in capture_service_check and "Namespaces.Message" not in capture_service_check
assert "public static func cacheReceived(" in capture_service_check
assert "public static func promoteReceivedToDeleted(" in store_text
assert "state.messages.removeAll" in store_text, "Recovered cache entries must be consumed to prevent duplicate replays"
assert "editDates: editDates" in DELETE.read_text(encoding="utf-8")
assert "Message IDs are only unique inside a peer" in DELETE.read_text(encoding="utf-8")
assert "_internal_cacheAyuGramReceivedMessages(" in holes_check
print("PASS: deleted markers are routed for text bubbles and media-only image/video status overlays.")
print("PASS: server-deleted messages remain as local rows in their original chat.")
print("PASS: the original text/media/timestamp stay on the Telegram message; the timestamp carries the 🧹 mark.")
print("PASS: interactive deletion still uses Telegram's normal deletion path.")
print("PASS: the standalone AyuGram History navigation shortcuts are removed.")
print("PASS: Before and Manual Save/saved/king code paths were not changed.")
# Device IPA candidate follows the green CloudGroup/CloudChannel receive-cache simulator smoke; iPhone live-chat verification remains pending.
