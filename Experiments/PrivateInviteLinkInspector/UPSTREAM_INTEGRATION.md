# Swiftgram MTProto integration map

This note records the verified upstream API surface before an app adapter is written. It is not an implementation claim.

## Verified upstream source

The upstream source is `Swiftgram/Telegram-iOS`. Its Telegram API schema is maintained under `submodules/TelegramApi` and includes these exact TL declarations:

```tl
chatInvitePeek#61695cb0 chat:Chat expires:int = ChatInvite;
messages.checkChatInvite#3eadb1bb hash:string = ChatInvite;
messages.getHistory#4423e6c5 peer:InputPeer offset_id:int offset_date:int add_offset:int limit:int max_id:int min_id:int hash:long = messages.Messages;
channels.getMessages#ad8c9a23 channel:InputChannel id:Vector<InputMessage> = messages.Messages;
```

The generated API layer is not a standalone Swift Package API that this isolated prototype can call directly. It is part of Telegram-iOS's generated/submodule build graph.

## Required app adapter

Implement this only after the full upstream source is present in the app build:

1. Invoke `messages.checkChatInvite(hash:)` through the signed-in account's existing Telegram network.
2. Pattern-match the actual generated `Api.ChatInvite` case for `chatInvitePeek(chat:expires:)`. Convert the returned `Chat` and Unix expiry into `PeekChat`.
3. Map ordinary `chatInvite`, `chatInviteAlready`, expired/invalid errors, and `CHANNEL_PRIVATE` without converting them to a peek session.
4. Resolve the returned `Chat` into the exact `InputPeer` / `InputChannel` required by the existing TelegramCore account context.
5. Fetch history only while the server-provided expiry remains valid. Use the existing TelegramCore message conversion pipeline so users, media references, and message attributes are not lost.
6. Present a dedicated read-only controller. Do not register this peer as a joined dialog or mutate membership state.

## Hard prohibitions

- Do not call `messages.importChatInvite`, `channels.joinChannel`, or join-request methods.
- Do not fabricate a channel participant, local membership, or access hash.
- Do not retry a `CHANNEL_PRIVATE` result using another endpoint or another account.
- Do not retain or log invite hashes, session credentials, or private invite URLs.

## Current integration

The simulator workflow checks out the licensed upstream source from `Swiftgram/Telegram-iOS` and runs `Scripts/apply_private_invite_preview.py` before building. The script adds a visible `Settings > Private Group Preview` entry and a native invite-link input screen to `Swiftgram/SGSettingsUI/Sources/SGSettingsController.swift`.

When the user pastes a private invite and taps Preview, the screen forwards the URL to `context.sharedContext.applicationBindings.openUrl`. This deliberately reuses Telegram's existing URL resolver and `JoinLinkPreviewController`; it does not implement a second MTProto client, call `messages.getHistory`, or fabricate membership. Telegram's own `.peek` result opens the chat with `ChatPeekTimeout`; metadata-only, expired, or denied results remain restricted to Telegram's native behavior.

The input component in this package remains a separately testable parser/UI prototype. The actual app screen is injected into the upstream Swiftgram checkout by the simulator patch script, so compilation and simulator launch are the integration proof still required.
