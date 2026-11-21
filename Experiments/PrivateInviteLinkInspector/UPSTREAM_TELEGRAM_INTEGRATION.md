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
- displays limited metadata for `.invite` without exposing an invitation,
  join, or join-request action;
- opens the existing chat for `.alreadyJoined` without creating a new join;
- displays an error for `.invalidHash`.

The resulting chat is Telegram's native ChatController, not a custom timeline.
Telegram's own chat/history/media implementation remains responsible for
rendering messages and media and enforcing the peek timeout. The AyuGram patch
removes only the Join action from the native peek-expiry alert, leaving a
dismiss-only expiry path so the temporary preview cannot become a join flow.

## MTProto transport proxy compatibility (Flowseal TG WS Proxy)

Reviewed `Flowseal/tg-ws-proxy` and its iOS-compatible connection contract.
The desktop project runs a local MTProto proxy (default listener
`127.0.0.1:1443`) and relays the encrypted MTProto stream to Telegram DCs
over WebSocket/TLS, with fallback transport. It is a transport bridge, not an
invite-access or membership bypass.

The pinned Telegram-iOS source already supports this without a custom proxy
implementation in the preview feature:

- `submodules/TelegramCore/Sources/Settings/ProxySettings.swift` maps an
  `.mtp(secret:)` proxy entry to `MTSocksProxySettings(ip:port:secret:)`.
- `submodules/TelegramCore/Sources/Network/Network.swift` applies the
  account's `proxySettings?.effectiveActiveServer` to the API environment
  using `withUpdatedSocksProxySettings(...)`.
- The preview call uses `context.engine.peers`, so it uses the signed-in
  account's configured Telegram network/proxy path. No separate downloader,
  second account, or custom invite RPC should be introduced.

Therefore, when a reachable Flowseal MTProto proxy is enabled in the iOS
client's native **Settings > Data and Storage > Proxy** screen, the invite
verification request can travel through it automatically. This can help only
when the failure is in network reachability or traffic filtering. Telegram
still evaluates the invite and account permissions: `.invite` and
`CHANNEL_PRIVATE` remain denied for message history when the server does not
grant a peek or the account is not authorized.

For a Windows-hosted local proxy to be reachable from an iPhone, its listener
cannot remain on `127.0.0.1` (that address means the iPhone itself). It must
listen on a LAN-reachable interface, and access should be restricted with the
host firewall to the trusted local network/device. Do not expose port 1443 to
the public Internet or configure router port forwarding. The phone and PC
must be able to reach each other on the same trusted network.

The original Flowseal desktop project is not copied into this app. The separate
community iOS ports have their own background-execution limitations and are
not included in this branch.

References:
- Flowseal TG WS Proxy: https://github.com/Flowseal/tg-ws-proxy
- Flowseal architecture: https://github.com/Flowseal/tg-ws-proxy/blob/main/docs/EN/README.md
- Telegram iOS proxy mapping:
  https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/TelegramCore/Sources/Settings/ProxySettings.swift
- Telegram iOS active network proxy:
  https://github.com/TelegramMessenger/Telegram-iOS/blob/279f89e4d4f63f17227bf877dc3d8990f22ecd58/submodules/TelegramCore/Sources/Network/Network.swift
- Telegram proxy setup: https://core.telegram.org/proxy

## Safety constraints

- Do not implement a second MTProto invite checker; use
  `joinLinkInformation(hash)`.
- Do not treat `.invite` metadata as read permission.
- Do not call `messages.importChatInvite`, `joinChatInteractively`,
  `channels.joinChannel`, or message/media send APIs.
- Do not expose any secondary invitation route when `.peek` is denied;
  remain metadata-only and do not request approval.
- Do not issue a standalone `messages.getHistory` request from this feature.
  Use Telegram's native `ChatPeekTimeout` navigation route.
- Never fabricate a peek result or bypass Telegram's server authorization.
- Never log or persist invite hashes, session credentials, or private invite URLs.

## Test limitations

The isolated Swift package is a policy/parser test layer, not the runtime
message provider. The app patch is audited for the native invite resolver,
peek-only branch, native chat navigation, timeout propagation, and absence
of join/send calls. The current no-build workflow does not compile or install
the full iOS app; actual display of messages/media must ultimately be
confirmed on an iOS runtime using a link for which the server grants peek.
