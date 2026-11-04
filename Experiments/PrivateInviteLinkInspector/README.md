# Private Invite Link Inspector

## Runtime integration

The app-facing implementation is injected by `Scripts/apply_four_feature_ui.py` into the Telegram iOS source checkout used by the four-feature workflow. The entry is exposed in **AyuGram → Message History → Preview Private Group**.

The feature does not implement a parallel chat renderer or issue ad-hoc history/media requests. It delegates both message timeline and media display to Telegram's own `ChatController`:

1. The pasted invite URL is validated locally and reduced to its invite hash. The hash is not logged or persisted.
2. The app calls `context.engine.peers.joinLinkInformation(hash)`, Telegram's existing wrapper around `messages.checkChatInvite`.
3. Only `.peek(peer, deadline)` opens a chat. The route uses `navigateToChatController` and the exact server deadline in `ChatPeekTimeout(deadline:linkData:)`.
4. Telegram's native chat/history/media UI handles the read-only peek session and its expiry.
5. Ordinary `.invite` metadata, already-member results, invalid links, and errors do not open a chat. The feature does not show invite participant lists or offer a Join button.

This means a successful preview depends on Telegram returning `chatInvitePeek`. An ordinary `chatInvite` result is not read permission and is deliberately rejected by this feature.

## Read-only and privacy boundaries

- No `messages.importChatInvite`, `joinChatInteractively`, `channels.joinChannel`, send-message, or send-media operation is used by this feature.
- A preview does not add the account to the group or create a join request.
- Invite hashes are used only for the live server check and native peek context; they are not logged or saved.
- The server deadline is passed unchanged to Telegram's native chat controller.
- No invite metadata or participant identities are rendered by the feature's fallback path.

## Test layers

The `PrivateInviteLinkInspector` Swift package tests URL parsing, server-result gating, expiry handling, bounded read requests, and mock-provider behavior. The `private-preview-repair-checks.yml` workflow additionally audits that the app patch uses the native MTProto invite resolver, only opens the native chat for `.peek`, passes `ChatPeekTimeout`, and contains no join/send operation.

These checks validate the source-level integration contract. They do not substitute for an iOS device run against a real invite link. A real-world positive preview test requires a Telegram invite for which Telegram actually returns `chatInvitePeek`; a denied result is expected for links where the server grants metadata only.

## Protocol references

- https://core.telegram.org/api/invites
- https://core.telegram.org/method/messages.checkChatInvite
- https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/TelegramCore/Sources/TelegramEngine/Peers/JoinLink.swift
- https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/TelegramUI/Sources/OpenResolvedUrl.swift
- https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/JoinLinkPreviewUI/Sources/JoinLinkPreviewController.swift
