# Incoming media edit integration research

## Verified upstream call chain

The Swiftgram fork is based on Telegram-iOS. The incoming update path is:

1. `submodules/TelegramCore/Sources/State/UpdateMessageService.swift`
   - Receives boxed `Api.Updates` in `networkSessionDidReceive(message:)`.
   - Normalizes the update variants and calls `groupUpdates(...)`.
   - Emits `[UpdateGroup]` through its pipe.
2. `submodules/TelegramCore/Sources/State/AccountStateManager.swift`
   - Receives update groups and processes `.processUpdateGroups(groups)`.
   - Calls `initialStateWithUpdateGroups(...)`, then `finalStateWithUpdateGroups(...)`.
   - Stores `finalState.state.preCachedResources` in `postbox.mediaBox`.
   - Opens a Postbox transaction and calls `replayFinalState(... transaction: ... finalState: ...)`.

This confirms that `ChatUpdatingMessageMedia.swift` is not the incoming edit hook: it models local/pending edit UI state. The network update path is handled by UpdateMessageService and AccountStateManager.

## Safe integration point

The only viable interception point identified so far is immediately before `replayFinalState(...)` inside the Postbox transaction in AccountStateManager's `.processUpdateGroups` case. At that point the old message is still in Postbox, and the transaction is about to apply the final state.

The integration must:
- Identify only messages whose media payload changes (not caption-only edits).
- Read the *old* media resource from the existing message and its already available MediaBox resource data.
- Persist those bytes to the private archive before replayFinalState replaces the message.
- Never download the post-edit server media and mislabel it as the original.
- Key records by full MessageId (peer + namespace + id), not bare numeric message id.
- Skip archiving when the original resource is not already locally available; report that limitation rather than blocking Telegram's update pipeline.
- Keep archive I/O bounded and avoid doing large file copies synchronously on the database queue.

## Why this is not wired in this repository yet

This repository's feature branch currently contains only the standalone Swift package and CI shell. It does not contain the Swiftgram/Telegram-iOS source tree, nor does it define Telegram's Message, MediaBox, AccountFinalState, or Postbox transaction types. A real integration patch must be applied to the upstream source checkout (or to a checked-in fork of it), then compiled against Telegram's Bazel targets.

The current isolated package tests prove only local archive persistence and comparison logic. They do not prove that incoming Telegram edits are intercepted, that original resource bytes are available, or that the iOS UI can display an "Original" action.

## Upstream files inspected

- `submodules/TelegramCore/Sources/State/UpdateMessageService.swift`
- `submodules/TelegramCore/Sources/State/AccountStateManager.swift`
- `submodules/TelegramCore/Sources/Utils/UpdateMessageMedia.swift`
- `submodules/TelegramCore/Sources/PendingMessages/ChatUpdatingMessageMedia.swift`

Upstream source: https://github.com/Swiftgram/Telegram-iOS
