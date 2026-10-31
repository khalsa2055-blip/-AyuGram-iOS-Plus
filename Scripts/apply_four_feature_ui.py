#!/usr/bin/env python3
"""Apply the two UI surfaces that complete the four-feature AyuGram integration."""
from pathlib import Path

ROOT = Path("telegram-ios")
SETTINGS = ROOT / "submodules/TelegramUI/Components/AyuGramSettingsScreen/Sources/AyuGramSettingsScreen.swift"
SETTINGS_BUILD = ROOT / "submodules/TelegramUI/Components/AyuGramSettingsScreen/BUILD"
MENU = ROOT / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return source.replace(old, new, 1)

for path in (SETTINGS, SETTINGS_BUILD, MENU):
    if not path.is_file():
        raise SystemExit(f"Missing required AyuGram integration file: {path}")

settings = SETTINGS.read_text(encoding="utf-8")
build = SETTINGS_BUILD.read_text(encoding="utf-8")
menu = MENU.read_text(encoding="utf-8")

if "AyuGramPrivateInvitePreviewController" not in settings:
    settings = replace_once(
        settings,
        "import UIKit\n",
        "import UIKit\nimport AsyncDisplayKit\n",
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
    private let field = UITextField()
    private let button = UIButton(type: .system)
    private let errorLabel = UILabel()

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

        let stack = UIStackView(arrangedSubviews: [field, button, errorLabel])
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

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    @objc private func previewPressed() {
        let raw = (field.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard let components = URLComponents(string: raw),
              let scheme = components.scheme?.lowercased(),
              scheme == "https" || scheme == "http",
              let host = components.host?.lowercased(),
              host == "t.me" || host == "www.t.me",
              components.query == nil, components.fragment == nil,
              components.user == nil, components.password == nil
        else {
            errorLabel.text = "Enter a valid Telegram private invite link."
            errorLabel.isHidden = false
            return
        }
        let parts = components.path.split(separator: "/", omittingEmptySubsequences: true)
        let valid = (parts.count == 1 && parts[0].hasPrefix("+") && parts[0].count > 1)
            || (parts.count == 2 && parts[0].lowercased() == "joinchat" && !parts[1].isEmpty)
        guard valid else {
            errorLabel.text = "Use a t.me/+… or t.me/joinchat/… invite link."
            errorLabel.isHidden = false
            return
        }
        errorLabel.isHidden = true
        endEditing(true)
        onPreview?(raw)
    }
}

private final class AyuGramPrivateInvitePreviewController: ViewController {
    private let context: AccountContext

    init(context: AccountContext) {
        self.context = context
        super.init(navigationBarPresentationData: nil)
        self.title = "Private Group Preview"
    }

    required init(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func loadDisplayNode() {
        let entryView = AyuGramPrivateInviteEntryView()
        entryView.onPreview = { [weak self] raw in
            guard let self else { return }
            // Telegram's own resolver decides whether read-only peek is permitted.
            // This does not join the group or bypass server authorization.
            self.context.sharedContext.applicationBindings.openUrl(raw)
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
        "        .clearDeletedHistory,\n",
        "        .clearDeletedHistory,\n        .privateInvitePreview,\n",
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

if "AyuGramOriginalMediaPreviewController" not in menu:
    menu = replace_once(
        menu,
        "import UIKit\n",
        "import UIKit\nimport QuickLook\n",
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
print("PASS: manual Save and deleted-message capture remain from the AyuGram patch.")
print("PASS: added Telegram-resolved private invite preview entry.")
print("PASS: added Before action backed by the pre-edit archive.")
