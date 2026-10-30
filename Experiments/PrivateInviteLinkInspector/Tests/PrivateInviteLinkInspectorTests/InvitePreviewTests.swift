import XCTest
@testable import PrivateInviteLinkInspector

private actor MockPeekMessageProvider: PeekMessageProvider {
    private(set) var requestCount = 0

    func fetchMessages(for session: PeekSession, limit: Int) async throws -> [PreviewMessage] {
        requestCount += 1
        return [
            PreviewMessage(
                id: 1,
                senderDisplayName: "Test sender",
                text: "Preview message",
                timestamp: Date(timeIntervalSince1970: 50),
                mediaKind: nil
            )
        ]
    }
}

final class InvitePreviewTests: XCTestCase {
    func testParsesPlusInvite() {
        XCTAssertEqual(
            InviteLinkParser.parse("https://t.me/+Abc_123-x"),
            .success(TelegramInvite(hash: "Abc_123-x"))
        )
    }

    func testParsesLegacyJoinChatInvite() {
        XCTAssertEqual(
            InviteLinkParser.parse("https://telegram.me/joinchat/AbC-123"),
            .success(TelegramInvite(hash: "AbC-123"))
        )
    }

    func testRejectsNonTelegramHost() {
        XCTAssertEqual(InviteLinkParser.parse("https://example.com/+secret"), .failure(.unsupportedHost))
    }

    func testRejectsPublicUsernamePath() {
        XCTAssertEqual(InviteLinkParser.parse("https://t.me/public_group"), .failure(.malformedPath))
    }

    func testPeekSessionOnlyStartsWhenServerGrantsPeek() throws {
        let expiry = Date(timeIntervalSince1970: 2_000_000_000)
        let chat = PeekChat(id: 42, title: "Test", expiresAt: expiry)
        XCTAssertEqual(try PeekSession.start(from: .peek(chat)), PeekSession(chat: chat))
        XCTAssertThrowsError(try PeekSession.start(from: .basicInfo(title: "Test", participantCount: 10)))
        XCTAssertThrowsError(try PeekSession.start(from: .approvalRequired))
    }

    func testPeekSessionExpires() throws {
        let expiry = Date(timeIntervalSince1970: 100)
        let session = try PeekSession.start(from: .peek(PeekChat(id: 1, title: "Test", expiresAt: expiry)))
        XCTAssertNoThrow(try session.authorizeRead(at: Date(timeIntervalSince1970: 99)))
        XCTAssertThrowsError(try session.authorizeRead(at: expiry)) { error in
            XCTAssertEqual(error as? PeekAccessError, .peekExpired)
        }
    }

    func testAuthorizedPeekFetchesMessages() async throws {
        let provider = MockPeekMessageProvider()
        let session = try PeekSession.start(
            from: .peek(PeekChat(id: 7, title: "Private group", expiresAt: Date(timeIntervalSince1970: 200)))
        )

        let messages = try await session.fetchMessages(
            using: provider,
            limit: 20,
            now: Date(timeIntervalSince1970: 100)
        )

        XCTAssertEqual(messages.map(\\.text), ["Preview message"])
        XCTAssertEqual(await provider.requestCount, 1)
    }

    func testExpiredPeekDoesNotCallProvider() async throws {
        let provider = MockPeekMessageProvider()
        let session = try PeekSession.start(
            from: .peek(PeekChat(id: 7, title: "Private group", expiresAt: Date(timeIntervalSince1970: 100)))
        )

        do {
            _ = try await session.fetchMessages(
                using: provider,
                limit: 20,
                now: Date(timeIntervalSince1970: 100)
            )
            XCTFail("An expired peek must not fetch messages")
        } catch {
            XCTAssertEqual(error as? PeekAccessError, .peekExpired)
        }

        XCTAssertEqual(await provider.requestCount, 0)
    }

    func testInvalidLimitDoesNotCallProvider() async throws {
        let provider = MockPeekMessageProvider()
        let session = try PeekSession.start(
            from: .peek(PeekChat(id: 7, title: "Private group", expiresAt: Date(timeIntervalSince1970: 200)))
        )

        do {
            _ = try await session.fetchMessages(
                using: provider,
                limit: 101,
                now: Date(timeIntervalSince1970: 100)
            )
            XCTFail("The fetch limit must be bounded")
        } catch {
            XCTAssertEqual(error as? PeekAccessError, .invalidMessageLimit)
        }

        XCTAssertEqual(await provider.requestCount, 0)
    }
}
