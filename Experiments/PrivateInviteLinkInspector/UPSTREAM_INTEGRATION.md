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

## Current integration blocker

The target repository's root README identifies it as a shell and says no upstream source has been imported. The current CI workflow checks out only this repository and runs the isolated Swift package tests on Ubuntu. It does not build Swiftgram, compile an iOS target, or run an iOS Simulator.

Therefore the next valid engineering step is to import/pin the licensed upstream Swiftgram source (including its required submodules and build setup) into this project, or change the project to a reproducible fork of that source. Only then can the adapter and native screen be implemented against real generated types. A guessed adapter written against imagined Telegram types would create avoidable compile failures, so it is intentionally not added.
