import Foundation

public struct PeekChat: Equatable, Sendable {
    public let id: Int64
    public let title: String
    public let expiresAt: Date

    public init(id: Int64, title: String, expiresAt: Date) {
        self.id = id
        self.title = title
        self.expiresAt = expiresAt
    }
}

/// Normalized outcomes from Telegram messages.checkChatInvite.
/// The MTProto adapter must map Telegram's chatInvitePeek constructor to .peek.
/// It must never call messages.importChatInvite as part of preview.
public enum InviteCheckResult: Equatable, Sendable {
    case peek(PeekChat)
    case basicInfo(title: String, participantCount: Int?)
    case alreadyMember
    case approvalRequired
    case expired
    case invalid
    case accessDenied
}

public enum PeekAccessError: Error, Equatable {
    case serverDidNotGrantPeek
    case peekExpired
    case invalidMessageLimit
}

/// Central guard for history/media requests. Only a server-issued peek session can read,
/// and it stops at the server-provided expiry time.
public struct PeekSession: Equatable, Sendable {
    public let chat: PeekChat

    public init(chat: PeekChat) {
        self.chat = chat
    }

    public func authorizeRead(at now: Date = Date()) throws {
        guard now < chat.expiresAt else {
            throw PeekAccessError.peekExpired
        }
    }

    public static func start(from result: InviteCheckResult) throws -> PeekSession {
        guard case let .peek(chat) = result else {
            throw PeekAccessError.serverDidNotGrantPeek
        }
        return PeekSession(chat: chat)
    }

    /// The only supported entry point for preview message retrieval.
    /// Authorization is checked immediately before every request.
    public func fetchMessages(
        using provider: any PeekMessageProvider,
        limit: Int,
        now: Date = Date()
    ) async throws -> [PreviewMessage] {
        guard (1...100).contains(limit) else {
            throw PeekAccessError.invalidMessageLimit
        }
        try authorizeRead(at: now)
        return try await provider.fetchMessages(for: self, limit: limit)
    }
}

/// Read-only boundary used by the app's MTProto integration.
/// Implementations should use messages.getHistory/channels.getMessages only after
/// PeekSession authorization succeeds. No send, join, or import operation is exposed.
public protocol PeekMessageProvider: Sendable {
    func fetchMessages(for session: PeekSession, limit: Int) async throws -> [PreviewMessage]
}

public struct PreviewMessage: Equatable, Sendable {
    public let id: Int32
    public let senderDisplayName: String?
    public let text: String
    public let timestamp: Date
    public let mediaKind: MediaKind?

    public init(id: Int32, senderDisplayName: String?, text: String, timestamp: Date, mediaKind: MediaKind?) {
        self.id = id
        self.senderDisplayName = senderDisplayName
        self.text = text
        self.timestamp = timestamp
        self.mediaKind = mediaKind
    }
}

public enum MediaKind: String, Equatable, Sendable {
    case photo, video, voice, audio, document, animation
}
