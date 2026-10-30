# Private Invite Link Inspector — isolated prototype

## Goal

A read-only Telegram invite viewer. It must never send messages, import an invite, join a chat, or create a join request automatically.

## Important protocol detail: Telegram supports conditional peeking

Telegram's official invite documentation describes a `chatInvitePeek` result from `messages.checkChatInvite`. For eligible supergroups and channels, this result includes a chat and an expiry timestamp; Telegram's documentation says the client may then fetch messages with the normal history/message methods until that timestamp.

This is conditional server-granted access, not a fabricated membership state. The server may instead return ordinary `chatInvite` metadata, `chatInviteAlready`, or an error such as `CHANNEL_PRIVATE`, expired, or invalid. The app must respect the exact result and must not pretend every invite supports peeking.

Reference: https://core.telegram.org/api/invites and https://core.telegram.org/method/messages.checkChatInvite

## Read-only flow

1. Parse the invite URL locally; never print or persist the invite hash.
2. Call `messages.checkChatInvite` using the signed-in user's existing Telegram session.
3. If Telegram returns `chatInvitePeek`, create a time-limited `PeekSession` and read messages only until the server-provided expiry.
4. Display the returned messages in a Telegram-like read-only timeline, including sender, timestamp, text, and supported media.
5. If Telegram returns ordinary metadata or denies access, show only that metadata and explain that message preview was not granted.
6. If the account is already a member, open the existing chat through the normal app route.
7. Never call `messages.importChatInvite`, `channels.joinChannel`, or any send method from this feature.

## Implemented isolated core

- `InviteLinkParser`: parses supported `t.me/+` and `joinchat` invite forms locally.
- `InviteCheckResult`: normalized outcomes for peek, basic metadata, already-member, approval-required, expired, invalid, and denied.
- `PeekSession`: only starts from a server-granted `.peek` result, validates bounded fetch limits, and checks expiry immediately before every message-provider request.
- `PeekMessageProvider`: read-only integration boundary for the future MTProto adapter.
- `PreviewMessage` / `MediaKind`: normalized message and media model for the viewer.
- Swift Package tests cover parsing, non-peek rejection, expiry enforcement, successful read-only retrieval, blocked expired retrieval, and invalid fetch limits.

## Still required before app integration

This repository is currently a project shell; the Swiftgram application source is checked out by CI rather than present in this branch. The isolated package is not yet wired to Swiftgram's generated MTProto types or UI. Next work is to import/use the exact upstream Telegram API types, map the `chatInvitePeek` constructor, implement the read-only message provider, and then add the native viewer screen.

## Privacy and secret handling

Invite links are bearer-style secrets. Never commit real invite links, hashes, account credentials, API hashes, or session data. Use synthetic fixtures only. Do not log invite hashes.

## Acceptance criteria

- No changes to `main`.
- No automatic joining, join requests, message sending, or membership spoofing.
- Peeking works only when Telegram explicitly returns `chatInvitePeek`.
- Reads stop at the server-provided expiry.
- Messages and media are shown only when returned by Telegram for that peek session.
- Unit tests and an iOS simulator build pass before claiming app integration is complete.

## Current status

The isolated Swift core now includes a guarded read-only fetch entry point and nine unit tests. Every retrieval through `PeekSession.fetchMessages` checks the server expiry immediately before calling the provider and rejects limits outside 1...100. The provider is a test seam only: it is not yet connected to Telegram MTProto. No real `messages.checkChatInvite` adapter, real history/media provider, Swiftgram UI integration, or iOS simulator test has been completed. The feature is therefore **not yet usable in the app**. Do not treat passing core tests as proof that Telegram preview works.
