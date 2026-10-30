import Foundation

public struct TelegramInvite: Equatable, Sendable {
    public let hash: String

    public init(hash: String) {
        self.hash = hash
    }
}

public enum InviteLinkParseError: Error, Equatable {
    case unsupportedHost
    case malformedPath
    case invalidHash
}

public enum InviteLinkParser {
    private static let acceptedHosts: Set<String> = [
        "t.me", "www.t.me", "telegram.me", "www.telegram.me",
        "t.dog", "telegram.dog"
    ]

    /// Parses invite links only. It never joins a chat or sends the hash anywhere.
    public static func parse(_ rawValue: String) -> Result<TelegramInvite, InviteLinkParseError> {
        guard let components = URLComponents(string: rawValue.trimmingCharacters(in: .whitespacesAndNewlines)),
              let host = components.host?.lowercased(),
              acceptedHosts.contains(host),
              components.scheme?.lowercased() == "https" || components.scheme?.lowercased() == "http"
        else {
            return .failure(.unsupportedHost)
        }

        let path = components.path.split(separator: "/").map(String.init)
        let candidate: String
        if path.count == 1, path[0].hasPrefix("+") {
            candidate = String(path[0].dropFirst())
        } else if path.count == 2, path[0].lowercased() == "joinchat" {
            candidate = path[1]
        } else {
            return .failure(.malformedPath)
        }

        guard !candidate.isEmpty,
              candidate.range(of: #"^[A-Za-z0-9_-]+$"#, options: .regularExpression) != nil
        else {
            return .failure(.invalidHash)
        }
        return .success(TelegramInvite(hash: candidate))
    }
}
