# Media Edit Archive — isolated implementation

## Intended behavior

- Detect a media payload replacement on an existing message.
- Preserve the first available photo/video bytes before Telegram applies the edit.
- Expose an edit record so the UI can show an edited marker beside the message time.
- Let the user open the archived original.
- Ignore caption-only edits.

## Integration contract

The Telegram message-update pipeline must call `captureOriginal` **before** replacing the message's current media in its local message store. It must provide the actual cached/downloaded media bytes (or a stable local file copied into archive storage). After parsing the update, call `mediaDidChange` only if the media kind or payload changed.

Do not fetch media after the edit and assume it is the original: the server may already expose only the replacement. Do not attempt to recover media that was never cached or downloaded before the edit.

## Persistence

The isolated core now stores each first-captured original as a local media file, stores its metadata separately, and persists edit-record metadata in `edit-records.json`. Recreating `MediaEditArchive` from the same directory reloads the captured snapshots and edit records. The caller must use a stable private app-container directory. This is local persistence only; it does not create a cloud/background Telegram listener.

## Current scope

This package is deliberately independent of Telegram UI and database types. It is a testable core, not yet wired into Telegram-iOS. The repository currently contains a project shell rather than the upstream Swiftgram/Telegram-iOS source, so app-level hooks and visual UI cannot be implemented or honestly claimed tested until that source is imported.

## Acceptance tests

1. Photo replaced with all-black image bytes → original bytes remain readable.
2. Video replaced with a different/black video → original bytes remain readable.
3. Same media with caption-only edit → no edit record (caller does not invoke media comparison for caption changes).
4. Different photo replaces original → first original remains the archived version.
5. Recreate the archive from the same directory → original media and edit record remain readable.
6. Missing pre-edit snapshot → report a missing-original error; never silently archive the replacement as the original.

## Privacy and storage

Archive media locally in the app's private data container. Provide a future retention/clear control before shipping. Never upload archived media to a third-party service.
