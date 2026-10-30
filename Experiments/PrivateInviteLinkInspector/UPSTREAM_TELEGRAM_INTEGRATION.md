# Telegram iOS integration findings

Verified against TelegramMessenger/Telegram-iOS at commit
`fb0e62ba8a147f0821da6aa63c09da7d79a10111`.

## Verified upstream flow

1. `submodules/TelegramCore/Sources/TelegramEngine/Peers/JoinLink.swift`
   implements `_internal_joinLinkInformation(_:account:)` using
   `account.network.request(Api.functions.messages.checkChatInvite(hash:))`.
2. Its `Api.ChatInvite` switch handles:
   - `chatInvite` as invite metadata (not permission to read messages);
   - `chatInviteAlready` as an already-joined peer;
   - `chatInvitePeek` as `.peek(EnginePeer, expires)`, where `expires` is
     the server-provided `Int32` deadline.
3. `submodules/JoinLinkPreviewUI/Sources/JoinLinkPreviewController.swift`
   routes the `.peek` result to the chat with
   `ChatPeekTimeout(deadline: deadline, linkData: link)`.
4. `submodules/AccountContext/Sources/AccountContext.swift` defines
   `ChatPeekTimeout.deadline` as `Int32`.
5. `submodules/TelegramApi/swift_scheme.tl` declares
   `messages.checkChatInvite` and `chatInvitePeek`.

## Integration constraints

- Use the app's existing `context.engine.peers.joinLinkInformation(hash)`
  entry point where available; do not create a second, competing invite-check
  implementation.
- Preserve the server deadline exactly when passing the peek into chat
  navigation. Convert Unix seconds to `Date` only at the package boundary.
- A `.chatInvite` response is only invite metadata. Do not promote it to a
  readable peek session.
- Do not call `messages.importChatInvite` for preview. The upstream
  `joinChatInteractively` function does call it and is an explicit join path.
- Do not assume that a standalone `messages.getHistory` request is valid for
  a peek. Follow Telegram iOS's existing `ChatPeekTimeout` chat-navigation
  path so the app's own chat/history logic enforces the temporary access.
- Never fabricate a peek result or bypass Telegram's server authorization.

## Current repository limitation

The `experiment/private-invite-preview` branch in this repository currently
contains the isolated Swift package and its workflow, not the Telegram iOS app
source tree or its Xcode/Bazel project. Therefore a real `AccountContext`
adapter and chat-navigation wiring cannot be compiled in this repository
branch yet. The package tests passing proves only the parser/access-policy
layer; it does not prove end-to-end Telegram preview or message loading.
