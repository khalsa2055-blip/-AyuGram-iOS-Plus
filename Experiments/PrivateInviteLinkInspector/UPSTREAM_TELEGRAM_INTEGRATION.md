# Telegram iOS integration findings

Verified against TelegramMessenger/Telegram-iOS at commit
`279f89e4d4f63f17227bf877dc3d8990f22ecd58`.

## Native invite and peek flow

1. `submodules/TelegramCore/Sources/TelegramEngine/Peers/JoinLink.swift`
   implements `_internal_joinLinkInformation(_:account:)` using
   `messages.checkChatInvite(hash:)`.
2. `chatInvite` becomes `.invite` (metadata only), `chatInviteAlready`
   becomes `.alreadyJoined`, and `chatInvitePeek` becomes
   `.peek(EnginePeer, expires)`.
3. `submodules/TelegramUI/Sources/OpenResolvedUrl.swift` handles
   `.peek` by opening the peer with
   `ChatPeekTimeout(deadline: deadline, linkData: link)`.
4. `submodules/JoinLinkPreviewUI/Sources/JoinLinkPreviewController.swift`
   uses the same native navigation contract for the `.peek` result.
5. `submodules/AccountContext/Sources/AccountContext.swift` defines
   `ChatPeekTimeout.deadline` as `Int32`; the server deadline must be
   forwarded unchanged.

## App integration in this branch

`Scripts/apply_four_feature_ui.py` adds the settings entry and input screen.
The Preview action:
- parses the private invite URL locally into its hash;
- calls `context.engine.peers.joinLinkInformation(hash)`;
- handles `.peek` only by calling
  `navigateToChatController(NavigateToChatControllerParams(...))` with
  `ChatPeekTimeout(deadline: deadline, linkData: hash)`;
- rejects `.invite`, `.alreadyJoined`, and `.invalidHash` without
  displaying the server's participant metadata or a Join action.

The resulting chat is Telegram's native ChatController, not a custom timeline.
Telegram's own chat/history/media implementation remains responsible for
rendering messages and media and enforcing the peek timeout. The AyuGram patch
removes only the Join action from the native peek-expiry alert, leaving a
dismiss-only expiry path so the temporary preview cannot become a join flow.

## Safety constraints

- Do not implement a second MTProto invite checker; use
  `joinLinkInformation(hash)`.
- Do not treat `.invite` metadata as read permission.
- Do not call `messages.importChatInvite`, `joinChatInteractively`,
  `channels.joinChannel`, or message/media send APIs.
- Do not issue a standalone `messages.getHistory` request from this feature.
  Use Telegram's native `ChatPeekTimeout` navigation route.
- Never fabricate a peek result or bypass Telegram's server authorization.
- Never log or persist an invite hash.

## Test limitations

The isolated Swift package is a policy/parser test layer, not the runtime
message provider. The app patch is audited for the native invite resolver,
peek-only branch, native chat navigation, timeout propagation, and absence
of join/send calls. The current no-build workflow does not compile or install
the full iOS app; actual display of messages/media must ultimately be
confirmed on an iOS runtime using a link for which the server grants peek.
