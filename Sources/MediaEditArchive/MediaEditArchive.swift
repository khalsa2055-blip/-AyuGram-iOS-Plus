import Foundation

public enum ArchivedMediaKind: String, Codable, Sendable {
    case photo
    case video
    case other
}

public struct MediaEditSnapshot: Sendable {
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

/// Standalone archive core. The Telegram integration must call captureOriginal
/// while the old media is still available and before applying the server update.
public actor MediaEditArchive {
    private let directory: URL
    private let fileManager: FileManager
    private var originals: [Int64: MediaEditSnapshot] = [:]

    public init(directory: URL, fileManager: FileManager = .default) throws {
        self.directory = directory
        self.fileManager = fileManager
        do {
            try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        } catch {
            throw MediaEditArchiveError.cannotCreateDirectory
        }
    }

    /// Cache the currently displayed media before processing an edit update.
    /// The first snapshot is retained so repeated edits never overwrite it.
    public func captureOriginal(_ snapshot: MediaEditSnapshot) {
        guard originals[snapshot.messageID] == nil else { return }
        originals[snapshot.messageID] = snapshot
    }

    /// Call when Telegram delivers a changed media payload. Caption-only edits
    /// should not call this method, so they do not create false edit markers.
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
        let fileName = "\(id.uuidString).media"
        let fileURL = directory.appendingPathComponent(fileName)
        try replacementSafeWrite(original.bytes, to: fileURL)

        return MediaEditRecord(
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
    }

    public func originalMedia(for record: MediaEditRecord) throws -> Data {
        try Data(contentsOf: directory.appendingPathComponent(record.originalFileName))
    }

    private func replacementSafeWrite(_ data: Data, to url: URL) throws {
        try data.write(to: url, options: .atomic)
    }
}
