# Private Invite Link Inspector

## Runtime integration

The app-facing implementation is injected by `Scripts/apply_four_feature_ui.py` into the Telegram iOS source checkout used by the four-feature workflow. The entry is exposed under **Settings → My Profile → Private Group Preview**.

The feature does not implement a parallel chat renderer or issue ad-hoc history/media requests. It delegates the message timeline and media display to Telegram's own `ChatController`:

1. The invite URL is validated locally and reduced to its invite hash. Supported forms include `https://t.me/+HASH`, legacy `https://t.me/joinchat/HASH`, the supported Telegram host aliases, and the official `tg://join?invite=HASH` deep link.
2. The app calls `context.engine.peers.joinLinkInformation(hash)`, Telegram's existing wrapper around `messages.checkChatInvite`.
3. Only `.peek(peer, deadline)` opens a chat. The route uses `navigateToChatController` and the exact server deadline in `ChatPeekTimeout(deadline:linkData:)`.
4. Telegram's native chat/history/media UI handles the read-only peek session and its expiry.
5. An ordinary `.invite` result displays metadata only. It also exposes a separate **Open invitation in Telegram** action. This action is user-triggered and routes the original invite through Telegram's normal invite resolver; the app does not join or request access automatically. Telegram may still require the user to join or obtain admin approval before messages can be viewed.
6. Already-member results open the existing chat normally. Invalid links and transport errors are shown as errors.
7. The native ChatController's peek-expiry alert is changed to a dismiss-only path; it cannot convert the preview into a join action.

A successful no-join message preview still depends on Telegram returning `chatInvitePeek`. An ordinary `chatInvite` result is not read permission.

## Read-only and privacy boundaries

- No `messages.importChatInvite`, `joinChatInteractively`, `channels.joinChannel`, send-message, or send-media operation is used by the preview feature.
- The second path opens Telegram's standard invite interface only after the user taps its button. It does not accept an invite, join a group, or create a join request on the user's behalf.
- Telegram's native chat send-permission gate rejects non-member channels, and the AyuGram peek-specific wrappers keep message and reaction sending disabled during a peek.
- A successful peek uses the server deadline unchanged.
- Invite hashes are used only for the live server check and native invite/peek context; they are not logged or saved.
- If Telegram denies peek access, the fallback shows group information and the user-controlled standard invitation route. It cannot read messages that Telegram has not authorized.

## Test layers

The `PrivateInviteLinkInspector` Swift package tests official URL forms, server-result gating, expiry handling, bounded read requests, and mock-provider behavior. The `private-preview-repair-checks.yml` workflow audits that the app patch uses the native MTProto invite resolver, only opens the native chat for `.peek`, passes `ChatPeekTimeout`, exposes the manually tapped fallback, and contains no automatic join/send operation.

These checks validate the source-level integration contract. They do not substitute for an iOS device run against a real invite link. A real-world positive preview test requires a Telegram invite for which the server actually returns `chatInvitePeek`; a denied result remains subject to Telegram's membership rules.

## Protocol references

- https://core.telegram.org/api/invites
- https://core.telegram.org/method/messages.checkChatInvite
- https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/TelegramCore/Sources/TelegramEngine/Peers/JoinLink.swift
- https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/TelegramUI/Sources/OpenResolvedUrl.swift
- https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/JoinLinkPreviewUI/Sources/JoinLinkPreviewController.swift
