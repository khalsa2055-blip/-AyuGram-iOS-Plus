#!/usr/bin/env python3
"""Wire the private invite entry into Swiftgram and audit Telegram's native peek path.

The entry screen forwards a validated invite URL to Telegram's existing URL resolver.
That resolver owns authorization and opens ChatPeekTimeout only when Telegram grants peek.
This patch never joins a group or fetches private history directly.
"""
from pathlib import Path
import argparse
import sys

def require(path: Path, needles: tuple[str, ...], label: str) -> str:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing upstream source: {path}")
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"FAIL: {label} is missing required source anchors: {missing}")
    return text

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"FAIL: {label}: expected one anchor, found {count}")
    return source.replace(old, new, 1)

ENTRY_CONTROLLER = r'''
private func sgPrivateInviteHash(_ raw: String) -> String? {
    guard let components = URLComponents(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
          let scheme = components.scheme?.lowercased(),
          components.fragment == nil,
          components.user == nil,
          components.password == nil,
          components.port == nil else {
        return nil
    }

    let hash: String
    if scheme == "tg" {
        guard components.host?.lowercased() == "join",
              components.path.isEmpty,
              let items = components.queryItems,
              items.count == 1,
              items[0].name == "invite",
              let value = items[0].value else {
            return nil
        }
        hash = value
    } else {
        guard scheme == "https",
              let host = components.host?.lowercased(),
              ["t.me", "www.t.me", "telegram.me", "www.telegram.me", "t.dog", "telegram.dog"].contains(host),
              components.query == nil else {
            return nil
        }
        let parts = components.path.split(separator: "/", omittingEmptySubsequences: true)
        if parts.count == 1, parts[0].hasPrefix("+") {
            hash = String(parts[0].dropFirst())
        } else if parts.count == 2, parts[0].lowercased() == "joinchat" {
            hash = String(parts[1])
        } else {
            return nil
        }
    }

    guard !hash.isEmpty,
          hash.unicodeScalars.allSatisfy({
              let value = $0.value
              return (48...57).contains(value)
                  || (65...90).contains(value)
                  || (97...122).contains(value)
                  || value == 45
                  || value == 95
          }) else {
        return nil
    }
    return hash
}

private final class SGPrivateInviteEntryView: UIView {
    var onPreview: ((String) -> Void)?
    private let field = UITextField()
    private let button = UIButton(type: .system)
    private let errorLabel = UILabel()
    private let infoLabel = UILabel()

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .systemBackground
        field.placeholder = "https://t.me/+…"
        field.borderStyle = .roundedRect
        field.keyboardType = .URL
        field.autocapitalizationType = .none
        field.autocorrectionType = .no
        field.clearButtonMode = .whileEditing
        field.accessibilityIdentifier = "privateInviteURLField"

        button.setTitle("Preview", for: .normal)
        button.titleLabel?.font = .preferredFont(forTextStyle: .headline)
        button.addTarget(self, action: #selector(previewPressed), for: .touchUpInside)
        button.accessibilityIdentifier = "privateInvitePreviewButton"

        errorLabel.font = .preferredFont(forTextStyle: .footnote)
        errorLabel.textColor = .systemRed
        errorLabel.numberOfLines = 0
        errorLabel.isHidden = true

        infoLabel.font = .preferredFont(forTextStyle: .body)
        infoLabel.textColor = .secondaryLabel
        infoLabel.numberOfLines = 0
        infoLabel.isHidden = true

        let stack = UIStackView(arrangedSubviews: [field, button, errorLabel, infoLabel])
        stack.axis = .vertical
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: safeAreaLayoutGuide.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: safeAreaLayoutGuide.trailingAnchor, constant: -20),
            stack.topAnchor.constraint(equalTo: safeAreaLayoutGuide.topAnchor, constant: 24),
            field.heightAnchor.constraint(equalToConstant: 48),
            button.heightAnchor.constraint(equalToConstant: 48)
        ])
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func setLoading(_ loading: Bool) {
        button.isEnabled = !loading
        field.isEnabled = !loading
        button.setTitle(loading ? "Checking…" : "Preview", for: .normal)
    }

    func clearMessage() {
        errorLabel.text = nil
        errorLabel.isHidden = true
        infoLabel.text = nil
        infoLabel.isHidden = true
    }

    func showMessage(_ message: String) {
        infoLabel.text = nil
        infoLabel.isHidden = true
        errorLabel.text = message
        errorLabel.isHidden = false
    }

    func showStatus(_ message: String) {
        errorLabel.text = nil
        errorLabel.isHidden = true
        infoLabel.text = message
        infoLabel.isHidden = false
    }

    func showInviteInfo(_ invite: ExternalJoiningChatState.Invite) {
        let type: String
        if invite.flags.isChannel {
            type = invite.flags.isMegagroup ? "Supergroup" : "Channel"
        } else {
            type = "Basic group"
        }
        var details = [invite.title, type]
        if invite.participantsCount > 0 {
            let count = NumberFormatter.localizedString(
                from: NSNumber(value: invite.participantsCount),
                number: .decimal
            )
            details.append("\(count) members")
        }
        if let about = invite.about?.trimmingCharacters(in: .whitespacesAndNewlines), !about.isEmpty {
            details.append(about)
        }
        if invite.flags.requestNeeded {
            details.append("Admin approval is required to join, but this preview has not sent a request.")
        }
        details.append("Telegram returned invite information instead of chatInvitePeek. Message preview is unavailable for this link. No join or request was sent.")
        showStatus(details.joined(separator: "\n\n"))
    }

    @objc private func previewPressed() {
        let raw = (field.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard sgPrivateInviteHash(raw) != nil else {
            showMessage("Enter a valid HTTPS Telegram invite link (t.me/+… or joinchat).")
            return
        }
        clearMessage()
        setLoading(true)
        endEditing(true)
        onPreview?(raw)
    }
}

private final class SGPrivateInvitePreviewController: ViewController {
    private let context: AccountContext
    private let previewDisposable = MetaDisposable()

    init(context: AccountContext) {
        self.context = context
        super.init(navigationBarPresentationData: nil)
        self.title = "Private Group Preview"
    }

    deinit {
        self.previewDisposable.dispose()
    }

    required init(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func showPreviewError(_ message: String, in entryView: SGPrivateInviteEntryView) {
        entryView.setLoading(false)
        entryView.showMessage(message)
    }

    override func loadDisplayNode() {
        let entryView = SGPrivateInviteEntryView()
        entryView.onPreview = { [weak self, weak entryView] raw in
            guard let self, let entryView else { return }
            guard let hash = sgPrivateInviteHash(raw) else {
                self.showPreviewError("This invite link is not valid.", in: entryView)
                return
            }

            self.previewDisposable.set((
                self.context.engine.peers.joinLinkInformation(hash)
                |> deliverOnMainQueue
            ).start(next: { [weak self, weak entryView] result in
                guard let self, let entryView else { return }
                entryView.setLoading(false)

                switch result {
                case let .peek(peer, deadline):
                    guard let navigationController = self.context.sharedContext.mainWindow?.viewController as? NavigationController else {
                        entryView.showMessage("Telegram granted peek, but the chat navigation is unavailable.")
                        return
                    }
                    self.context.sharedContext.navigateToChatController(
                        NavigateToChatControllerParams(
                            navigationController: navigationController,
                            context: self.context,
                            chatLocation: .peer(peer),
                            subject: nil,
                            peekData: ChatPeekTimeout(deadline: deadline, linkData: hash)
                        )
                    )
                    self.dismiss()
                case let .invite(invite):
                    entryView.showInviteInfo(invite)
                case let .alreadyJoined(peer):
                    guard let navigationController = self.context.sharedContext.mainWindow?.viewController as? NavigationController else {
                        entryView.showStatus("You already belong to this group. Open it from your chat list.")
                        return
                    }
                    self.context.sharedContext.navigateToChatController(
                        NavigateToChatControllerParams(
                            navigationController: navigationController,
                            context: self.context,
                            chatLocation: .peer(peer),
                            subject: nil
                        )
                    )
                    self.dismiss()
                case .invalidHash:
                    entryView.showMessage("Telegram could not verify this invite. It may be invalid or expired.")
                }
            }, error: { [weak self, weak entryView] error in
                guard let self, let entryView else { return }
                let message: String
                switch error {
                case .flood:
                    message = "Telegram is temporarily limiting invite checks. Try again later."
                case .generic:
                    message = "Telegram could not verify this invite link. Check the link and connection."
                }
                self.showPreviewError(message, in: entryView)
            }))
        }
        self.displayNode = ASDisplayNode(viewBlock: { entryView })
        self.displayNodeDidLoad()
    }
}

'''

def patch_app_entry(upstream: Path) -> None:
    settings = upstream / "Swiftgram/SGSettingsUI/Sources/SGSettingsController.swift"
    source = require(settings, (
        "private enum SGDisclosureLink: String {",
        "case contentSettings",
        "entries.append(.searchInput(id: id.count, section: .search",
        "case .contentSettings:",
        "pushControllerImpl?(context.sharedContext.makeLocalizationListController(context: context))",
    ), "Swiftgram settings integration")

    if "SGPrivateInvitePreviewController" in source:
        print("PASS: private invite settings entry already patched")
        return

    source = replace_once(source, "import UIKit\n", "import UIKit\nimport AsyncDisplayKit\n", "AsyncDisplayKit import")
    source = replace_once(
        source,
        "private enum SGDisclosureLink: String {\n    case contentSettings",
        "private enum SGDisclosureLink: String {\n    case privateInvitePreview\n    case contentSettings",
        "settings disclosure enum"
    )
    source = replace_once(
        source,
        "entries.append(.searchInput(id: id.count, section: .search, title: NSAttributedString(string: \"🔍\"), text: state.searchQuery ?? \"\", placeholder: strings.Common_Search))",
        "entries.append(.searchInput(id: id.count, section: .search, title: NSAttributedString(string: \"🔍\"), text: state.searchQuery ?? \"\", placeholder: strings.Common_Search))\n    entries.append(.disclosure(id: id.count, section: .content, link: .privateInvitePreview, text: \"Private Group Preview\"))",
        "private invite settings row"
    )
    source = replace_once(
        source,
        "        switch (link) {\n            case .languageSettings:",
        "        switch (link) {\n            case .privateInvitePreview:\n                pushControllerImpl?(SGPrivateInvitePreviewController(context: context))\n            case .languageSettings:",
        "private invite settings navigation"
    )
    source = replace_once(
        source,
        "public func sgSettingsController(context: AccountContext",
        ENTRY_CONTROLLER + "\npublic func sgSettingsController(context: AccountContext",
        "private invite entry controller insertion"
    )
    settings.write_text(source, encoding="utf-8")
    print(f"PASS: added Settings > Private Group Preview in {settings}")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()

    patch_app_entry(args.upstream)

    core = args.upstream / "submodules/TelegramCore/Sources/TelegramEngine/Peers/JoinLink.swift"
    ui = args.upstream / "submodules/JoinLinkPreviewUI/Sources/JoinLinkPreviewController.swift"
    route = args.upstream / "submodules/TelegramUI/Sources/OpenResolvedUrl.swift"

    require(core, (
        "messages.checkChatInvite(hash:",
        "case let .chatInvite(chatInviteData):",
        "case let .chatInvitePeek(chatInvitePeekData):",
        "return .peek(EnginePeer(peer), expires)",
    ), "server invite result mapping")
    ui_text = require(ui, (
        "case let .invite(invite):",
        "case let .peek(peer, deadline):",
        "ChatPeekTimeout(deadline: deadline, linkData:",
    ), "native preview UI")
    require(route, (
        "case let .peek(peer, deadline):",
        "peekData: ChatPeekTimeout(deadline: deadline, linkData:",
        "JoinLinkPreviewController(context: context, link: link",
    ), "deep-link navigation")

    package_source = args.package / "Sources/PrivateInviteLinkInspector/PeekAccess.swift"
    require(package_source, (
        "case peek(PeekChat)",
        "case basicInfo(title: String, participantCount: Int?)",
        "case accessDenied",
        "guard case let .peek(chat) = result",
    ), "isolated access-state model")

    peek_branch = ui_text.split("case let .peek(peer, deadline):", 1)[1].split("case .invalidHash:", 1)[0]
    forbidden = ("joinChatInteractively", "importChatInvite", "messages.getHistory")
    found = [token for token in forbidden if token in peek_branch]
    if found:
        raise SystemExit(f"FAIL: forbidden operation in native peek branch: {found}")

    print("PASS: settings entry forwards invite URLs to Telegram's native resolver.")
    print("PASS: server-granted peek uses ChatPeekTimeout; metadata/denied states do not expose messages.")
    print("PASS: no automatic import/join or standalone history request in the peek branch.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
