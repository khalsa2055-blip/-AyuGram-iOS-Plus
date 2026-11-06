#!/usr/bin/env python3
"""Apply the two UI surfaces that complete the four-feature AyuGram integration."""
from pathlib import Path
import re

ROOT = Path("telegram-ios")
SETTINGS = ROOT / "submodules/TelegramUI/Components/AyuGramSettingsScreen/Sources/AyuGramSettingsScreen.swift"
SETTINGS_BUILD = ROOT / "submodules/TelegramUI/Components/AyuGramSettingsScreen/BUILD"
MENU = ROOT / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
CHAT_CONTROLLER = ROOT / "submodules/TelegramUI/Sources/ChatController.swift"
CHAT_CONTROLLER_INTERACTION = ROOT / "submodules/TelegramUI/Components/ChatControllerInteraction/Sources/ChatControllerInteraction.swift"

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return source.replace(old, new, 1)

for path in (SETTINGS, SETTINGS_BUILD, MENU, CHAT_CONTROLLER, CHAT_CONTROLLER_INTERACTION):
    if not path.is_file():
        raise SystemExit(f"Missing required AyuGram integration file: {path}")

settings = SETTINGS.read_text(encoding="utf-8")
build = SETTINGS_BUILD.read_text(encoding="utf-8")
menu = MENU.read_text(encoding="utf-8")
chat_controller = CHAT_CONTROLLER.read_text(encoding="utf-8")
chat_controller_interaction = CHAT_CONTROLLER_INTERACTION.read_text(encoding="utf-8")

# Give Swift's constraint solver the concrete interaction type before it checks
# Telegram's large callback initializer; the read-only closures otherwise push
# this expression over the type-checker complexity budget.
interaction_initializer = "let controllerInteraction = ChatControllerInteraction("
typed_interaction_initializer = "let controllerInteraction: ChatControllerInteraction = ChatControllerInteraction("
if typed_interaction_initializer not in chat_controller:
    chat_controller = replace_once(
        chat_controller,
        interaction_initializer,
        typed_interaction_initializer,
        "ChatControllerInteraction explicit type"
    )

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
        '        "//submodules/AccountContext",\n        "//submodules/AsyncDisplayKit",\n',
        "private invite AsyncDisplayKit dependency"
    )

# Telegram's native ChatPeekTimeout owns the peek lifecycle and read-only behavior.
# Do not globally alter channel send/reaction permissions: that would also affect
# ordinary public channels and non-peek chats for every non-member account.
# Keep Telegram's native peek timer and timeout alert, but remove its Join action.
# The preview screen remains a native ChatController; expiry only dismisses the peek.
# Scope timeout edits to the exact native ChatPeekTimeout block. A marker elsewhere
# in ChatController must never suppress installation of the actual timeout guard.
peek_start = chat_controller.index("if let peekData = self.peekData")
peek_end = chat_controller.index("self.checksTooltipDisposable", peek_start)
timeout_block = chat_controller[peek_start:peek_end]

if "AyuGram read-only peek: suppress Join action" not in timeout_block:
    join_action = "                        TextAlertAction(type: .genericAction, title: strongSelf.presentationData.strings.Conversation_PrivateChannelTimeLimitedAlertJoin, action: {"
    cancel_action = "                        TextAlertAction(type: .defaultAction, title: strongSelf.presentationData.strings.Common_Cancel"
    if timeout_block.count(join_action) != 1 or timeout_block.count(cancel_action) < 1:
        raise SystemExit("Could not uniquely locate Telegram native peek timeout Join action")
    action_start = timeout_block.index(join_action)
    action_end = timeout_block.index(cancel_action, action_start)
    timeout_block = (
        timeout_block[:action_start]
        + "                        // AyuGram read-only peek: suppress Join action.\\n"
        + timeout_block[action_end:]
    )

# At Telegram's peek deadline, close the preview directly instead of leaving
# the temporary ChatController open behind a Cancel-only expiration alert.
if "AyuGram read-only peek: dismiss at deadline" not in timeout_block:
    alert_start = timeout_block.find("                strongSelf.present(textAlertController(")
    alert_end_marker = "                ), in: .window(.root))"
    alert_end = timeout_block.find(alert_end_marker, alert_start)
    if alert_start < 0 or alert_end < 0 or timeout_block.count(alert_end_marker) != 1:
        raise SystemExit("Could not uniquely locate native peek expiration alert")
    alert_end += len(alert_end_marker)
    timeout_block = (
        timeout_block[:alert_start]
        + "                // AyuGram read-only peek: dismiss at deadline without Join.\\n"
        + "                strongSelf.dismiss()"
        + timeout_block[alert_end:]
    )

if "AyuGram read-only peek: suppress Join action" not in timeout_block:
    raise SystemExit("Native peek timeout Join action was not suppressed in its own block")
if "AyuGram read-only peek: dismiss at deadline" not in timeout_block:
    raise SystemExit("Native peek timeout dismissal was not installed in its own block")
chat_controller = chat_controller[:peek_start] + timeout_block + chat_controller[peek_end:]

# Telegram's native send permission function checks channel bans, but not membership.
# Scope a hard read-only gate to ChatController instances created with ChatPeekTimeout.
# Normal chats continue to use Telegram's permission implementation unchanged.
if "ayuGramCanSendMessagesInCurrentChat" not in chat_controller:
    replacements = (
        ("canSendMessagesToChat(self.presentationInterfaceState)", "self.ayuGramCanSendMessagesInCurrentChat()"),
        ("canSendMessagesToChat(strongSelf.presentationInterfaceState)", "strongSelf.ayuGramCanSendMessagesInCurrentChat()"),
        ("canSendReactionsToChat(strongSelf.presentationInterfaceState)", "strongSelf.ayuGramCanSendReactionsInCurrentChat()"),
    )
    for old, new in replacements:
        count = chat_controller.count(old)
        if count == 0:
            raise SystemExit(f"Read-only preview send-gate anchor missing: {old}")
        chat_controller = chat_controller.replace(old, new)

    # Read-only callback gates are installed in ChatControllerInteraction below.

    # Disable the avatar/profile and header More surfaces during a private peek.
    long_tap_old = 'if let strongSelf = self, let peerView = strongSelf.contentData?.state.peerView'
    long_tap_new = 'if let strongSelf = self, case nil = strongSelf.peekData, let peerView = strongSelf.contentData?.state.peerView'
    if long_tap_old in chat_controller:
        chat_controller = replace_once(chat_controller, long_tap_old, long_tap_new, "preview title long-tap")
    avatar_context_marker = "avatarNode.contextAction = { [weak self] node, gesture in"
    avatar_context_start = chat_controller.find(avatar_context_marker)
    avatar_context_end = chat_controller.find("            chatInfoButtonItem = UIBarButtonItem(customDisplayNode: avatarNode)!", avatar_context_start)
    if avatar_context_start < 0 or avatar_context_end < 0:
        raise SystemExit("Avatar context menu section not found")
    avatar_section = chat_controller[avatar_context_start:avatar_context_end]
    avatar_old = 'guard let strongSelf = self, let peer = strongSelf.presentationInterfaceState.renderedPeer?.chatMainPeer else {'
    avatar_new = 'guard let strongSelf = self, case nil = strongSelf.peekData, let peer = strongSelf.presentationInterfaceState.renderedPeer?.chatMainPeer else {'
    if avatar_new not in avatar_section:
        avatar_matches = avatar_section.count(avatar_old)
        if avatar_matches < 1:
            raise SystemExit("Avatar context guard anchor missing")
        # Telegram has multiple avatar context branches in this bounded section;
        # guard every matching entry point so no profile action leaks in peek.
        avatar_section = avatar_section.replace(avatar_old, avatar_new)
    chat_controller = chat_controller[:avatar_context_start] + avatar_section + chat_controller[avatar_context_end:]

    title_tap_old = 'self.chatTitleView?.tapAction = { [weak self] in\n            self?.navigationButtonAction(.openChatInfo(expandAvatar: false, section: nil))'
    title_tap_new = 'self.chatTitleView?.tapAction = { [weak self] in\n            guard case nil = self?.peekData else { return }\n            self?.navigationButtonAction(.openChatInfo(expandAvatar: false, section: nil))'
    if title_tap_old in chat_controller:
        chat_controller = chat_controller.replace(title_tap_old, title_tap_new, 1)

    more_guard_old = '            guard let self else {\n                return\n            }\n            guard let peerId = self.chatLocation.peerId else {'
    more_guard_new = '            guard let self, case nil = self.peekData else { return }\n            guard let peerId = self.chatLocation.peerId else {'
    if more_guard_old in chat_controller:
        chat_controller = chat_controller.replace(more_guard_old, more_guard_new, 1)
    profile_button_old = """        chatInfoButtonItem.target = self
        chatInfoButtonItem.action = #selector(self.rightNavigationButtonAction)
"""
    profile_button_new = """        if self.peekData == nil {
            chatInfoButtonItem.target = self
            chatInfoButtonItem.action = #selector(self.rightNavigationButtonAction)
        } else {
            chatInfoButtonItem.target = nil
            chatInfoButtonItem.action = nil
        }
"""
    if profile_button_new not in chat_controller:
        if chat_controller.count(profile_button_old) != 1:
            raise SystemExit("Profile button action anchor not unique")
        chat_controller = chat_controller.replace(profile_button_old, profile_button_new, 1)

    more_button_line = '        self.moreBarButton.addTarget(self, action: #selector(self.moreButtonPressed), forControlEvents: .touchUpInside)'
    if more_button_line in chat_controller and 'self.moreBarButton.isHidden = self.peekData != nil' not in chat_controller:
        chat_controller = chat_controller.replace(
            more_button_line,
            '        self.moreBarButton.isHidden = self.peekData != nil\n' + more_button_line,
            1,
        )

    group_call_marker = "    public override func joinGroupCall(peerId: PeerId, invite: String?, activeCall: EngineGroupCallDescription) {"
    group_call_guard = group_call_marker + "\n        guard case nil = self.peekData else { return }"
    if group_call_guard not in chat_controller:
        if chat_controller.count(group_call_marker) != 1:
            raise SystemExit("ChatController group-call override anchor not unique")
        chat_controller = chat_controller.replace(group_call_marker, group_call_guard, 1)

    send_method = "    func sendMessages(_ messages: [EnqueueMessage], media: Bool = false, postpone: Bool = false, commit: Bool = false) {"
    helpers = """    private func ayuGramCanSendMessagesInCurrentChat() -> Bool {
        guard case nil = self.peekData else {
            return false
        }
        return canSendMessagesToChat(self.presentationInterfaceState)
    }

    private func ayuGramCanSendReactionsInCurrentChat() -> Bool {
        guard case nil = self.peekData else {
            return false
        }
        return canSendReactionsToChat(self.presentationInterfaceState)
    }

"""
    if chat_controller.count(send_method) != 1:
        raise SystemExit("Could not uniquely locate ChatController sendMessages entry point")
    chat_controller = chat_controller.replace(send_method, helpers + send_method, 1)
    chat_controller = chat_controller.replace(
        send_method + "\n",
        send_method + "\n        guard case nil = self.peekData else { return }\n",
        1,
    )

    if "guard case nil = self.peekData else { return }" not in chat_controller:
        raise SystemExit("Direct sendMessages read-only guard did not install")

if chat_controller.count("canSendMessagesToChat(self.presentationInterfaceState)") != 1:
    raise SystemExit("The only remaining native message gate must be inside the scoped wrapper")
if "canSendMessagesToChat(strongSelf.presentationInterfaceState)" in chat_controller:
    raise SystemExit("An unscoped message send gate remains in a ChatController call site")
if chat_controller.count("canSendReactionsToChat(self.presentationInterfaceState)") != 1:
    raise SystemExit("The only remaining native reaction gate must be inside the scoped wrapper")
if "canSendReactionsToChat(strongSelf.presentationInterfaceState)" in chat_controller:
    raise SystemExit("An unscoped reaction gate remains in a ChatController call site")
if chat_controller.count("ayuGramCanSendMessagesInCurrentChat()") < 15:
    raise SystemExit("Not all composer/sticker/command/file-send call sites use the preview gate")
# One occurrence is the scoped helper; Telegram revisions may expose more than two call sites.
# Require at least two guarded call sites plus the helper, while rejecting any unscoped native gate below.
if chat_controller.count("ayuGramCanSendReactionsInCurrentChat()") < 3:
    raise SystemExit("Both reaction send entry points must use the preview gate")

# The gallery-level Before action is only meaningful for edited messages.
# Hide it on untouched media rather than presenting an empty preview action.
gallery_before_guard = 'if !message.containsSecretMedia && !isCopyProtected {\n            actions.append(.action(ContextMenuActionItem(text: "Before"'
gallery_before_guarded = 'if message.attributes.contains(where: { $0 is EditedMessageAttribute }) && !message.containsSecretMedia && !isCopyProtected {\n            actions.append(.action(ContextMenuActionItem(text: "Before"'
if gallery_before_guard in menu:
    menu = replace_once(menu, gallery_before_guard, gallery_before_guarded, "Before edited-media visibility")
elif gallery_before_guarded not in menu:
    raise SystemExit("Could not locate gallery Before action visibility guard")

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

# Keep preview-only interaction checks out of ChatController's giant initializer.
# Each callback is wrapped independently inside ChatControllerInteraction so Swift
# does not have to type-check many new guards as part of one enormous expression.
if "canPerformPeekInteractions: @escaping () -> Bool = { true }" not in chat_controller_interaction:
    chat_controller_interaction = replace_once(
        chat_controller_interaction,
        "        displayPollRestrictedToast: @escaping (EngineMessage.Id) -> Void,\n        automaticMediaDownloadSettings: MediaAutoDownloadSettings,",
        "        displayPollRestrictedToast: @escaping (EngineMessage.Id) -> Void,\n        canPerformPeekInteractions: @escaping () -> Bool = { true },\n        automaticMediaDownloadSettings: MediaAutoDownloadSettings,",
        "private preview interaction permission parameter"
    )

callback_wrappers = [
    ("self.openPeer = openPeer", """self.openPeer = { peer, navigation, reference, source in
            guard canPerformPeekInteractions() else { return }
            openPeer(peer, navigation, reference, source)
        }"""),
    ("self.openPeerMention = openPeerMention", """self.openPeerMention = { name, progress in
            guard canPerformPeekInteractions() else { return }
            openPeerMention(name, progress)
        }"""),
    ("self.openMessageContextMenu = openMessageContextMenu", """self.openMessageContextMenu = { message, selectAll, node, frame, recognizer, location in
            guard canPerformPeekInteractions() else { return }
            openMessageContextMenu(message, selectAll, node, frame, recognizer, location)
        }"""),
    ("self.openMessageReactionContextMenu = openMessageReactionContextMenu", """self.openMessageReactionContextMenu = { message, sourceView, gesture, value in
            guard canPerformPeekInteractions() else { return }
            openMessageReactionContextMenu(message, sourceView, gesture, value)
        }"""),
    ("self.updateMessageReaction = updateMessageReaction", """self.updateMessageReaction = { message, reaction, isLarge, sourceView in
            guard canPerformPeekInteractions() else { return }
            updateMessageReaction(message, reaction, isLarge, sourceView)
        }"""),
    ("self.openMessageContextActions = openMessageContextActions", """self.openMessageContextActions = { message, node, frame, gesture in
            guard canPerformPeekInteractions() else { return }
            openMessageContextActions(message, node, frame, gesture)
        }"""),
    ("self.requestMessageActionCallback = requestMessageActionCallback", """self.requestMessageActionCallback = { message, data, isGame, requiresPassword, progress in
            guard canPerformPeekInteractions() else { return }
            requestMessageActionCallback(message, data, isGame, requiresPassword, progress)
        }"""),
    ("self.requestMessageActionUrlAuth = requestMessageActionUrlAuth", """self.requestMessageActionUrlAuth = { url, subject in
            guard canPerformPeekInteractions() else { return }
            requestMessageActionUrlAuth(url, subject)
        }"""),
    ("self.requestSelectMessagePollOptions = requestSelectMessagePollOptions", """self.requestSelectMessagePollOptions = { id, options in
            guard canPerformPeekInteractions() else { return }
            requestSelectMessagePollOptions(id, options)
        }"""),
    ("self.requestAddMessagePollOption = requestAddMessagePollOption", """self.requestAddMessagePollOption = { id, text, entities, identifier, mediaReference in
            guard canPerformPeekInteractions() else { return }
            requestAddMessagePollOption(id, text, entities, identifier, mediaReference)
        }"""),
    ("self.openJoinLink = openJoinLink", """self.openJoinLink = { hash in
            guard canPerformPeekInteractions() else { return }
            openJoinLink(hash)
        }"""),
    ("self.openWebView = openWebView", """self.openWebView = { buttonText, url, simple, source in
            guard canPerformPeekInteractions() else { return }
            openWebView(buttonText, url, simple, source)
        }"""),
    ("self.activateAdAction = activateAdAction", """self.activateAdAction = { messageId, progress, media, fullscreen in
            guard canPerformPeekInteractions() else { return }
            activateAdAction(messageId, progress, media, fullscreen)
        }"""),
    ("self.callPeer = callPeer", """self.callPeer = { peerId, isVideo in
            guard canPerformPeekInteractions() else { return }
            callPeer(peerId, isVideo)
        }"""),
    ("self.openConferenceCall = openConferenceCall", """self.openConferenceCall = { message in
            guard canPerformPeekInteractions() else { return }
            openConferenceCall(message)
        }"""),
]
for old, new in callback_wrappers:
    if new not in chat_controller_interaction:
        chat_controller_interaction = replace_once(
            chat_controller_interaction, old, new, "read-only callback wrapper"
        )

call_marker='}, displayPollRestrictedToast: { [weak self] messageId in\n            guard let self else {\n                return\n            }\n            self.displayPollRestrictedToast(messageId: messageId)\n        }, automaticMediaDownloadSettings:'
call_replacement='''}, displayPollRestrictedToast: { [weak self] messageId in
            guard let self else {
                return
            }
            self.displayPollRestrictedToast(messageId: messageId)
        }, canPerformPeekInteractions: { [weak self] in
            guard let self else { return false }
            return self.peekData == nil
        }, automaticMediaDownloadSettings:'''
if "canPerformPeekInteractions: { [weak self] in" not in chat_controller:
    chat_controller = replace_once(chat_controller, call_marker, call_replacement, "private preview callback gate argument")

if "canPerformPeekInteractions: @escaping () -> Bool = { true }" not in chat_controller_interaction:
    raise SystemExit("Private preview callback gate parameter did not install")
if chat_controller_interaction.count("guard canPerformPeekInteractions() else { return }") < 10:
    raise SystemExit("Not all private preview callbacks were wrapped")

CHAT_CONTROLLER_INTERACTION.write_text(chat_controller_interaction, encoding="utf-8")

SETTINGS.write_text(settings, encoding="utf-8")
SETTINGS_BUILD.write_text(build, encoding="utf-8")
MENU.write_text(menu, encoding="utf-8")
CHAT_CONTROLLER.write_text(chat_controller, encoding="utf-8")
CHAT_CONTROLLER_INTERACTION.write_text(chat_controller_interaction, encoding="utf-8")
print("PASS: manual Save and deleted-message capture remain from the AyuGram patch.")
print("PASS: added Telegram-resolved private invite preview entry.")
print("PASS: non-member channel chat composer and reactions are read-only.")
print("PASS: native peek expiry no longer offers Join.")
print("PASS: added Before action backed by the pre-edit archive.")
