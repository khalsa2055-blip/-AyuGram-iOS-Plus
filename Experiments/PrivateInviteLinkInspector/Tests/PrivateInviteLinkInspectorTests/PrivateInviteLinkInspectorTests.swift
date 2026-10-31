import XCTest
@testable import PrivateInviteLinkInspector

final class PrivateInviteLinkInspectorTests: XCTestCase {
    func testPlusInviteLink() {
        XCTAssertEqual(
            PrivateInviteLinkInspector.inspect("https://t.me/+AbC_123-x"),
            .inviteHash("AbC_123-x")
        )
    }

    func testLegacyJoinChatLink() {
        XCTAssertEqual(
            PrivateInviteLinkInspector.inspect("https://t.me/joinchat/AbC123"),
            .inviteHash("AbC123")
        )
    }

    func testTrimsWhitespace() {
        XCTAssertEqual(
            PrivateInviteLinkInspector.inspect("  https://t.me/+abc  "),
            .inviteHash("abc")
        )
    }

    func testRejectsPublicUsername() {
        XCTAssertEqual(PrivateInviteLinkInspector.inspect("https://t.me/somegroup"), .invalid)
    }

    func testRejectsOtherHost() {
        XCTAssertEqual(PrivateInviteLinkInspector.inspect("https://example.com/+abc"), .invalid)
    }

    func testRejectsQueryAndFragment() {
        XCTAssertEqual(PrivateInviteLinkInspector.inspect("https://t.me/+abc?x=1"), .invalid)
        XCTAssertEqual(PrivateInviteLinkInspector.inspect("https://t.me/+abc#x"), .invalid)
    }

    func testRejectsEmptyOrMalformedHash() {
        XCTAssertEqual(PrivateInviteLinkInspector.inspect("https://t.me/+"), .invalid)
        XCTAssertEqual(PrivateInviteLinkInspector.inspect("https://t.me/+bad%20hash"), .invalid)
    }

    func testDoesNotClaimParsedLinkGrantsAccess() {
        XCTAssertTrue(PrivateInviteLinkInspector.requiresTelegramPreviewAuthorization)
    }
}
