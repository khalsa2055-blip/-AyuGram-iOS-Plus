#if canImport(UIKit)
import UIKit

/// Small native input screen for a private invite URL.
/// The host app supplies `onPreview` and routes the accepted URL through
/// Telegram's existing `context.engine.peers.joinLinkInformation` flow.
@MainActor
public final class PrivateInviteEntryViewController: UIViewController {
    public var onPreview: ((String) -> Void)?

    private let field = UITextField()
    private let previewButton = UIButton(type: .system)
    private let errorLabel = UILabel()

    public override func viewDidLoad() {
        super.viewDidLoad()
        title = "Private Group Preview"
        view.backgroundColor = .systemBackground

        field.placeholder = "https://t.me/+…"
        field.borderStyle = .roundedRect
        field.keyboardType = .URL
        field.autocapitalizationType = .none
        field.autocorrectionType = .no
        field.clearButtonMode = .whileEditing
        field.accessibilityIdentifier = "privateInviteURLField"

        previewButton.setTitle("Preview", for: .normal)
        previewButton.titleLabel?.font = .preferredFont(forTextStyle: .headline)
        previewButton.addTarget(self, action: #selector(previewPressed), for: .touchUpInside)
        previewButton.accessibilityIdentifier = "privateInvitePreviewButton"

        errorLabel.font = .preferredFont(forTextStyle: .footnote)
        errorLabel.textColor = .systemRed
        errorLabel.numberOfLines = 0
        errorLabel.isHidden = true

        let stack = UIStackView(arrangedSubviews: [field, previewButton, errorLabel])
        stack.axis = .vertical
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)

        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -20),
            stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 24),
            field.heightAnchor.constraint(equalToConstant: 48),
            previewButton.heightAnchor.constraint(equalToConstant: 48)
        ])
    }

    @objc private func previewPressed() {
        let raw = field.text ?? ""
        guard case .inviteHash = PrivateInviteLinkInspector.inspect(raw) else {
            errorLabel.text = "Enter a valid Telegram private invite link."
            errorLabel.isHidden = false
            return
        }
        errorLabel.isHidden = true
        view.endEditing(true)
        onPreview?(raw.trimmingCharacters(in: .whitespacesAndNewlines))
    }
}
#endif
