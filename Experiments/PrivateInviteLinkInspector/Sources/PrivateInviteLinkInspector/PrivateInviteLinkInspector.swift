import Foundation

/// Parses Telegram invite URLs without joining a chat or changing account membership.
/// This component deliberately does not attempt to fetch private chat contents.
public enum PrivateInviteLinkInspector {
    public enum Inspection: Equatable, Sendable {
        case inviteHash(String)
        case invalid
    }

    /// Accepts https://t.me/+HASH and https://t.me/joinchat/HASH invite links.
    /// Public usernames and unrelated hosts are not treated as private invites.
    public static func inspect(_ rawValue: String) -> Inspection {
        let value = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty,
              let components = URLComponents(string: value),
              let scheme = components.scheme?.lowercased(),
              scheme == "https" || scheme == "http",
              let host = components.host?.lowercased(),
              host == "t.me" || host == "www.t.me",
              components.user == nil,
              components.password == nil,
              components.query == nil,
              components.fragment == nil
        else { return .invalid }

        let parts = components.path.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
        let candidate: String
        if parts.count == 1, parts[0].hasPrefix("+") {
            candidate = String(parts[0].dropFirst())
        } else if parts.count == 2, parts[0].lowercased() == "joinchat" {
            candidate = parts[1]
        } else {
            return .invalid
        }

        guard !candidate.isEmpty,
              candidate.count <= 256,
              candidate.unicodeScalars.allSatisfy({
                  CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-").contains($0)
              })
        else { return .invalid }

        return .inviteHash(candidate)
    }

    /// A parsed invite hash is not proof of access. Actual preview data must come
    /// from Telegram's authorized invite-preview response; this inspector never joins.
    public static let requiresTelegramPreviewAuthorization = true
}
