import XCTest
@testable import PrivateInviteLinkInspector

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
}
