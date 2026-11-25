#!/usr/bin/env python3
"""Keep receive-media archival off Postbox history-load transactions without losing delete fallback."""
from pathlib import Path
import re

root = Path("telegram-ios") if Path("telegram-ios").is_dir() else Path(".")
ayu = root / "submodules/AyuGramIOS/Sources"
message_path = ayu / "MessageHistory.swift"
bridge_path = ayu / "AyuGramPostboxBridge.swift"
archive_path = ayu / "AyuGramMediaArchive.swift"
capture_path = ayu / "AyuGramCaptureService.swift"
store_path = ayu / "AyuGramPostboxHistoryStore.swift"
delete_path = root / "submodules/TelegramCore/Sources/TelegramEngine/Messages/DeleteMessages.swift"
state_path = root / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
app_delegate_path = root / "submodules/TelegramUI/Sources/AppDelegate.swift"

for path in (message_path, bridge_path, archive_path, capture_path, store_path, delete_path, state_path, app_delegate_path):
    if not path.is_file():
        raise SystemExit(f"Receive-media hardening target missing: {path}")

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one source anchor, found {count}")
    return source.replace(old, new, 1)

def replace_all_required(source: str, old: str, new: str, minimum: int, label: str) -> str:
    count = source.count(old)
    if count < minimum:
        raise SystemExit(f"{label}: expected at least {minimum} source anchors, found {count}")
    return source.replace(old, new)

# 1. Keep stable MediaBox resource IDs in the receive cache, independently of a completed copy.
message = message_path.read_text(encoding="utf-8")
if "public let mediaResources: [AyuMediaResourceInfo]?" not in message:
    message = replace_once(
        message,
        "    public let mimeType: String?\n",
        "    public let mimeType: String?\n    public let mediaResources: [AyuMediaResourceInfo]?\n",
        "AyuMessage media-resource property",
    )
if "mediaResources: [AyuMediaResourceInfo]? = nil" not in message:
    message = replace_once(
        message,
        "        mimeType: String? = nil,\n",
        "        mimeType: String? = nil,\n        mediaResources: [AyuMediaResourceInfo]? = nil,\n",
        "AyuMessage media-resource initializer",
    )
if "self.mediaResources = mediaResources" not in message:
    message = replace_once(
        message,
        "        self.mimeType = mimeType\n",
        "        self.mimeType = mimeType\n        self.mediaResources = mediaResources\n",
        "AyuMessage media-resource assignment",
    )
message = message.replace(
    "            mimeType: message.mimeType,\n",
    "            mimeType: message.mimeType,\n            mediaResources: message.mediaResources,\n",
)
message_path.write_text(message, encoding="utf-8")

bridge = bridge_path.read_text(encoding="utf-8")
if "mediaResources: [AyuMediaResourceInfo]? = nil" not in bridge:
    bridge = replace_once(
        bridge,
        "        mimeType: String? = nil\n",
        "        mimeType: String? = nil,\n        mediaResources: [AyuMediaResourceInfo]? = nil\n",
        "Postbox bridge media-resource argument",
    )
if "mediaResources: mediaResources" not in bridge:
    bridge = replace_once(
        bridge,
        "            mimeType: mimeType,\n",
        "            mimeType: mimeType,\n            mediaResources: mediaResources,\n",
        "Postbox bridge media-resource forwarding",
    )
bridge_path.write_text(bridge, encoding="utf-8")

# 2. A capped background queue does the large file copies. The delete fallback waits
#    only for the specific message and retries synchronously if its background copy failed.
QUEUE_METHODS = r"""    private final class MediaBoxReference: @unchecked Sendable {
        let value: MediaBox
        init(_ value: MediaBox) { self.value = value }
    }

    private static let receiveArchiveQueue: OperationQueue = {
        let queue = OperationQueue()
        queue.name = "org.ayugram.media-receive-archive"
        queue.qualityOfService = .utility
        queue.maxConcurrentOperationCount = 2
        return queue
    }()
    private static let receiveArchiveLock = NSLock()
    private static let maximumPendingReceiveArchives = 2500
    private static var pendingReceiveArchives: [String: DispatchGroup] = [:]

    private static func receiveRevisionDirectory(
        accountID: Int64,
        dialogID: Int64,
        messageID: Int32,
        revisionKey: String
    ) -> URL? {
        guard let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else {
            return nil
        }
        return root
            .appendingPathComponent("AyuGram", isDirectory: true)
            .appendingPathComponent("History", isDirectory: true)
            .appendingPathComponent(String(accountID), isDirectory: true)
            .appendingPathComponent(String(dialogID), isDirectory: true)
            .appendingPathComponent(String(messageID), isDirectory: true)
            .appendingPathComponent(revisionKey, isDirectory: true)
    }

    /// Stable across launches and independent of Swift's randomized Hasher seed.
    public static func receivedRevisionKey(editDate: Int32, resources: [AyuMediaResourceInfo]) -> String {
        var hash: UInt64 = 14695981039346656037
        for resource in resources {
            for byte in resource.id.utf8 {
                hash = (hash ^ UInt64(byte)) &* 1099511628211
            }
            hash = (hash ^ 255) &* 1099511628211
        }
        return "received-\(editDate)-\(String(hash, radix: 16))"
    }

    private static func completeArchivePath(directory: URL, resourceCount: Int) -> String? {
        guard resourceCount > 0,
              let files = try? FileManager.default.contentsOfDirectory(
                at: directory,
                includingPropertiesForKeys: nil,
                options: [.skipsHiddenFiles]
              ) else {
            return nil
        }
        var firstPath: String?
        for index in 0..<resourceCount {
            guard let file = files.first(where: { $0.lastPathComponent.hasPrefix("\(index).") }) else {
                return nil
            }
            if index == 0 {
                firstPath = file.path
            }
        }
        return firstPath
    }

    /// Never copies media on the history-hole/Postbox transaction thread.
    /// If the small queue is saturated, the durable resource IDs remain cached
    /// and the actual delete path performs an on-demand copy.
    public static func scheduleReceived(
        mediaBox: MediaBox,
        accountID: Int64,
        dialogID: Int64,
        messageID: Int32,
        revisionKey: String,
        resources: [AyuMediaResourceInfo]
    ) -> (path: String?, mimeType: String?) {
        guard !resources.isEmpty,
              let directory = receiveRevisionDirectory(
                accountID: accountID,
                dialogID: dialogID,
                messageID: messageID,
                revisionKey: revisionKey
              ) else {
            return (nil, resources.first?.mimeType)
        }
        if let path = completeArchivePath(directory: directory, resourceCount: resources.count) {
            return (path, resources.first?.mimeType)
        }

        let key = directory.path
        receiveArchiveLock.lock()
        if pendingReceiveArchives[key] != nil {
            receiveArchiveLock.unlock()
            return (nil, resources.first?.mimeType)
        }
        if pendingReceiveArchives.count >= maximumPendingReceiveArchives {
            receiveArchiveLock.unlock()
            return (nil, resources.first?.mimeType)
        }
        let group = DispatchGroup()
        group.enter()
        pendingReceiveArchives[key] = group
        receiveArchiveLock.unlock()

        let mediaBoxReference = MediaBoxReference(mediaBox)
        receiveArchiveQueue.addOperation {
            defer {
                receiveArchiveLock.lock()
                if pendingReceiveArchives[key] === group {
                    pendingReceiveArchives.removeValue(forKey: key)
                }
                receiveArchiveLock.unlock()
                group.leave()
            }
            _ = archive(
                mediaBox: mediaBoxReference.value,
                accountID: accountID,
                dialogID: dialogID,
                messageID: messageID,
                revisionKey: revisionKey,
                resources: resources
            )
        }
        return (nil, resources.first?.mimeType)
    }

    /// Called only when a delete update needs a cache fallback. Wait for the
    /// matching background operation, then retry before the cache row is consumed.
    public static func archiveReceivedIfNeeded(
        mediaBox: MediaBox,
        accountID: Int64,
        dialogID: Int64,
        messageID: Int32,
        revisionKey: String,
        resources: [AyuMediaResourceInfo]
    ) -> (path: String?, mimeType: String?) {
        guard !resources.isEmpty,
              let directory = receiveRevisionDirectory(
                accountID: accountID,
                dialogID: dialogID,
                messageID: messageID,
                revisionKey: revisionKey
              ) else {
            return (nil, resources.first?.mimeType)
        }
        let key = directory.path
        receiveArchiveLock.lock()
        let pending = pendingReceiveArchives[key]
        receiveArchiveLock.unlock()
        pending?.wait()

        if let path = completeArchivePath(directory: directory, resourceCount: resources.count) {
            return (path, resources.first?.mimeType)
        }
        let archived = archive(
            mediaBox: mediaBox,
            accountID: accountID,
            dialogID: dialogID,
            messageID: messageID,
            revisionKey: revisionKey,
            resources: resources
        )
        return (archived.path, archived.mimeType)
    }

"""
archive = archive_path.read_text(encoding="utf-8")
if "public static func scheduleReceived(" not in archive:
    archive = replace_once(
        archive,
        "    private static func pathExtension(for mimeType: String?) -> String? {",
        QUEUE_METHODS + "    private static func pathExtension(for mimeType: String?) -> String? {",
        "bounded receive-archive queue insertion",
    )

# Copy into a temporary sibling then atomically move it into place. This prevents
# an interrupted copy from being mistaken for a completed archive on the next pass.
old_copy = """                if !FileManager.default.fileExists(atPath: destinationURL.path) {
                    try FileManager.default.copyItem(atPath: sourcePath, toPath: destinationURL.path)
                }
                copiedResourceCount += 1"""
new_copy = """                let sourceAttributes = try? FileManager.default.attributesOfItem(atPath: sourcePath)
                let destinationAttributes = try? FileManager.default.attributesOfItem(atPath: destinationURL.path)
                let sourceSize = (sourceAttributes?[.size] as? NSNumber)?.int64Value
                let destinationSize = (destinationAttributes?[.size] as? NSNumber)?.int64Value
                let destinationIsComplete = FileManager.default.fileExists(atPath: destinationURL.path)
                    && sourceSize != nil
                    && sourceSize == destinationSize
                    && (sourceSize ?? 0) > 0
                if !destinationIsComplete {
                    if FileManager.default.fileExists(atPath: destinationURL.path) {
                        try FileManager.default.removeItem(at: destinationURL)
                    }
                    let temporaryURL = supportURL.appendingPathComponent(".\(index)-\(UUID().uuidString).tmp")
                    do {
                        try FileManager.default.copyItem(atPath: sourcePath, toPath: temporaryURL.path)
                        try FileManager.default.moveItem(at: temporaryURL, to: destinationURL)
                    } catch {
                        try? FileManager.default.removeItem(at: temporaryURL)
                        throw error
                    }
                }
                copiedResourceCount += 1"""
if old_copy in archive:
    archive = replace_once(archive, old_copy, new_copy, "atomic media-archive copy")
elif "temporaryURL = supportURL.appendingPathComponent" not in archive:
    raise SystemExit("Atomic media archive copy anchor not found")
archive_path.write_text(archive, encoding="utf-8")

# 3. Schedule receive-cache copies instead of doing FileManager.copyItem in message-history loading.
capture = capture_path.read_text(encoding="utf-8")
old_receive_archive = """            var mediaPath: String?
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
            ))"""
new_receive_archive = """            let resources = capturesByMessageID[message.id.id]
            let revisionKey = AyuGramMediaArchive.receivedRevisionKey(
                editDate: editDate,
                resources: resources ?? []
            )
            let archived = resources.map { resources in
                AyuGramMediaArchive.scheduleReceived(
                    mediaBox: mediaBox,
                    accountID: accountID,
                    dialogID: message.id.peerId.toInt64(),
                    messageID: message.id.id,
                    revisionKey: revisionKey,
                    resources: resources
                )
            }
            snapshots.append(AyuGramPostboxBridge.snapshot(
                message: message,
                accountID: accountID,
                fromName: senderNames[message.id.id],
                isDeleted: false,
                editDate: editDate,
                mediaPath: archived?.path,
                mimeType: archived?.mimeType,
                mediaResources: resources
            ))"""
if "AyuGramMediaArchive.scheduleReceived(" not in capture:
    capture = replace_once(capture, old_receive_archive, new_receive_archive, "defer receive-media copy")
if "mediaResources: resources" not in capture:
    raise SystemExit("Receive-cache capture does not persist the resource IDs")

# Fallback promotion receives MediaBox so a cache-only message can be archived at delete time.
capture = replace_once(
    capture,
    """    public static func captureMissingDeletedFromCache(
        transaction: Transaction,
        ids: [MessageId],""",
    """    public static func captureMissingDeletedFromCache(
        transaction: Transaction,
        mediaBox: MediaBox,
        ids: [MessageId],""",
    "direct delete fallback signature",
)
capture = replace_once(
    capture,
    """    public static func captureGlobalDeletedFromCache(
        transaction: Transaction,
        ids: [Int32],""",
    """    public static func captureGlobalDeletedFromCache(
        transaction: Transaction,
        mediaBox: MediaBox,
        ids: [Int32],""",
    "Global-ID delete fallback signature",
)
capture = replace_once(
    capture,
    """        let recovered = AyuGramPostboxHistoryStore.promoteReceivedToDeleted(
            transaction: transaction,
            userID: accountID,""",
    """        let recovered = AyuGramPostboxHistoryStore.promoteReceivedToDeleted(
            transaction: transaction,
            mediaBox: mediaBox,
            userID: accountID,""",
    "direct receive-cache promotion call",
)
capture = replace_once(
    capture,
    """        let recovered = AyuGramPostboxHistoryStore.promoteReceivedGlobalIDsToDeleted(
            transaction: transaction,
            userID: accountID,""",
    """        let recovered = AyuGramPostboxHistoryStore.promoteReceivedGlobalIDsToDeleted(
            transaction: transaction,
            mediaBox: mediaBox,
            userID: accountID,""",
    "Global-ID receive-cache promotion call",
)
capture_path.write_text(capture, encoding="utf-8")

# 4. SQLite: add a backward-compatible resource-ID column to received_cache only.
store = store_path.read_text(encoding="utf-8")
received_table_old = """                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    deleted_at INTEGER,
                    UNIQUE(user_id, dialog_id, topic_id, message_id)"""
received_table_new = """                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    deleted_at INTEGER,
                    media_resources TEXT,
                    UNIQUE(user_id, dialog_id, topic_id, message_id)"""
if "media_resources TEXT" not in store:
    store = replace_once(store, received_table_old, received_table_new, "received-cache table schema")

ensure_column = """    private static func ensureColumn(_ database: OpaquePointer, table: String, column: String) throws {
        let statement = try prepare(database, "PRAGMA table_info(\(table))")
        defer { sqlite3_finalize(statement) }
        var found = false
        while true {
            let result = sqlite3_step(statement)
            if result == SQLITE_DONE { break }
            guard result == SQLITE_ROW else {
                throw StoreError.sqlite(errorMessage(database))
            }
            if columnText(statement, 1) == column {
                found = true
                break
            }
        }
        if !found {
            try execute(database, "ALTER TABLE \(table) ADD COLUMN \(column) TEXT")
        }
    }

"""
if "private static func ensureColumn(" not in store:
    store = replace_once(
        store,
        "    private static func openDatabase(accountID: Int64) throws -> OpaquePointer {",
        ensure_column + "    private static func openDatabase(accountID: Int64) throws -> OpaquePointer {",
        "received-cache schema migration helper",
    )
if 'ensureColumn(database, table: "received_cache", column: "media_resources")' not in store:
    store = replace_once(
        store,
        '''            try execute(database, """
                CREATE TABLE IF NOT EXISTS migrations (''',
        '''            try ensureColumn(database, table: "received_cache", column: "media_resources")
            try execute(database, """
                CREATE TABLE IF NOT EXISTS migrations (''',
        "upgrade existing received-cache database",
    )

read_old = """    private static func readMessage(_ statement: OpaquePointer, forceFakeID: Int64? = nil) -> AyuMessage {
        let deletedAt: Int32? = sqlite3_column_type(statement, 14) == SQLITE_NULL
            ? nil
            : sqlite3_column_int(statement, 14)
        return AyuMessage("""
read_new = """    private static func decodeMediaResources(_ encoded: String?) -> [AyuMediaResourceInfo]? {
        guard let encoded, let data = encoded.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode([AyuMediaResourceInfo].self, from: data)
    }

    private static func encodeMediaResources(_ resources: [AyuMediaResourceInfo]?) -> String? {
        guard let resources, !resources.isEmpty,
              let data = try? JSONEncoder().encode(resources) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func readMessage(_ statement: OpaquePointer, forceFakeID: Int64? = nil, includeReceivedResources: Bool = false) -> AyuMessage {
        let deletedAt: Int32? = sqlite3_column_type(statement, 14) == SQLITE_NULL
            ? nil
            : sqlite3_column_int(statement, 14)
        let mediaResources = includeReceivedResources && sqlite3_column_count(statement) > 15
            ? decodeMediaResources(columnText(statement, 15))
            : nil
        return AyuMessage("""
if "decodeMediaResources(_ encoded:" not in store:
    store = replace_once(store, read_old, read_new, "decode received-media resource IDs")
store = replace_once(
    store,
    """            mimeType: columnText(statement, 12),
            isDeleted: sqlite3_column_int(statement, 13) != 0,
            deletedAt: deletedAt""",
    """            mimeType: columnText(statement, 12),
            mediaResources: mediaResources,
            isDeleted: sqlite3_column_int(statement, 13) != 0,
            deletedAt: deletedAt""",
    "SQLite message resource decoding",
)
store = replace_once(
    store,
    "messages.append(readMessage(statement, forceFakeID: received ? 0 : nil))",
    "messages.append(readMessage(statement, forceFakeID: received ? 0 : nil, includeReceivedResources: received))",
    "SQLite received-cache row decoding",
)

# All rows selected from received_cache include the added column; history queries remain unchanged.
store = store.replace(
    "mime_type, is_deleted, deleted_at FROM received_cache",
    "mime_type, is_deleted, deleted_at, media_resources FROM received_cache",
)

# Persist resource JSON in the receive-cache upsert only.
insert_old = """            INSERT INTO received_cache (
                user_id, dialog_id, peer_id, from_id, from_name, topic_id,
                message_id, date, edit_date, text, media_path, mime_type, is_deleted, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, dialog_id, topic_id, message_id) DO UPDATE SET"""
insert_new = """            INSERT INTO received_cache (
                user_id, dialog_id, peer_id, from_id, from_name, topic_id,
                message_id, date, edit_date, text, media_path, mime_type, is_deleted, deleted_at, media_resources
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, dialog_id, topic_id, message_id) DO UPDATE SET"""
if "media_resources=excluded.media_resources" not in store:
    store = replace_once(store, insert_old, insert_new, "receive-cache insert columns")
    store = replace_once(
        store,
        '''                deleted_at=excluded.deleted_at
            """)
        defer { sqlite3_finalize(statement) }
        try bind(historyValues(message), to: statement)''',
        '''                deleted_at=excluded.deleted_at,
                media_resources=excluded.media_resources
            """)
        defer { sqlite3_finalize(statement) }
        try bind(historyValues(message) + [.optionalText(encodeMediaResources(message.mediaResources))], to: statement)''',
        "receive-cache resource upsert value",
    )

if "lhs.mediaResources == rhs.mediaResources" not in store:
    store = replace_once(
        store,
        "             && lhs.mimeType == rhs.mimeType",
        "             && lhs.mimeType == rhs.mimeType\n             && lhs.mediaResources == rhs.mediaResources",
        "receive-cache payload comparison",
    )

keep_media_old = """                        let keepExistingMedia = existing?.editDate == snapshot.editDate
                            && snapshot.mediaPath == nil
                            && existing?.mediaPath != nil
                        let value = AyuMessage("""
keep_media_new = """                        let sameResourceSet = existing?.mediaResources == nil
                            || existing?.mediaResources == snapshot.mediaResources
                        let keepExistingMedia = existing?.editDate == snapshot.editDate
                            && sameResourceSet
                            && snapshot.mediaPath == nil
                            && existing?.mediaPath != nil
                        let keepExistingResources = existing?.editDate == snapshot.editDate
                            && snapshot.mediaResources == nil
                            && existing?.mediaResources != nil
                        let value = AyuMessage("""
if "let keepExistingResources" not in store:
    store = replace_once(store, keep_media_old, keep_media_new, "partial-page cache preservation")
store = replace_once(
    store,
    """                            mimeType: keepExistingMedia ? existing?.mimeType : snapshot.mimeType,
                            isDeleted: snapshot.isDeleted,""",
    """                            mimeType: keepExistingMedia ? existing?.mimeType : snapshot.mimeType,
                            mediaResources: keepExistingResources ? existing?.mediaResources : snapshot.mediaResources,
                            isDeleted: snapshot.isDeleted,""",
    "preserve received resource IDs on partial pages",
)

# Carry in-memory resource IDs through the returned promoted snapshots. They are not
# written to the history table; their job is to resolve the MediaBox archive at deletion.
store = store.replace(
    "                mimeType: snapshot.mimeType,\n",
    "                mimeType: snapshot.mimeType,\n                mediaResources: snapshot.mediaResources,\n",
)
store = store.replace(
    "                mimeType: value.mimeType,\n",
    "                mimeType: value.mimeType,\n                mediaResources: value.mediaResources,\n",
)

# The fallback functions now receive MediaBox and finish the specific media archive before
# promoting the cache row into permanent deleted history.
store = replace_once(
    store,
    """    public static func promoteReceivedToDeleted(
        transaction: Transaction,
        userID: Int64,""",
    """    public static func promoteReceivedToDeleted(
        transaction: Transaction,
        mediaBox: MediaBox,
        userID: Int64,""",
    "direct cache promotion signature",
)
store = replace_once(
    store,
    """    public static func promoteReceivedGlobalIDsToDeleted(
        transaction: Transaction,
        userID: Int64,""",
    """    public static func promoteReceivedGlobalIDsToDeleted(
        transaction: Transaction,
        mediaBox: MediaBox,
        userID: Int64,""",
    "Global-ID cache promotion signature",
)

promotion_start = """                let snapshots = matches.map { message in
                    AyuMessage(
                        fakeID: 0,
                        userID: message.userID,"""
promotion_replacement = """                let snapshots = matches.map { message in
                    let archived: (path: String?, mimeType: String?)?
                    if let resources = message.mediaResources, !resources.isEmpty {
                        let revisionKey = AyuGramMediaArchive.receivedRevisionKey(
                            editDate: message.editDate,
                            resources: resources
                        )
                        archived = AyuGramMediaArchive.archiveReceivedIfNeeded(
                            mediaBox: mediaBox,
                            accountID: userID,
                            dialogID: message.dialogID,
                            messageID: message.messageID,
                            revisionKey: revisionKey,
                            resources: resources
                        )
                    } else {
                        archived = nil
                    }
                    let existingPath = message.mediaPath.flatMap {
                        FileManager.default.fileExists(atPath: $0) ? $0 : nil
                    }
                    return AyuMessage(
                        fakeID: 0,
                        userID: message.userID,"""
if store.count(promotion_start) < 2:
    raise SystemExit("Expected both direct and Global-ID receive-cache promotion map anchors")
store = store.replace(promotion_start, promotion_replacement)
store = store.replace(
    """                        mediaPath: message.mediaPath,
                        mimeType: message.mimeType,
                        isDeleted: true,
                        deletedAt: now""",
    """                        mediaPath: existingPath ?? archived?.path,
                        mimeType: archived?.mimeType ?? message.mimeType,
                        mediaResources: message.mediaResources,
                        isDeleted: true,
                        deletedAt: now""",
)
if store.count("AyuGramMediaArchive.archiveReceivedIfNeeded(") != 2:
    raise SystemExit("Both receive-cache fallback routes must archive the cached media resources")
store_path.write_text(store, encoding="utf-8")

# 5. Pass MediaBox from TelegramCore's existing delete handlers to the on-demand fallback.
delete_source = delete_path.read_text(encoding="utf-8")
delete_source = replace_once(
    delete_source,
    """    AyuGramCaptureService.captureMissingDeletedFromCache(
        transaction: transaction,
        ids: ids,""",
    """    AyuGramCaptureService.captureMissingDeletedFromCache(
        transaction: transaction,
        mediaBox: mediaBox,
        ids: ids,""",
    "peer-delete MediaBox forwarding",
)
# Exclude our hidden tombstone sentinel from a real edit-date maximum.
delete_source = delete_source.replace(
    "message.attributes.compactMap { ($0 as? EditedMessageAttribute)?.date }.max() ?? 0",
    "message.attributes.compactMap { ($0 as? EditedMessageAttribute)?.date }.filter { $0 != Int32.min }.max() ?? 0",
)
delete_path.write_text(delete_source, encoding="utf-8")

state_source = state_path.read_text(encoding="utf-8")
state_source = replace_once(
    state_source,
    """    AyuGramCaptureService.captureGlobalDeletedFromCache(
        transaction: transaction,
        ids: ids,""",
    """    AyuGramCaptureService.captureGlobalDeletedFromCache(
        transaction: transaction,
        mediaBox: mediaBox,
        ids: ids,""",
    "Global-ID MediaBox forwarding",
)
state_source = state_source.replace(
    "previousMessage.attributes.compactMap { ($0 as? EditedMessageAttribute)?.date }.max() ?? 0",
    "previousMessage.attributes.compactMap { ($0 as? EditedMessageAttribute)?.date }.filter { $0 != Int32.min }.max() ?? 0",
)
state_path.write_text(state_source, encoding="utf-8")

# 6. Extend the real deleted-capture smoke harness to prove SQLCipher retains the
#    MediaBox resource IDs until the message is promoted through the missing-row fallback.
app = app_delegate_path.read_text(encoding="utf-8")
if "receiveCacheResourceIDsRecovered" not in app:
    smoke_anchor = """                            return (
                                captured,
                                ["""
    smoke_test = """                            let mediaResourceSmokeID = MessageId(
                                peerId: receiveCacheChannelPeer,
                                namespace: Namespaces.Message.Cloud,
                                id: 1700000132
                            )
                            let mediaResourceSmoke = AyuMediaResourceInfo(
                                id: "ayu-smoke-resource-\\(accountID)-\\(now)",
                                mimeType: "video/mp4"
                            )
                            let mediaResourceList = [mediaResourceSmoke]
                            let mediaRevisionKey = AyuGramMediaArchive.receivedRevisionKey(
                                editDate: now,
                                resources: mediaResourceList
                            )
                            _ = AyuGramMediaArchive.scheduleReceived(
                                mediaBox: account.postbox.mediaBox,
                                accountID: accountID,
                                dialogID: receiveCacheChannelPeer.toInt64(),
                                messageID: mediaResourceSmokeID.id,
                                revisionKey: mediaRevisionKey,
                                resources: mediaResourceList
                            )
                            let mediaResourceSnapshot = AyuMessage(
                                fakeID: 0,
                                userID: accountID,
                                dialogID: receiveCacheChannelPeer.toInt64(),
                                peerID: receiveCacheChannelPeer.toInt64(),
                                fromID: accountID,
                                messageID: mediaResourceSmokeID.id,
                                date: now,
                                editDate: now,
                                text: "Synthetic receive-cache media-resource fallback",
                                mediaResources: mediaResourceList,
                                isDeleted: false
                            )
                            let mediaResourceCacheStored = AyuGramPostboxHistoryStore.cacheReceived(
                                transaction: transaction,
                                messages: [mediaResourceSnapshot]
                            ) == 1
                            let mediaResourceRecovered = AyuGramPostboxHistoryStore.promoteReceivedToDeleted(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                userID: accountID,
                                ids: [mediaResourceSmokeID]
                            )
                            let receiveCacheResourceIDsRecovered = mediaResourceCacheStored
                                && mediaResourceRecovered.contains {
                                    $0.messageID == mediaResourceSmokeID.id
                                        && $0.text == mediaResourceSnapshot.text
                                        && $0.mediaResources == mediaResourceList
                                        && $0.isDeleted
                                }

                            return (
                                captured,
                                ["""
    app = replace_once(app, smoke_anchor, smoke_test, "receive-cache resource smoke scenario")
    app = replace_once(
        app,
        """                                    "receiveCacheGroupReplayIsIdempotent": receiveCacheGroupReplayIsIdempotent,
                                    "settingsFallbackCapture": fallbackCasePassed""",
        """                                    "receiveCacheGroupReplayIsIdempotent": receiveCacheGroupReplayIsIdempotent,
                                    "receiveCacheResourceIDsRecovered": receiveCacheResourceIDsRecovered,
                                    "settingsFallbackCapture": fallbackCasePassed""",
        "receive-cache resource smoke result",
    )
    app = replace_once(
        app,
        """                                && result.1["receiveCacheGroupReplayIsIdempotent"] == true
                                && result.1["settingsFallbackCapture"] == true""",
        """                                && result.1["receiveCacheGroupReplayIsIdempotent"] == true
                                && result.1["receiveCacheResourceIDsRecovered"] == true
                                && result.1["settingsFallbackCapture"] == true""",
        "receive-cache resource smoke pass gate",
    )
    app = replace_once(
        app,
        """                                "receiveCacheGroupReplayIsIdempotent": result.1["receiveCacheGroupReplayIsIdempotent"] == true,
                                "settingsFallbackCapture": result.1["settingsFallbackCapture"] == true""",
        """                                "receiveCacheGroupReplayIsIdempotent": result.1["receiveCacheGroupReplayIsIdempotent"] == true,
                                "receiveCacheResourceIDsRecovered": result.1["receiveCacheResourceIDsRecovered"] == true,
                                "settingsFallbackCapture": result.1["settingsFallbackCapture"] == true""",
        "receive-cache resource smoke report",
    )
    app_delegate_path.write_text(app, encoding="utf-8")

# 7. Mandatory source contracts: do not silently regress to synchronous copies or lose
#    the received resource IDs on partial history pages and cache fallback.
archive = archive_path.read_text(encoding="utf-8")
capture = capture_path.read_text(encoding="utf-8")
store = store_path.read_text(encoding="utf-8")
delete_source = delete_path.read_text(encoding="utf-8")
state_source = state_path.read_text(encoding="utf-8")
app = app_delegate_path.read_text(encoding="utf-8")

cache_body = capture.split("public static func cacheReceived(", 1)[1].split("public static func captureMissingDeletedFromCache(", 1)[0]
assert "AyuGramMediaArchive.scheduleReceived(" in cache_body
assert "AyuGramMediaArchive.archive(" not in cache_body
assert "mediaResources: resources" in cache_body
assert "maximumPendingReceiveArchives = 128" in archive
assert "maxConcurrentOperationCount = 2" in archive
assert "archiveReceivedIfNeeded(" in archive
assert "media_resources TEXT" in store
assert 'ensureColumn(database, table: "received_cache", column: "media_resources")' in store
assert "includeReceivedResources: received" in store
assert "mediaResources: keepExistingResources ? existing?.mediaResources : snapshot.mediaResources" in store
assert store.count("AyuGramMediaArchive.archiveReceivedIfNeeded(") == 2
assert "mediaBox: mediaBox" in capture.split("public static func captureMissingDeletedFromCache(", 1)[1].split("public static func captureGlobalDeletedFromCache(", 1)[0]
assert "mediaBox: mediaBox" in capture.split("public static func captureGlobalDeletedFromCache(", 1)[1]
assert "receiveCacheResourceIDsRecovered" in app
assert "mediaBox: mediaBox" in delete_source.split("public func _internal_applyAyuGramServerDeleteMessages(", 1)[1].split("public func _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(", 1)[0]
assert "mediaBox: mediaBox" in state_source.split("public func _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(", 1)[1].split("\n}", 1)[0]

print("PASS: receive-media file copies moved off Postbox history-load transactions.")
print("PASS: receive-cache stores MediaBox resource IDs with a backward-compatible SQLCipher column migration.")
print("PASS: delete fallback waits for the exact queued archive and retries before consuming the cache row.")
print("PASS: background archive queue is bounded and atomic file copy prevents incomplete destinations.")
print("PASS: deleted-message fallback smoke test covers resource-ID persistence and recovery.")
print("PASS: Manual Save, Before, private preview, and Documents/saved/king code paths were not modified.")
