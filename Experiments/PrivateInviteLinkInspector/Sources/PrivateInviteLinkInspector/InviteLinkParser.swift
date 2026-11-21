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

    private static func isValidHash(_ candidate: String) -> Bool {
        return !candidate.isEmpty
            && candidate.range(of: #"^[A-Za-z0-9_-]+$"#, options: .regularExpression) != nil
    }

    /// Parses official Telegram invite-link forms only. It never joins a chat or sends the hash anywhere.
    public static func parse(_ rawValue: String) -> Result<TelegramInvite, InviteLinkParseError> {
        guard let components = URLComponents(string: rawValue.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = components.scheme?.lowercased(),
              components.user == nil,
              components.password == nil,
              components.port == nil,
              components.fragment == nil
        else {
            return .failure(.unsupportedHost)
        }

        let candidate: String
        if scheme == "tg" {
            // Official Telegram deep link: tg://join?invite=HASH.
            guard components.host?.lowercased() == "join",
                  components.path.isEmpty,
                  let items = components.queryItems,
                  items.count == 1,
                  items[0].name == "invite",
                  let value = items[0].value else {
                return .failure(.unsupportedHost)
            }
            candidate = value
        } else {
            guard scheme == "https",
                  let host = components.host?.lowercased(),
                  acceptedHosts.contains(host),
                  components.query == nil else {
                return .failure(.unsupportedHost)
            }

            let path = components.path.split(separator: "/").map(String.init)
            if path.count == 1, path[0].hasPrefix("+") {
                candidate = String(path[0].dropFirst())
            } else if path.count == 2, path[0].lowercased() == "joinchat" {
                candidate = path[1]
            } else {
                return .failure(.malformedPath)
            }
        }

        guard isValidHash(candidate) else {
            return .failure(.invalidHash)
        }
        return .success(TelegramInvite(hash: candidate))
    }
}
