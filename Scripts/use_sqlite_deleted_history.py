#!/usr/bin/env python3
"""Replace AyuGram's Postbox-preferences history cache with an account-scoped SQLCipher/SQLite store."""
from pathlib import Path

root = Path("telegram-ios") if Path("telegram-ios").is_dir() else Path(".")
store_path = root / "submodules/AyuGramIOS/Sources/AyuGramPostboxHistoryStore.swift"
build_path = root / "submodules/AyuGramIOS/BUILD"

if not store_path.is_file():
    raise SystemExit(f"Missing AyuGram History store: {store_path}")
if not build_path.is_file():
    raise SystemExit(f"Missing AyuGram Bazel target: {build_path}")

source = r'''import Foundation
import Postbox
import BuildConfig
import sqlcipher

/// Legacy state models are retained only to import existing Postbox preferences
/// into SQLite once. New writes go exclusively to the SQLite database.
public struct AyuPostboxHistoryState: Codable, Equatable, Sendable {
    public var version: Int32
    public var nextFakeID: Int64
    public var messages: [AyuMessage]

    public init(version: Int32 = 1, nextFakeID: Int64 = 1, messages: [AyuMessage] = []) {
        self.version = version
        self.nextFakeID = nextFakeID
        self.messages = messages
    }
}

public struct AyuPostboxReceivedMessageState: Codable, Equatable, Sendable {
    public var messages: [AyuMessage]

    public init(messages: [AyuMessage] = []) {
        self.messages = messages
    }
}

public enum AyuGramPostboxHistoryStore {
    private static let legacyHistoryKey = ValueBoxKey("ayugram.messageHistory.v1")
    private static let legacyReceivedKey = ValueBoxKey("ayugram.receivedMessageCache.v1")
    private static let maximumEntries = 5000
    private static let maximumReceivedEntries = 2500
    private static let lock = NSRecursiveLock()
    private static let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

    private enum StoreError: Error, CustomStringConvertible {
        case sqlite(String)
        case invalidStatement

        var description: String {
            switch self {
            case let .sqlite(message):
                return message
            case .invalidStatement:
                return "SQLite failed to prepare a statement"
            }
        }
    }

    private enum Value {
        case integer(Int64)
        case text(String)
        case optionalText(String?)
        case null
    }

    // Keep the database separate from History media archives and Manual Save's
    // Documents/saved/king directory. Each Telegram account has its own file.
    private static func appGroupLocation() throws -> (rootPath: String, baseAppBundleId: String) {
        guard
            let appBundleIdentifier = Bundle.main.bundleIdentifier,
            let lastDotRange = appBundleIdentifier.range(of: ".", options: .backwards)
        else {
            throw StoreError.sqlite("The Telegram app bundle identifier is unavailable")
        }
        let baseAppBundleId = String(appBundleIdentifier[..<lastDotRange.lowerBound])
        let appGroupIdentifier = "group.\(baseAppBundleId)"
        guard let appGroupURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier) else {
            throw StoreError.sqlite("The Telegram app group container is unavailable")
        }
        let rootURL = appGroupURL.appendingPathComponent("telegram-data", isDirectory: true)
        try FileManager.default.createDirectory(at: rootURL, withIntermediateDirectories: true)
        return (rootURL.path, baseAppBundleId)
    }

    private static func databaseURL(accountID: Int64) throws -> URL {
        let location = try appGroupLocation()
        let directory = URL(fileURLWithPath: location.rootPath, isDirectory: true)
            .appendingPathComponent("AyuGram", isDirectory: true)
            .appendingPathComponent("HistoryDatabase", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory.appendingPathComponent("account-\(accountID).sqlite", isDirectory: false)
    }

    private static func configureEncryption(_ database: OpaquePointer) throws {
        let location = try appGroupLocation()
        let parameters = BuildConfig.deviceSpecificEncryptionParameters(
            location.rootPath,
            baseAppBundleId: location.baseAppBundleId
        )
        guard parameters.key.count == 32, parameters.salt.count == 16 else {
            throw StoreError.sqlite("Telegram's SQLCipher key material has an invalid size")
        }
        let keyHex = (Array(parameters.key) + Array(parameters.salt))
            .map { String(format: "%02x", Int($0)) }
            .joined()
        try execute(database, "PRAGMA cipher_plaintext_header_size=32")
        try execute(database, "PRAGMA cipher_default_plaintext_header_size=32")
        try execute(database, "PRAGMA key=\"x'\(keyHex)'\"")
    }

    private static func errorMessage(_ database: OpaquePointer?) -> String {
        guard let database, let message = sqlite3_errmsg(database) else {
            return "unknown SQLite error"
        }
        return String(cString: message)
    }

    private static func execute(_ database: OpaquePointer, _ sql: String) throws {
        let result = sql.withCString { sqlite3_exec(database, $0, nil, nil, nil) }
        guard result == SQLITE_OK else {
            throw StoreError.sqlite(errorMessage(database))
        }
    }

    private static func prepare(_ database: OpaquePointer, _ sql: String) throws -> OpaquePointer {
        var statement: OpaquePointer?
        let result = sql.withCString { sqlite3_prepare_v2(database, $0, -1, &statement, nil) }
        guard result == SQLITE_OK, let statement else {
            throw StoreError.sqlite(errorMessage(database))
        }
        return statement
    }

    private static func bind(_ value: Value, to statement: OpaquePointer, at index: Int32) throws {
        let result: Int32
        switch value {
        case let .integer(number):
            result = sqlite3_bind_int64(statement, index, number)
        case let .text(string):
            result = string.withCString {
                sqlite3_bind_text(statement, index, $0, -1, transient)
            }
        case let .optionalText(optional):
            if let string = optional {
                result = string.withCString {
                    sqlite3_bind_text(statement, index, $0, -1, transient)
                }
            } else {
                result = sqlite3_bind_null(statement, index)
            }
        case .null:
            result = sqlite3_bind_null(statement, index)
        }
        guard result == SQLITE_OK else {
            throw StoreError.sqlite("SQLite bind failed with code \(result)")
        }
    }

    private static func bind(_ values: [Value], to statement: OpaquePointer) throws {
        for (offset, value) in values.enumerated() {
            try bind(value, to: statement, at: Int32(offset + 1))
        }
    }

    private static func withTransaction<T>(_ database: OpaquePointer, body: () throws -> T) throws -> T {
        try execute(database, "BEGIN IMMEDIATE")
        do {
            let result = try body()
            try execute(database, "COMMIT")
            return result
        } catch {
            try? execute(database, "ROLLBACK")
            throw error
        }
    }

    private static func withDatabase<T>(accountID: Int64, body: (OpaquePointer) throws -> T) -> T? {
        lock.lock()
        defer { lock.unlock() }

        var handle: OpaquePointer?
        do {
            let url = try databaseURL(accountID: accountID)
            let openResult = url.path.withCString {
                sqlite3_open_v2(
                    $0,
                    &handle,
                    SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX,
                    nil
                )
            }
            guard openResult == SQLITE_OK, let database = handle else {
                let message = errorMessage(handle)
                if let handle {
                    sqlite3_close(handle)
                }
                throw StoreError.sqlite(message)
            }
            defer { sqlite3_close(database) }

            sqlite3_busy_timeout(database, 5000)
            try configureEncryption(database)
            try execute(database, "PRAGMA journal_mode=WAL")
            try execute(database, "PRAGMA synchronous=NORMAL")
            try execute(database, "PRAGMA foreign_keys=ON")
            try execute(database, """
                CREATE TABLE IF NOT EXISTS history (
                    fake_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    dialog_id INTEGER NOT NULL,
                    peer_id INTEGER NOT NULL,
                    from_id INTEGER NOT NULL,
                    from_name TEXT,
                    topic_id INTEGER NOT NULL DEFAULT 0,
                    message_id INTEGER NOT NULL,
                    date INTEGER NOT NULL,
                    edit_date INTEGER NOT NULL DEFAULT 0,
                    text TEXT NOT NULL,
                    media_path TEXT,
                    mime_type TEXT,
                    is_deleted INTEGER NOT NULL,
                    deleted_at INTEGER
                )
                """)
            try execute(database, """
                CREATE INDEX IF NOT EXISTS history_dialog_lookup
                ON history(user_id, dialog_id, is_deleted, fake_id DESC)
                """)
            try execute(database, """
                CREATE INDEX IF NOT EXISTS history_revision_lookup
                ON history(user_id, dialog_id, message_id, is_deleted, fake_id DESC)
                """)
            try execute(database, """
                CREATE TABLE IF NOT EXISTS received_cache (
                    cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    dialog_id INTEGER NOT NULL,
                    peer_id INTEGER NOT NULL,
                    from_id INTEGER NOT NULL,
                    from_name TEXT,
                    topic_id INTEGER NOT NULL DEFAULT 0,
                    message_id INTEGER NOT NULL,
                    date INTEGER NOT NULL,
                    edit_date INTEGER NOT NULL DEFAULT 0,
                    text TEXT NOT NULL,
                    media_path TEXT,
                    mime_type TEXT,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    deleted_at INTEGER,
                    UNIQUE(user_id, dialog_id, topic_id, message_id)
                )
                """)
            try execute(database, """
                CREATE TABLE IF NOT EXISTS migrations (
                    account_id INTEGER NOT NULL,
                    migration TEXT NOT NULL,
                    PRIMARY KEY(account_id, migration)
                )
                """)
            return try body(database)
        } catch {
            AyuGramCaptureService.recordDeletedRouteDiagnostic(
                "sqlite-store-error",
                received: 0,
                missing: 1
            )
            return nil
        }
    }

    private static func columnText(_ statement: OpaquePointer, _ index: Int32) -> String? {
        guard sqlite3_column_type(statement, index) != SQLITE_NULL,
              let text = sqlite3_column_text(statement, index) else {
            return nil
        }
        return String(cString: UnsafeRawPointer(text).assumingMemoryBound(to: CChar.self))
    }

    private static func readMessage(_ statement: OpaquePointer, forceFakeID: Int64? = nil) -> AyuMessage {
        let deletedAt: Int32? = sqlite3_column_type(statement, 14) == SQLITE_NULL
            ? nil
            : sqlite3_column_int(statement, 14)
        return AyuMessage(
            fakeID: forceFakeID ?? sqlite3_column_int64(statement, 0),
            userID: sqlite3_column_int64(statement, 1),
            dialogID: sqlite3_column_int64(statement, 2),
            peerID: sqlite3_column_int64(statement, 3),
            fromID: sqlite3_column_int64(statement, 4),
            fromName: columnText(statement, 5),
            topicID: sqlite3_column_int64(statement, 6),
            messageID: sqlite3_column_int(statement, 7),
            date: sqlite3_column_int(statement, 8),
            editDate: sqlite3_column_int(statement, 9),
            text: columnText(statement, 10) ?? "",
            mediaPath: columnText(statement, 11),
            mimeType: columnText(statement, 12),
            isDeleted: sqlite3_column_int(statement, 13) != 0,
            deletedAt: deletedAt
        )
    }

    private static let historyColumns = """
        fake_id, user_id, dialog_id, peer_id, from_id, from_name,
        topic_id, message_id, date, edit_date, text, media_path, mime_type,
        is_deleted, deleted_at
        """

    private static func selectMessages(
        _ database: OpaquePointer,
        sql: String,
        values: [Value],
        received: Bool = false
    ) throws -> [AyuMessage] {
        let statement = try prepare(database, sql)
        defer { sqlite3_finalize(statement) }
        try bind(values, to: statement)
        var messages: [AyuMessage] = []
        while true {
            let result = sqlite3_step(statement)
            if result == SQLITE_DONE {
                break
            }
            guard result == SQLITE_ROW else {
                throw StoreError.sqlite(errorMessage(database))
            }
            messages.append(readMessage(statement, forceFakeID: received ? 0 : nil))
        }
        return messages
    }

    private static func historyValues(_ message: AyuMessage) -> [Value] {
        [
            .integer(message.userID),
            .integer(message.dialogID),
            .integer(message.peerID),
            .integer(message.fromID),
            .optionalText(message.fromName),
            .integer(message.topicID),
            .integer(Int64(message.messageID)),
            .integer(Int64(message.date)),
            .integer(Int64(message.editDate)),
            .text(message.text),
            .optionalText(message.mediaPath),
            .optionalText(message.mimeType),
            .integer(message.isDeleted ? 1 : 0),
            message.deletedAt.map { .integer(Int64($0)) } ?? .null
        ]
    }

    private static func insertHistory(
        _ database: OpaquePointer,
        message: AyuMessage,
        preserveFakeID: Bool = false
    ) throws -> Int64 {
        let sql: String
        let values: [Value]
        if preserveFakeID, message.fakeID > 0 {
            sql = """
                INSERT OR IGNORE INTO history (
                    fake_id, user_id, dialog_id, peer_id, from_id, from_name, topic_id,
                    message_id, date, edit_date, text, media_path, mime_type, is_deleted, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            values = [.integer(message.fakeID)] + historyValues(message)
        } else {
            sql = """
                INSERT INTO history (
                    user_id, dialog_id, peer_id, from_id, from_name, topic_id,
                    message_id, date, edit_date, text, media_path, mime_type, is_deleted, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            values = historyValues(message)
        }
        let statement = try prepare(database, sql)
        defer { sqlite3_finalize(statement) }
        try bind(values, to: statement)
        let result = sqlite3_step(statement)
        guard result == SQLITE_DONE else {
            throw StoreError.sqlite(errorMessage(database))
        }
        return sqlite3_last_insert_rowid(database)
    }

    private static func insertReceived(_ database: OpaquePointer, message: AyuMessage) throws {
        let statement = try prepare(database, """
            INSERT INTO received_cache (
                user_id, dialog_id, peer_id, from_id, from_name, topic_id,
                message_id, date, edit_date, text, media_path, mime_type, is_deleted, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, dialog_id, topic_id, message_id) DO UPDATE SET
                peer_id=excluded.peer_id,
                from_id=excluded.from_id,
                from_name=excluded.from_name,
                date=excluded.date,
                edit_date=excluded.edit_date,
                text=excluded.text,
                media_path=excluded.media_path,
                mime_type=excluded.mime_type,
                is_deleted=excluded.is_deleted,
                deleted_at=excluded.deleted_at
            """)
        defer { sqlite3_finalize(statement) }
        try bind(historyValues(message), to: statement)
        let result = sqlite3_step(statement)
        guard result == SQLITE_DONE else {
            throw StoreError.sqlite(errorMessage(database))
        }
    }

    private static func historyDuplicateExists(_ database: OpaquePointer, message: AyuMessage) throws -> Bool {
        let statement = try prepare(database, """
            SELECT 1 FROM history
            WHERE user_id=? AND dialog_id=? AND topic_id=? AND message_id=?
              AND is_deleted=? AND edit_date=? AND text=?
              AND COALESCE(media_path, '')=COALESCE(?, '')
              AND COALESCE(mime_type, '')=COALESCE(?, '')
            LIMIT 1
            """)
        defer { sqlite3_finalize(statement) }
        let values: [Value] = [
            .integer(message.userID),
            .integer(message.dialogID),
            .integer(message.topicID),
            .integer(Int64(message.messageID)),
            .integer(message.isDeleted ? 1 : 0),
            .integer(Int64(message.editDate)),
            .text(message.text),
            .optionalText(message.mediaPath),
            .optionalText(message.mimeType)
        ]
        try bind(values, to: statement)
        let result = sqlite3_step(statement)
        if result == SQLITE_ROW {
            return true
        }
        guard result == SQLITE_DONE else {
            throw StoreError.sqlite(errorMessage(database))
        }
        return false
    }

    private static func appendInDatabase(
        _ database: OpaquePointer,
        snapshots: [AyuMessage],
        deleted: Bool
    ) throws -> [AyuMessage] {
        guard !snapshots.isEmpty else { return [] }
        let deletedAtNow = Int32(Date().timeIntervalSince1970)
        var stored: [AyuMessage] = []
        stored.reserveCapacity(snapshots.count)

        for snapshot in snapshots {
            let value = AyuMessage(
                fakeID: 0,
                userID: snapshot.userID,
                dialogID: snapshot.dialogID,
                peerID: snapshot.peerID,
                fromID: snapshot.fromID,
                fromName: snapshot.fromName,
                topicID: snapshot.topicID,
                messageID: snapshot.messageID,
                date: snapshot.date,
                editDate: snapshot.editDate,
                text: snapshot.text,
                mediaPath: snapshot.mediaPath,
                mimeType: snapshot.mimeType,
                isDeleted: deleted,
                deletedAt: deleted ? (snapshot.deletedAt ?? deletedAtNow) : nil
            )
            if try historyDuplicateExists(database, message: value) {
                continue
            }
            let identifier = try insertHistory(database, message: value)
            stored.append(AyuMessage(
                fakeID: identifier,
                userID: value.userID,
                dialogID: value.dialogID,
                peerID: value.peerID,
                fromID: value.fromID,
                fromName: value.fromName,
                topicID: value.topicID,
                messageID: value.messageID,
                date: value.date,
                editDate: value.editDate,
                text: value.text,
                mediaPath: value.mediaPath,
                mimeType: value.mimeType,
                isDeleted: value.isDeleted,
                deletedAt: value.deletedAt
            ))
        }

        if let accountID = snapshots.first?.userID {
            let trim = try prepare(database, """
                DELETE FROM history
                WHERE user_id=? AND fake_id NOT IN (
                    SELECT fake_id FROM history WHERE user_id=?
                    ORDER BY fake_id DESC LIMIT ?
                )
                """)
            defer { sqlite3_finalize(trim) }
            try bind([.integer(accountID), .integer(accountID), .integer(Int64(maximumEntries))], to: trim)
            guard sqlite3_step(trim) == SQLITE_DONE else {
                throw StoreError.sqlite(errorMessage(database))
            }
        }
        return stored
    }

    private static func receivedMessages(
        _ database: OpaquePointer,
        userID: Int64
    ) throws -> [AyuMessage] {
        return try selectMessages(
            database,
            sql: "SELECT cache_id AS fake_id, user_id, dialog_id, peer_id, from_id, from_name, topic_id, message_id, date, edit_date, text, media_path, mime_type, is_deleted, deleted_at FROM received_cache WHERE user_id=? ORDER BY cache_id ASC",
            values: [.integer(userID)],
            received: true
        )
    }

    private static func samePayload(_ lhs: AyuMessage, _ rhs: AyuMessage) -> Bool {
        lhs.userID == rhs.userID
            && lhs.dialogID == rhs.dialogID
            && lhs.peerID == rhs.peerID
            && lhs.fromID == rhs.fromID
            && lhs.fromName == rhs.fromName
            && lhs.topicID == rhs.topicID
            && lhs.messageID == rhs.messageID
            && lhs.date == rhs.date
            && lhs.editDate == rhs.editDate
            && lhs.text == rhs.text
            && lhs.mediaPath == rhs.mediaPath
            && lhs.mimeType == rhs.mimeType
    }

    private static func trimReceived(_ database: OpaquePointer, userID: Int64) throws {
        let statement = try prepare(database, """
            DELETE FROM received_cache
            WHERE user_id=? AND cache_id NOT IN (
                SELECT cache_id FROM received_cache WHERE user_id=?
                ORDER BY cache_id DESC LIMIT ?
            )
            """)
        defer { sqlite3_finalize(statement) }
        try bind([.integer(userID), .integer(userID), .integer(Int64(maximumReceivedEntries))], to: statement)
        guard sqlite3_step(statement) == SQLITE_DONE else {
            throw StoreError.sqlite(errorMessage(database))
        }
    }

    private static func deleteReceivedRows(_ database: OpaquePointer, cacheIDs: [Int64]) throws {
        guard !cacheIDs.isEmpty else { return }
        let statement = try prepare(database, "DELETE FROM received_cache WHERE cache_id=?")
        defer { sqlite3_finalize(statement) }
        for identifier in cacheIDs {
            sqlite3_reset(statement)
            sqlite3_clear_bindings(statement)
            try bind(.integer(identifier), to: statement, at: 1)
            guard sqlite3_step(statement) == SQLITE_DONE else {
                throw StoreError.sqlite(errorMessage(database))
            }
        }
    }

    // Old installations stored both arrays in Postbox preferences. Import them
    // once per account and leave the old keys intact as a rollback safety copy.
    private static func migrateLegacyIfNeeded(transaction: Transaction, accountID: Int64) {
        _ = withDatabase(accountID: accountID) { database in
            let check = try? prepare(database, "SELECT 1 FROM migrations WHERE account_id=? AND migration='postbox-preferences-v1' LIMIT 1")
            guard let check else { return }
            defer { sqlite3_finalize(check) }
            try? bind(.integer(accountID), to: check, at: 1)
            if sqlite3_step(check) == SQLITE_ROW {
                return
            }

            let oldHistory = transaction.getPreferencesEntry(key: legacyHistoryKey)?.get(AyuPostboxHistoryState.self)
                ?? AyuPostboxHistoryState()
            let oldReceived = transaction.getPreferencesEntry(key: legacyReceivedKey)?.get(AyuPostboxReceivedMessageState.self)
                ?? AyuPostboxReceivedMessageState()
            do {
                try withTransaction(database) {
                    for message in oldHistory.messages where message.userID == accountID {
                        _ = try insertHistory(database, message: message, preserveFakeID: true)
                    }
                    for message in oldReceived.messages where message.userID == accountID {
                        try insertReceived(database, message: message)
                    }
                    let marker = try prepare(database, """
                        INSERT OR REPLACE INTO migrations(account_id, migration)
                        VALUES (?, 'postbox-preferences-v1')
                        """)
                    defer { sqlite3_finalize(marker) }
                    try bind(.integer(accountID), to: marker, at: 1)
                    guard sqlite3_step(marker) == SQLITE_DONE else {
                        throw StoreError.sqlite(errorMessage(database))
                    }
                }
            } catch {
                AyuGramCaptureService.recordDeletedRouteDiagnostic("sqlite-migration-error", received: oldHistory.messages.count + oldReceived.messages.count)
            }
        }
    }

    // MARK: - History reads

    private static func legacyAccountIDs(transaction: Transaction) -> [Int64] {
        let history = transaction.getPreferencesEntry(key: legacyHistoryKey)?.get(AyuPostboxHistoryState.self)
            ?? AyuPostboxHistoryState()
        let received = transaction.getPreferencesEntry(key: legacyReceivedKey)?.get(AyuPostboxReceivedMessageState.self)
            ?? AyuPostboxReceivedMessageState()
        return Array(Set(history.messages.map(\.userID) + received.messages.map(\.userID))).sorted()
    }

    public static func all(transaction: Transaction, userID: Int64? = nil, limit: Int = 500) -> [AyuMessage] {
        if let userID {
            return filtered(transaction: transaction, userID: userID, kind: .all, limit: limit)
        }
        let rows = legacyAccountIDs(transaction: transaction).flatMap { accountID in
            filtered(transaction: transaction, userID: accountID, kind: .all, limit: limit)
        }
        return Array(rows.sorted { $0.fakeID > $1.fakeID }.prefix(max(0, limit)))
    }

    public static func filtered(
        transaction: Transaction,
        userID: Int64? = nil,
        dialogID: Int64? = nil,
        kind: AyuHistoryKind = .all,
        limit: Int = 500
    ) -> [AyuMessage] {
        guard let userID else {
            let rows = legacyAccountIDs(transaction: transaction).flatMap { accountID in
                filtered(transaction: transaction, userID: accountID, dialogID: dialogID, kind: kind, limit: limit)
            }
            return Array(rows.sorted { $0.fakeID > $1.fakeID }.prefix(max(0, limit)))
        }
        migrateLegacyIfNeeded(transaction: transaction, accountID: userID)
        return withDatabase(accountID: userID) { database in
            var clauses = ["user_id=?"]
            var values: [Value] = [.integer(userID)]
            if let dialogID {
                clauses.append("dialog_id=?")
                values.append(.integer(dialogID))
            }
            switch kind {
            case .all:
                break
            case .deleted:
                clauses.append("is_deleted=1")
            case .edited:
                clauses.append("is_deleted=0")
            }
            values.append(.integer(Int64(max(0, limit))))
            let sql = "SELECT \(historyColumns) FROM history WHERE \(clauses.joined(separator: " AND ")) ORDER BY fake_id DESC LIMIT ?"
            return (try? selectMessages(database, sql: sql, values: values)) ?? []
        } ?? []
    }

    public static func deleted(
        transaction: Transaction,
        userID: Int64,
        dialogID: Int64,
        topicID: Int64 = 0,
        query: String? = nil,
        limit: Int = 100
    ) -> [AyuMessage] {
        migrateLegacyIfNeeded(transaction: transaction, accountID: userID)
        return withDatabase(accountID: userID) { database in
            let normalizedQuery = query?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            var sql = "SELECT \(historyColumns) FROM history WHERE user_id=? AND dialog_id=? AND is_deleted=1"
            var values: [Value] = [.integer(userID), .integer(dialogID)]
            if topicID != 0 {
                sql += " AND topic_id=?"
                values.append(.integer(topicID))
            }
            if !normalizedQuery.isEmpty {
                sql += " AND LOWER(text) LIKE '%' || LOWER(?) || '%'"
                values.append(.text(normalizedQuery))
            }
            sql += " ORDER BY message_id DESC, fake_id DESC LIMIT ?"
            values.append(.integer(Int64(max(0, limit))))
            return (try? selectMessages(database, sql: sql, values: values)) ?? []
        } ?? []
    }

    public static func revisions(
        transaction: Transaction,
        userID: Int64,
        dialogID: Int64,
        messageID: Int32,
        limit: Int = 100
    ) -> [AyuMessage] {
        migrateLegacyIfNeeded(transaction: transaction, accountID: userID)
        return withDatabase(accountID: userID) { database in
            let sql = "SELECT \(historyColumns) FROM history WHERE user_id=? AND dialog_id=? AND message_id=? AND is_deleted=0 ORDER BY fake_id DESC LIMIT ?"
            let values: [Value] = [
                .integer(userID),
                .integer(dialogID),
                .integer(Int64(messageID)),
                .integer(Int64(max(0, limit)))
            ]
            return (try? selectMessages(database, sql: sql, values: values)) ?? []
        } ?? []
    }

    // MARK: - History writes

    @discardableResult
    public static func appendDeleted(transaction: Transaction, messages snapshots: [AyuMessage]) -> [AyuMessage] {
        append(transaction: transaction, snapshots: snapshots, deleted: true)
    }

    @discardableResult
    public static func appendEdited(transaction: Transaction, messages snapshots: [AyuMessage]) -> [AyuMessage] {
        append(transaction: transaction, snapshots: snapshots, deleted: false)
    }

    private static func append(
        transaction: Transaction,
        snapshots: [AyuMessage],
        deleted: Bool
    ) -> [AyuMessage] {
        guard !snapshots.isEmpty else { return [] }
        var result: [AyuMessage] = []
        for accountID in Set(snapshots.map(\.userID)) {
            migrateLegacyIfNeeded(transaction: transaction, accountID: accountID)
            let scoped = snapshots.filter { $0.userID == accountID }
            let saved = withDatabase(accountID: accountID) { database in
                try? withTransaction(database) {
                    try appendInDatabase(database, snapshots: scoped, deleted: deleted)
                }
            } ?? nil
            result.append(contentsOf: saved ?? [])
        }
        return result
    }

    public static func clearDeleted(
        transaction: Transaction,
        userID: Int64,
        dialogID: Int64,
        topicID: Int64 = 0
    ) {
        migrateLegacyIfNeeded(transaction: transaction, accountID: userID)
        _ = withDatabase(accountID: userID) { database in
            let sql = topicID == 0
                ? "DELETE FROM history WHERE user_id=? AND dialog_id=? AND is_deleted=1"
                : "DELETE FROM history WHERE user_id=? AND dialog_id=? AND topic_id=? AND is_deleted=1"
            let statement = try prepare(database, sql)
            defer { sqlite3_finalize(statement) }
            let values: [Value] = topicID == 0
                ? [.integer(userID), .integer(dialogID)]
                : [.integer(userID), .integer(dialogID), .integer(topicID)]
            try bind(values, to: statement)
            guard sqlite3_step(statement) == SQLITE_DONE else {
                throw StoreError.sqlite(errorMessage(database))
            }
        }
    }

    public static func clearDeletedForAccount(transaction: Transaction, userID: Int64) {
        migrateLegacyIfNeeded(transaction: transaction, accountID: userID)
        _ = withDatabase(accountID: userID) { database in
            try execute(database, "DELETE FROM history WHERE user_id=\(userID) AND is_deleted=1")
        }
    }

    public static func clearAll(transaction: Transaction, userID: Int64? = nil) {
        let accounts = userID.map { [$0] } ?? legacyAccountIDs(transaction: transaction)
        for accountID in accounts {
            migrateLegacyIfNeeded(transaction: transaction, accountID: accountID)
            _ = withDatabase(accountID: accountID) { database in
                try withTransaction(database) {
                    try execute(database, "DELETE FROM history WHERE user_id=\(accountID)")
                    try execute(database, "DELETE FROM received_cache WHERE user_id=\(accountID)")
                }
            }
        }
    }

    // MARK: - Received-message cache

    @discardableResult
    public static func cacheReceived(transaction: Transaction, messages snapshots: [AyuMessage]) -> Int {
        guard !snapshots.isEmpty else { return 0 }
        var changed = 0
        for accountID in Set(snapshots.map(\.userID)) {
            migrateLegacyIfNeeded(transaction: transaction, accountID: accountID)
            let scoped = snapshots.filter { $0.userID == accountID }
            let stored = withDatabase(accountID: accountID) { database in
                try? withTransaction(database) {
                    var updated = 0
                    for snapshot in scoped {
                        let existing = try selectMessages(
                            database,
                            sql: "SELECT cache_id AS fake_id, user_id, dialog_id, peer_id, from_id, from_name, topic_id, message_id, date, edit_date, text, media_path, mime_type, is_deleted, deleted_at FROM received_cache WHERE user_id=? AND dialog_id=? AND topic_id=? AND message_id=? LIMIT 1",
                            values: [
                                .integer(accountID),
                                .integer(snapshot.dialogID),
                                .integer(snapshot.topicID),
                                .integer(Int64(snapshot.messageID))
                            ],
                            received: true
                        ).first
                        if existing.map({ samePayload($0, snapshot) }) != true {
                            try insertReceived(database, message: snapshot)
                            updated += 1
                        }
                    }
                    try trimReceived(database, userID: accountID)
                    return updated
                }
            } ?? nil
            changed += stored ?? 0
        }
        return changed
    }

    @discardableResult
    public static func promoteReceivedToDeleted(
        transaction: Transaction,
        userID: Int64,
        ids: [MessageId]
    ) -> [AyuMessage] {
        guard !ids.isEmpty else { return [] }
        migrateLegacyIfNeeded(transaction: transaction, accountID: userID)
        return withDatabase(accountID: userID) { database in
            (try? withTransaction(database) {
                var matches: [AyuMessage] = []
                var cacheIDs: [Int64] = []
                for id in ids {
                    let rows = try selectMessages(
                        database,
                        sql: "SELECT cache_id AS fake_id, user_id, dialog_id, peer_id, from_id, from_name, topic_id, message_id, date, edit_date, text, media_path, mime_type, is_deleted, deleted_at FROM received_cache WHERE user_id=? AND dialog_id=? AND message_id=?",
                        values: [.integer(userID), .integer(id.peerId.toInt64()), .integer(Int64(id.id))],
                        received: true
                    )
                    if !rows.isEmpty {
                        matches.append(contentsOf: rows)
                        let idsQuery = try prepare(database, "SELECT cache_id FROM received_cache WHERE user_id=? AND dialog_id=? AND message_id=?")
                        try bind([.integer(userID), .integer(id.peerId.toInt64()), .integer(Int64(id.id))], to: idsQuery)
                        while sqlite3_step(idsQuery) == SQLITE_ROW {
                            cacheIDs.append(sqlite3_column_int64(idsQuery, 0))
                        }
                        sqlite3_finalize(idsQuery)
                    }
                }
                guard !matches.isEmpty else { return [] }
                try deleteReceivedRows(database, cacheIDs: cacheIDs)
                let now = Int32(Date().timeIntervalSince1970)
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
                        deletedAt: now
                    )
                }
                return try appendInDatabase(database, snapshots: snapshots, deleted: true)
            }) ?? []
        } ?? []
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
        migrateLegacyIfNeeded(transaction: transaction, accountID: userID)
        return withDatabase(accountID: userID) { database in
            (try? withTransaction(database) {
                let globalIDSet = Set(globalIDs)
                let resolved = Set(resolvedMessageIds.map { "\($0.peerId.toInt64()):\($0.id)" })
                let received = try receivedMessages(database, userID: userID)
                let matches = received.filter { message in
                    guard globalIDSet.contains(message.messageID) else { return false }
                    guard !resolved.contains("\(message.dialogID):\(message.messageID)") else { return false }
                    return allowedPeerNamespaces.contains(PeerId(message.dialogID).namespace._internalGetInt32Value())
                }
                guard !matches.isEmpty else { return [] }
                let matchKeys = Set(matches.map { "\($0.dialogID):\($0.messageID)" })
                let actualRows = try prepare(database, """
                    SELECT cache_id, dialog_id, message_id FROM received_cache WHERE user_id=?
                    """)
                defer { sqlite3_finalize(actualRows) }
                try bind(.integer(userID), to: actualRows, at: 1)
                var deleteIDs: [Int64] = []
                while true {
                    let result = sqlite3_step(actualRows)
                    if result == SQLITE_DONE { break }
                    guard result == SQLITE_ROW else {
                        throw StoreError.sqlite(errorMessage(database))
                    }
                    let key = "\(sqlite3_column_int64(actualRows, 1)):\(sqlite3_column_int(actualRows, 2))"
                    if matchKeys.contains(key) {
                        deleteIDs.append(sqlite3_column_int64(actualRows, 0))
                    }
                }
                try deleteReceivedRows(database, cacheIDs: deleteIDs)
                let now = Int32(Date().timeIntervalSince1970)
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
                        deletedAt: now
                    )
                }
                return try appendInDatabase(database, snapshots: snapshots, deleted: true)
            }) ?? []
        } ?? []
    }

    public static func removeReceivedGlobalIDs(
        transaction: Transaction,
        userID: Int64,
        globalIDs: [Int32],
        excluding resolvedMessageIds: [MessageId],
        allowedPeerNamespaces: Set<Int32>
    ) {
        guard !globalIDs.isEmpty else { return }
        migrateLegacyIfNeeded(transaction: transaction, accountID: userID)
        _ = withDatabase(accountID: userID) { database in
            try withTransaction(database) {
                let globalIDSet = Set(globalIDs)
                let resolved = Set(resolvedMessageIds.map { "\($0.peerId.toInt64()):\($0.id)" })
                let received = try receivedMessages(database, userID: userID)
                let keys = received.filter { message in
                    globalIDSet.contains(message.messageID)
                        && !resolved.contains("\(message.dialogID):\(message.messageID)")
                        && allowedPeerNamespaces.contains(PeerId(message.dialogID).namespace._internalGetInt32Value())
                }
                let targetKeys = Set(keys.map { "\($0.dialogID):\($0.messageID)" })
                let rows = try prepare(database, "SELECT cache_id, dialog_id, message_id FROM received_cache WHERE user_id=?")
                try bind(.integer(userID), to: rows, at: 1)
                var deleteIDs: [Int64] = []
                while sqlite3_step(rows) == SQLITE_ROW {
                    let key = "\(sqlite3_column_int64(rows, 1)):\(sqlite3_column_int(rows, 2))"
                    if targetKeys.contains(key) {
                        deleteIDs.append(sqlite3_column_int64(rows, 0))
                    }
                }
                sqlite3_finalize(rows)
                try deleteReceivedRows(database, cacheIDs: deleteIDs)
            }
        }
    }

    public static func removeReceived(transaction: Transaction, userID: Int64, ids: [MessageId]) {
        guard !ids.isEmpty else { return }
        migrateLegacyIfNeeded(transaction: transaction, accountID: userID)
        _ = withDatabase(accountID: userID) { database in
            try withTransaction(database) {
                let statement = try prepare(database, "DELETE FROM received_cache WHERE user_id=? AND dialog_id=? AND message_id=?")
                defer { sqlite3_finalize(statement) }
                for id in ids {
                    sqlite3_reset(statement)
                    sqlite3_clear_bindings(statement)
                    try bind([
                        .integer(userID),
                        .integer(id.peerId.toInt64()),
                        .integer(Int64(id.id))
                    ], to: statement)
                    guard sqlite3_step(statement) == SQLITE_DONE else {
                        throw StoreError.sqlite(errorMessage(database))
                    }
                }
            }
        }
    }
}
'''

store_path.write_text(source, encoding="utf-8")

build = build_path.read_text(encoding="utf-8")
dependencies = [
    '"//submodules/BuildConfig:BuildConfig",',
    '"//submodules/sqlcipher:sqlcipher",',
]
anchor = '"//submodules/Postbox:Postbox",'
for dependency in dependencies:
    if dependency not in build:
        if build.count(anchor) != 1:
            raise SystemExit("Could not uniquely locate the Postbox dependency in AyuGramIOS/BUILD")
        build = build.replace(anchor, anchor + "\n        " + dependency, 1)
build_path.write_text(build, encoding="utf-8")

required = [
    "import BuildConfig",
    "import sqlcipher",
    "BuildConfig.deviceSpecificEncryptionParameters",
    "PRAGMA key=",
    "CREATE TABLE IF NOT EXISTS history",
    "CREATE TABLE IF NOT EXISTS received_cache",
    "public static func cacheReceived(",
    "public static func promoteReceivedToDeleted(",
    "public static func promoteReceivedGlobalIDsToDeleted(",
    "private static func migrateLegacyIfNeeded(",
]
for marker in required:
    if marker not in source:
        raise SystemExit(f"SQLite history integration invariant missing: {marker}")
if "transaction.setPreferencesEntry(key: key" in source:
    raise SystemExit("History store still writes to Postbox preferences")
print("PASS: deleted history and pre-delete receive cache now use account-scoped SQLCipher/SQLite with legacy Postbox migration.")
