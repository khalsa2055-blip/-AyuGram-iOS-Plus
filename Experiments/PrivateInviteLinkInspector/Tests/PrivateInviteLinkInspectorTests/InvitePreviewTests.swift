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

    func testParsesOfficialTelegramSchemeInvite() {
        XCTAssertEqual(
            InviteLinkParser.parse("tg://join?invite=Abc_123-x"),
            .success(TelegramInvite(hash: "Abc_123-x"))
        )
    }

    func testRejectsMalformedTelegramSchemeInvite() {
        let invalidLinks = [
            "tg://join",
            "tg://join?domain=public_group",
            "tg://join?invite=bad.hash",
            "tg://join?invite=first&invite=second",
            "tg://resolve?invite=secret",
            "tg://join/path?invite=secret"
        ]
        for link in invalidLinks {
            if case .success = InviteLinkParser.parse(link) {
                XCTFail("Malformed Telegram deep link must be rejected: \(link)")
            }
        }
    }

    func testRejectsNonTelegramHost() {
        XCTAssertEqual(InviteLinkParser.parse("https://example.com/+secret"), .failure(.unsupportedHost))
    }

    func testRejectsPublicUsernamePath() {
        XCTAssertEqual(InviteLinkParser.parse("https://t.me/public_group"), .failure(.malformedPath))
    }

    func testRejectsNonASCIIAndPercentEncodedHashCharacters() {
        for link in ["https://t.me/+секрет", "https://t.me/+secret%24other", "https://t.me/+bad.hash", "https://t.me/+bad hash"] {
            if case .success = InviteLinkParser.parse(link) {
                XCTFail("Invite hashes must use only the Telegram-safe ASCII alphabet: \\(link)")
            }
        }
    }

    func testRejectsInviteURLWithCredentialsQueryOrFragment() {
        XCTAssertEqual(InviteLinkParser.parse("https://user@t.me/+secret"), .failure(.unsupportedHost))
        XCTAssertEqual(InviteLinkParser.parse("https://t.me/+secret?start=1"), .failure(.unsupportedHost))
        XCTAssertEqual(InviteLinkParser.parse("https://t.me/+secret#fragment"), .failure(.unsupportedHost))
        XCTAssertEqual(InviteLinkParser.parse("https://t.me:443/+secret"), .failure(.unsupportedHost))
    }

    func testPeekSessionOnlyStartsWhenServerGrantsPeek() throws {
        let expiry = Date(timeIntervalSince1970: 2_000_000_000)
        let chat = PeekChat(id: 42, title: "Test", expiresAt: expiry)
        XCTAssertEqual(try PeekSession.start(from: .peek(chat)), PeekSession(chat: chat))

        let deniedResults: [InviteCheckResult] = [
            .basicInfo(title: "Test", participantCount: 10),
            .alreadyMember,
            .approvalRequired,
            .expired,
            .invalid,
            .accessDenied
        ]
        for result in deniedResults {
            XCTAssertThrowsError(try PeekSession.start(from: result)) { error in
                XCTAssertEqual(error as? PeekAccessError, .serverDidNotGrantPeek)
            }
        }
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

        XCTAssertEqual(messages.map(\.text), ["Preview message"])
        let requestCount = await provider.requestCount
        XCTAssertEqual(requestCount, 1)
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

        let requestCount = await provider.requestCount
        XCTAssertEqual(requestCount, 0)
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

        let requestCount = await provider.requestCount
        XCTAssertEqual(requestCount, 0)
    }
}
