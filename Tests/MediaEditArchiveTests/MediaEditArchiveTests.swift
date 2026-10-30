import XCTest
@testable import MediaEditArchive

final class MediaEditArchiveTests: XCTestCase {
    func testPhotoReplacedByBlackFrameArchivesOriginal() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let archive = try MediaEditArchive(directory: directory)
        let original = Data([0x10, 0x20, 0x30, 0x40])
        try await archive.captureOriginal(.init(
            messageID: 100, groupID: 7, senderName: "sender",
            kind: .photo, bytes: original
        ))

        let record = try await archive.mediaDidChange(
            messageID: 100, replacementKind: .photo,
            replacementBytes: Data(repeating: 0, count: 4)
        )

        XCTAssertNotNil(record)
        let archived = try await archive.originalMedia(for: XCTUnwrap(record))
        XCTAssertEqual(archived, original)
    }

    func testVideoReplacedWithDifferentMediaArchivesOriginal() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let archive = try MediaEditArchive(directory: directory)
        let original = Data("original-video".utf8)
        try await archive.captureOriginal(.init(
            messageID: 101, groupID: 7, senderName: "sender",
            kind: .video, bytes: original
        ))

        let record = try await archive.mediaDidChange(
            messageID: 101, replacementKind: .video,
            replacementBytes: Data("black-video".utf8)
        )

        XCTAssertNotNil(record)
        let archived = try await archive.originalMedia(for: XCTUnwrap(record))
        XCTAssertEqual(archived, original)
    }

    func testUnchangedMediaDoesNotCreateEditRecord() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let archive = try MediaEditArchive(directory: directory)
        let bytes = Data("same-media".utf8)
        try await archive.captureOriginal(.init(
            messageID: 102, groupID: 7, senderName: "sender",
            kind: .photo, bytes: bytes
        ))

        let record = try await archive.mediaDidChange(
            messageID: 102, replacementKind: .photo, replacementBytes: bytes
        )
        XCTAssertNil(record)
    }

    func testRepeatedCaptureDoesNotOverwriteFirstOriginal() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let archive = try MediaEditArchive(directory: directory)
        let first = Data("first".utf8)
        try await archive.captureOriginal(.init(
            messageID: 103, groupID: 7, senderName: "sender",
            kind: .photo, bytes: first
        ))
        try await archive.captureOriginal(.init(
            messageID: 103, groupID: 7, senderName: "sender",
            kind: .photo, bytes: Data("second".utf8)
        ))

        let record = try await archive.mediaDidChange(
            messageID: 103, replacementKind: .photo, replacementBytes: Data("black".utf8)
        )
        let archived = try await archive.originalMedia(for: XCTUnwrap(record))
        XCTAssertEqual(archived, first)
    }
}
