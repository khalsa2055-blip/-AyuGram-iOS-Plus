# Private Invite Link Inspector

## Runtime integration

The app-facing implementation is injected by `Scripts/apply_four_feature_ui.py` into the Telegram iOS source checkout used by the four-feature workflow. The entry is exposed under **Settings → My Profile → Private Group Preview**.

The feature does not implement a parallel chat renderer or issue ad-hoc history/media requests. It delegates the message timeline and media display to Telegram's own `ChatController`:

1. The invite URL is validated locally and reduced to its invite hash. Supported forms include `https://t.me/+HASH`, legacy `https://t.me/joinchat/HASH`, the supported Telegram host aliases, and the official `tg://join?invite=HASH` deep link.
2. The app calls `context.engine.peers.joinLinkInformation(hash)`, Telegram's existing wrapper around `messages.checkChatInvite`.
3. Only `.peek(peer, deadline)` opens a chat. The route uses `navigateToChatController` and the exact server deadline in `ChatPeekTimeout(deadline:linkData:)`.
4. Telegram's native chat/history/media UI handles the read-only peek session and its expiry.
5. An ordinary `.invite` result displays metadata only. No invitation button, join action, or join-request action is exposed. If Telegram does not grant `chatInvitePeek`, the app does not attempt another route to message access.
6. Already-member results open the existing chat normally. Invalid links and transport errors are shown as errors.
7. The native ChatController's peek-expiry alert is changed to a dismiss-only path; it cannot convert the preview into a join action.

A successful no-join message preview still depends on Telegram returning `chatInvitePeek`. An ordinary `chatInvite` result is not read permission.

## Read-only and privacy boundaries

- No `messages.importChatInvite`, `joinChatInteractively`, `channels.joinChannel`, send-message, or send-media operation is used by the preview feature.
- When Telegram denies peek access, the app remains on a metadata-only screen. It does not expose a standard invitation interface, create a join request, or join the group.
- Telegram's native chat send-permission gate rejects non-member channels, and the AyuGram peek-specific wrappers keep message and reaction sending disabled during a peek.
- A successful peek uses the server deadline unchanged.
- Invite hashes are used only for the live server check and native invite/peek context; they are not logged or saved.
- If Telegram denies peek access, only limited invite metadata is shown. The app cannot read messages that Telegram has not authorized.

## Test layers

The `PrivateInviteLinkInspector` Swift package tests official URL forms, server-result gating, expiry handling, bounded read requests, and mock-provider behavior. The `private-preview-repair-checks.yml` workflow audits that the app patch uses the native MTProto invite resolver, only opens the native chat for `.peek`, passes `ChatPeekTimeout`, contains no invitation, join, join-request, or send action.

These checks validate the source-level integration contract. They do not substitute for an iOS device run against a real invite link. A real-world positive preview test requires a Telegram invite for which the server actually returns `chatInvitePeek`; a denied result remains subject to Telegram's membership rules.

## Protocol references

- https://core.telegram.org/api/invites
- https://core.telegram.org/method/messages.checkChatInvite
- https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/TelegramCore/Sources/TelegramEngine/Peers/JoinLink.swift
- https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/TelegramUI/Sources/OpenResolvedUrl.swift
- https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/JoinLinkPreviewUI/Sources/JoinLinkPreviewController.swift
