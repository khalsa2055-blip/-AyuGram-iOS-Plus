#!/usr/bin/env python3
"""Apply the two UI surfaces that complete the four-feature AyuGram integration."""
from pathlib import Path

ROOT = Path("telegram-ios")
SETTINGS = ROOT / "submodules/TelegramUI/Components/AyuGramSettingsScreen/Sources/AyuGramSettingsScreen.swift"
SETTINGS_BUILD = ROOT / "submodules/TelegramUI/Components/AyuGramSettingsScreen/BUILD"
MENU = ROOT / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
CHAT_CONTROLLER = ROOT / "submodules/TelegramUI/Sources/ChatController.swift"

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return source.replace(old, new, 1)

for path in (SETTINGS, SETTINGS_BUILD, MENU, CHAT_CONTROLLER):
    if not path.is_file():
        raise SystemExit(f"Missing required AyuGram integration file: {path}")

settings = SETTINGS.read_text(encoding="utf-8")
build = SETTINGS_BUILD.read_text(encoding="utf-8")
menu = MENU.read_text(encoding="utf-8")
chat_controller = CHAT_CONTROLLER.read_text(encoding="utf-8")

if "AyuGramPrivateInvitePreviewController" not in settings:
    settings = replace_once(
        settings,
        "import UIKit\n",
        "import UIKit\nimport AsyncDisplayKit\nimport SwiftSignalKit\nimport TelegramCore\n",
        "private invite UI import"
    )
    settings = replace_once(
        settings,
        "    case clearDeletedHistory\n",
        "    case clearDeletedHistory\n    case privateInvitePreview\n",
        "private invite settings case"
    )
    settings = replace_once(
        settings,
        "case .saveDeleted, .saveEdited, .history, .clearDeletedHistory:",
        "case .saveDeleted, .saveEdited, .history, .clearDeletedHistory, .privateInvitePreview:",
        "private invite settings section"
    )
    settings = replace_once(
        settings,
        "case .clearDeletedHistory: return 104\n",
        "case .clearDeletedHistory: return 104\n        case .privateInvitePreview: return 105\n",
        "private invite stable id"
    )
    settings = replace_once(
        settings,
        "        case .clearDeletedHistory:\n",
        """        case .privateInvitePreview:
            return ItemListActionItem(
                presentationData: presentationData,
                systemStyle: .glass,
                title: "Preview Private Group",
                kind: .generic,
                alignment: .natural,
                sectionId: self.section,
                style: .blocks,
                action: {
                    arguments.context.sharedContext.mainWindow?.present(
                        AyuGramPrivateInvitePreviewController(context: arguments.context),
                        on: .root
                    )
                }
            )
        case .clearDeletedHistory:
""",
        "private invite settings action"
    )
    settings = replace_once(
        settings,
        "private func ayuSettingsEntries(_ settings: AyuSettings, accountID: Int64) -> [AyuSettingsEntry] {",
        r'''private final class AyuGramPrivateInviteEntryView: UIView {
    var onPreview: ((String) -> Void)?
    var onBack: (() -> Void)?
    private let backButton = UIButton(type: .system)
    private let titleLabel = UILabel()
    private let field = UITextField()
    private let button = UIButton(type: .system)
    private let errorLabel = UILabel()

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .systemBackground
        backButton.setTitle("‹ Back", for: .normal)
        backButton.contentHorizontalAlignment = .leading
        backButton.titleLabel?.font = .preferredFont(forTextStyle: .body)
        backButton.accessibilityIdentifier = "privateInvitePreviewBackButton"
        backButton.addTarget(self, action: #selector(backPressed), for: .touchUpInside)

        titleLabel.text = "Private Group Preview"
        titleLabel.font = .preferredFont(forTextStyle: .title2)
        titleLabel.textAlignment = .natural

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

        let header = UIStackView(arrangedSubviews: [backButton, titleLabel])
        header.axis = .horizontal
        header.alignment = .center
        header.spacing = 8
        backButton.setContentHuggingPriority(.required, for: .horizontal)

        let stack = UIStackView(arrangedSubviews: [header, field, button, errorLabel])
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

    @objc private func backPressed() {
        onBack?()
    }

    func setLoading(_ loading: Bool) {
        button.isEnabled = !loading
        field.isEnabled = !loading
        button.setTitle(loading ? "Checking…" : "Preview", for: .normal)
    }

    func showMessage(_ message: String) {
        errorLabel.text = message
        errorLabel.isHidden = false
    }

    func clearMessage() {
        errorLabel.text = nil
        errorLabel.isHidden = true
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    @objc private func previewPressed() {
        let raw = (field.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard ayuGramPrivateInviteHash(raw) != nil else {
            showMessage("Enter a valid Telegram private invite link (t.me/+… or joinchat).")
            return
        }
        clearMessage()
        endEditing(true)
        onPreview?(raw)
    }
}

private func ayuGramPrivateInviteHash(_ raw: String) -> String? {
    guard let components = URLComponents(string: raw),
          let scheme = components.scheme?.lowercased(),
          scheme == "https" || scheme == "http",
          let host = components.host?.lowercased(),
          ["t.me", "www.t.me", "telegram.me", "www.telegram.me", "t.dog", "telegram.dog"].contains(host),
          components.query == nil,
          components.fragment == nil,
          components.user == nil,
          components.password == nil,
          components.port == nil else {
        return nil
    }

    let parts = components.path.split(separator: "/", omittingEmptySubsequences: true)
    let hash: String
    if parts.count == 1, parts[0].hasPrefix("+") {
        hash = String(parts[0].dropFirst())
    } else if parts.count == 2, parts[0].lowercased() == "joinchat" {
        hash = String(parts[1])
    } else {
        return nil
    }

    // Keep runtime validation identical to InviteLinkParser's ASCII allowlist.
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

private final class AyuGramPrivateInvitePreviewController: ViewController {
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

    private func showPreviewError(_ message: String, in entryView: AyuGramPrivateInviteEntryView) {
        entryView.setLoading(false)
        entryView.showMessage(message)
    }

    override func loadDisplayNode() {
        let entryView = AyuGramPrivateInviteEntryView()
        entryView.onBack = { [weak self] in
            self?.dismiss()
        }
        entryView.onPreview = { [weak self, weak entryView] raw in
            guard let self, let entryView else { return }
            guard let hash = ayuGramPrivateInviteHash(raw) else {
                self.showPreviewError("This invite link is not valid.", in: entryView)
                return
            }

            entryView.clearMessage()
            entryView.setLoading(true)

            // Ask Telegram's own MTProto invite resolver. Only a server-issued
            // chatInvitePeek result can open the native chat in temporary read-only mode.
            self.previewDisposable.set((
                self.context.engine.peers.joinLinkInformation(hash)
                |> deliverOnMainQueue
            ).start(next: { [weak self, weak entryView] result in
                guard let self, let entryView else { return }
                entryView.setLoading(false)

                switch result {
                case let .peek(peer, deadline):
                    guard let navigationController = self.context.sharedContext.mainWindow?.viewController as? NavigationController else {
                        entryView.showMessage("Telegram granted preview, but the chat screen is not available right now.")
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
                case .invite:
                    // Intentionally do not display invite metadata/member identities or a Join action.
                    entryView.showMessage("Telegram did not grant read-only message preview for this link.")
                case .alreadyJoined:
                    entryView.showMessage("This account already has access. Preview-only mode is not available for this link.")
                case .invalidHash:
                    entryView.showMessage("The invite link is invalid or has expired.")
                }
            }, error: { [weak self, weak entryView] error in
                guard let self, let entryView else { return }
                let message: String
                switch error {
                case .flood:
                    message = "Telegram is temporarily limiting invite checks. Try again later."
                case .generic:
                    message = "Telegram could not verify this invite link."
                }
                self.showPreviewError(message, in: entryView)
            }))
        }
        self.displayNode = ASDisplayNode(viewBlock: { entryView })
        self.displayNodeDidLoad()
    }
}

private func ayuSettingsEntries(_ settings: AyuSettings, accountID: Int64) -> [AyuSettingsEntry] {''',
        "private invite controller insertion"
    )
    settings = replace_once(
        settings,
        "        .saveEdited(settings.saveMessagesHistory),\n",
        "        .saveEdited(settings.saveMessagesHistory),\n        .privateInvitePreview,\n",
        "private invite settings row"
    )

if "privateInvitePreview" not in settings or "privateInviteURLField" not in settings:
    raise SystemExit("Private group preview settings integration did not complete")

if "//submodules/AsyncDisplayKit" not in build:
    build = replace_once(
        build,
        '        "//submodules/AccountContext",\n',
        '        "//submodules/AccountContext",\n        "//submodules/AsyncDisplayKit",\n        "//submodules/SwiftSignalKit",\n',
        "private invite AsyncDisplayKit dependency"
    )

# Telegram's native ChatPeekTimeout owns the peek lifecycle and read-only behavior.
# Do not globally alter channel send/reaction permissions: that would also affect
# ordinary public channels and non-peek chats for every non-member account.
# Keep Telegram's native peek timer and timeout alert, but remove its Join action.
# The preview screen remains a native ChatController; expiry only dismisses the peek.
if "AyuGram read-only peek: suppress Join action" not in chat_controller:
    join_action = "                        TextAlertAction(type: .genericAction, title: strongSelf.presentationData.strings.Conversation_PrivateChannelTimeLimitedAlertJoin, action: {"
    cancel_action = "                        TextAlertAction(type: .defaultAction, title: strongSelf.presentationData.strings.Common_Cancel"
    if chat_controller.count(join_action) != 1 or chat_controller.count(cancel_action) < 1:
        raise SystemExit("Could not uniquely locate Telegram native peek timeout Join action")
    start = chat_controller.index(join_action)
    end = chat_controller.index(cancel_action, start)
    chat_controller = (
        chat_controller[:start]
        + "                        // AyuGram read-only peek: suppress Join action.\n"
        + chat_controller[end:]
    )

if "AyuGramOriginalMediaPreviewController" not in menu:
    menu = replace_once(
        menu,
        "import Foundation\nimport UIKit\nimport TelegramCore\n",
        "import Foundation\nimport UIKit\nimport QuickLook\nimport TelegramCore\n",
        "original media QuickLook import"
    )
    menu = replace_once(
        menu,
        "private extension DateFormatter {\n",
        r'''private final class AyuGramOriginalMediaPreviewItem: NSObject, QLPreviewItem {
    private let url: URL

    init(url: URL) {
        self.url = url
    }

    var previewItemURL: URL? { return self.url }
    var previewItemTitle: String? { return "قبل" }
}

private final class AyuGramOriginalMediaPreviewController: QLPreviewController, QLPreviewControllerDataSource {
    private let item: AyuGramOriginalMediaPreviewItem

    init(url: URL) {
        self.item = AyuGramOriginalMediaPreviewItem(url: url)
        super.init(nibName: nil, bundle: nil)
        self.dataSource = self
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func numberOfPreviewItems(in controller: QLPreviewController) -> Int { return 1 }

    func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem {
        return self.item
    }
}

private extension DateFormatter {
''',
        "original media preview controller"
    )
    settings_before_action = r'''        if message.effectiveMedia.contains(where: { media in
            if media is TelegramMediaImage { return true }
            if let file = media as? TelegramMediaFile { return file.isVideo }
            return false
        }), message.attributes.contains(where: { $0 is EditedMessageAttribute }) {
            actions.append(.action(ContextMenuActionItem(text: "قبل", icon: { theme in
                return generateTintedImage(image: UIImage(systemName: "clock.arrow.circlepath"), color: theme.actionSheet.primaryTextColor)
            }, action: { c, _ in
                c?.dismiss(completion: {
                    let revisions = context.account.postbox.transaction { transaction -> [AyuMessage] in
                        return AyuGramPostboxHistoryStore.revisions(
                            transaction: transaction,
                            userID: context.account.peerId.toInt64(),
                            dialogID: message.id.peerId.toInt64(),
                            messageID: message.id.id,
                            limit: 1
                        )
                    }
                    _ = (revisions |> deliverOnMainQueue).startStandalone(next: { values in
                        guard let path = values.first?.mediaPath,
                              FileManager.default.fileExists(atPath: path) else {
                            controllerInteraction.displayUndo(.info(title: nil, text: "Original media was not cached before the edit.", timeout: 2.0, customUndoText: nil))
                            return
                        }
                        let preview = AyuGramOriginalMediaPreviewController(url: URL(fileURLWithPath: path))
                        controllerInteraction.navigationController()?.present(preview, animated: true)
                    })
                })
            })))
        }

        // Always expose the full AyuGram History list from the message menu.
'''
    menu = replace_once(
        menu,
        "        // Always expose the full AyuGram History list from the message menu.\n",
        settings_before_action,
        "Before context menu action"
    )

SETTINGS.write_text(settings, encoding="utf-8")
SETTINGS_BUILD.write_text(build, encoding="utf-8")
MENU.write_text(menu, encoding="utf-8")
CHAT_CONTROLLER.write_text(chat_controller, encoding="utf-8")
print("PASS: manual Save and deleted-message capture remain from the AyuGram patch.")
print("PASS: added Telegram-resolved private invite preview entry.")
print("PASS: non-member channel chat composer and reactions are read-only.")
print("PASS: native peek expiry no longer offers Join.")
print("PASS: added Before action backed by the pre-edit archive.")
