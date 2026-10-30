import Foundation

public enum ArchivedMediaKind: String, Codable, Sendable {
    case photo
    case video
    case other
}

public struct MediaEditSnapshot: Codable, Sendable {
    public let messageID: Int64
    public let groupID: Int64
    public let senderName: String
    public let kind: ArchivedMediaKind
    public let bytes: Data
    public let capturedAt: Date

    public init(
        messageID: Int64,
        groupID: Int64,
        senderName: String,
        kind: ArchivedMediaKind,
        bytes: Data,
        capturedAt: Date = Date()
    ) {
        self.messageID = messageID
        self.groupID = groupID
        self.senderName = senderName
        self.kind = kind
        self.bytes = bytes
        self.capturedAt = capturedAt
    }
}

public struct MediaEditRecord: Codable, Sendable, Identifiable {
    public let id: UUID
    public let messageID: Int64
    public let groupID: Int64
    public let senderName: String
    public let originalKind: ArchivedMediaKind
    public let replacementKind: ArchivedMediaKind
    public let originalFileName: String
    public let capturedAt: Date
    public let editedAt: Date
}

public enum MediaEditArchiveError: Error {
    case missingOriginal
    case cannotCreateDirectory
}

/// Local, persistent archive core. Telegram integration must capture the
/// currently available media before applying a server-side message update.
public actor MediaEditArchive {
    private let directory: URL
    private let fileManager: FileManager
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    private var originals: [Int64: MediaEditSnapshot] = [:]
    private var editRecords: [MediaEditRecord] = []

    private var recordsURL: URL {
        directory.appendingPathComponent("edit-records.json")
    }

    public init(directory: URL, fileManager: FileManager = .default) throws {
        self.directory = directory
        self.fileManager = fileManager
        do {
            try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
            let snapshotFiles = try fileManager.contentsOfDirectory(
                at: directory,
                includingPropertiesForKeys: nil
            ).filter { $0.lastPathComponent.hasPrefix("snapshot-") && $0.pathExtension == "json" }

            for url in snapshotFiles {
                let snapshot = try decoder.decode(
                    MediaEditSnapshot.self,
                    from: Data(contentsOf: url)
                )
                originals[snapshot.messageID] = snapshot
            }

            if fileManager.fileExists(atPath: recordsURL.path) {
                editRecords = try decoder.decode([MediaEditRecord].self, from: Data(contentsOf: recordsURL))
            }
        } catch {
            throw MediaEditArchiveError.cannotCreateDirectory
        }
    }

    /// Persist the first snapshot before Telegram replaces the message media.
    /// Repeated captures for the same message never overwrite that first copy.
    public func captureOriginal(_ snapshot: MediaEditSnapshot) throws {
        guard originals[snapshot.messageID] == nil else { return }

        let stem = "snapshot-\(snapshot.messageID)"
        let mediaURL = directory.appendingPathComponent("\(stem).media")
        let metadataURL = directory.appendingPathComponent("\(stem).json")
        try snapshot.bytes.write(to: mediaURL, options: .atomic)

        do {
            try encoder.encode(snapshot).write(to: metadataURL, options: .atomic)
            originals[snapshot.messageID] = snapshot
        } catch {
            try? fileManager.removeItem(at: mediaURL)
            throw error
        }
    }

    /// Call only when the media payload or media kind actually changes.
    /// Caption-only edits must not call this method.
    public func mediaDidChange(
        messageID: Int64,
        replacementKind: ArchivedMediaKind,
        replacementBytes: Data,
        editedAt: Date = Date()
    ) throws -> MediaEditRecord? {
        guard let original = originals[messageID] else {
            throw MediaEditArchiveError.missingOriginal
        }

        guard original.bytes != replacementBytes || original.kind != replacementKind else {
            return nil
        }

        let id = UUID()
        let fileName = "original-\(id.uuidString).media"
        let fileURL = directory.appendingPathComponent(fileName)
        try original.bytes.write(to: fileURL, options: .atomic)

        let record = MediaEditRecord(
            id: id,
            messageID: original.messageID,
            groupID: original.groupID,
            senderName: original.senderName,
            originalKind: original.kind,
            replacementKind: replacementKind,
            originalFileName: fileName,
            capturedAt: original.capturedAt,
            editedAt: editedAt
        )

        editRecords.append(record)
        do {
            try encoder.encode(editRecords).write(to: recordsURL, options: .atomic)
        } catch {
            editRecords.removeLast()
            try? fileManager.removeItem(at: fileURL)
            throw error
        }
        return record
    }

    public func originalMedia(for record: MediaEditRecord) throws -> Data {
        try Data(contentsOf: directory.appendingPathComponent(record.originalFileName))
    }

    /// Records are reloaded from disk when the archive is recreated.
    public func allEditRecords() -> [MediaEditRecord] {
        editRecords
    }
}
