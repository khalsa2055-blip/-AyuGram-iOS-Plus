# Private Invite Link Inspector — isolated prototype

## Purpose

Prototype a Swiftgram-compatible screen for inspecting a Telegram private invite link without changing the main app or its existing features.

## Important Telegram access boundary

A private invite link is not a read-only credential for the group's message history. Telegram may return limited invite-preview metadata, but it does not grant message access to a non-member. The prototype must not attempt to bypass membership, privacy settings, or Telegram authorization.

## Proposed user flow

1. User pastes or shares a `t.me/+` invite link into **Invite Link Inspector**.
2. The app validates the URL format locally and removes tracking/query noise where safe.
3. Using the signed-in Telegram account and Telegram's supported MTProto invite-check flow, it requests only the preview Telegram makes available.
4. It displays available fields such as title, avatar, chat type, member/subscriber count, and invite status.
5. If the account already has access, offer **Open chat**.
6. If the account does not have access, explain that messages require joining and offer Telegram's normal join/request flow. Never imply that a preview is the message history.

## Architecture sketch

- `InviteLinkParser`: validates supported Telegram invite URL forms; never logs or uploads the invite token.
- `InvitePreviewService`: wraps the supported Telegram invite-check request using the existing authenticated account session.
- `InvitePreviewModel`: represents available metadata and explicit states: loading, preview available, expired/invalid, approval required, already a member, and access required.
- `InvitePreviewViewController` / SwiftUI view: native-looking preview UI with clear status and actions.
- Keep this prototype isolated from message storage, background monitoring, and the main app's existing features.

## Privacy and secret handling

The invite URL is a bearer-style secret. Do not commit real invite links, tokens, account credentials, API hashes, or session data to this repository, source files, CI logs, screenshots, or issue reports. Use redacted or synthetic links in tests. The real test invite supplied in the conversation stays in that conversation only.

## Test plan

- Valid invite with preview metadata: show only fields returned by Telegram.
- Expired/revoked invite: show a clear invalid/expired state.
- Join-request invite: show approval-required state; do not claim access.
- Existing member: allow opening the chat through the authenticated account.
- Non-member: verify that message history is not displayed and joining is required.
- Malformed URL and unrelated URL: reject safely.
- Verify that invite tokens are not written to logs or analytics.

## Acceptance criteria

- No changes to the main branch.
- No unauthorized message access or membership bypass.
- No real invite token stored in Git.
- UI states are tested before this prototype is considered complete.
- A successful compile is not treated as proof that Telegram returns preview metadata for every invite type.

## Current status

Planning/specification only. No Swift implementation or simulator test has been completed yet.
