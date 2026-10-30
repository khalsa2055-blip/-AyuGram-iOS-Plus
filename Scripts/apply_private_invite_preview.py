#!/usr/bin/env python3
"""Fail-closed source audit for Telegram's native invite-preview flow.

This does not bypass Telegram authorization or patch upstream sources. It verifies
that the simulator build uses the upstream implementation that distinguishes a
server-granted peek from metadata-only/denied invite states.
"""
from pathlib import Path
import argparse
import sys

def require(path: Path, needles: tuple[str, ...], label: str) -> str:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing upstream source: {path}")
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"FAIL: {label} is missing required source anchors: {missing}")
    return text

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()

    core = args.upstream / "submodules/TelegramCore/Sources/TelegramEngine/Peers/JoinLink.swift"
    ui = args.upstream / "submodules/JoinLinkPreviewUI/Sources/JoinLinkPreviewController.swift"
    route = args.upstream / "submodules/TelegramUI/Sources/OpenResolvedUrl.swift"

    core_text = require(core, (
        "messages.checkChatInvite(hash:",
        "case let .chatInvite(chatInviteData):",
        "case let .chatInvitePeek(chatInvitePeekData):",
        "return .peek(EnginePeer(peer), expires)",
    ), "server invite result mapping")

    ui_text = require(ui, (
        "case let .invite(invite):",
        "case let .peek(peer, deadline):",
        "ChatPeekTimeout(deadline: deadline, linkData:",
    ), "native preview UI")

    require(route, (
        "case let .peek(peer, deadline):",
        "peekData: ChatPeekTimeout(deadline: deadline, linkData:",
        "JoinLinkPreviewController(context: context, link: link",
    ), "deep-link navigation")

    package_source = args.package / "Sources/PrivateInviteLinkInspector/PeekAccess.swift"
    package_text = require(package_source, (
        "case peek(PeekChat)",
        "case basicInfo(title: String, participantCount: Int?)",
        "case accessDenied",
        "guard case let .peek(chat) = result",
    ), "isolated access-state model")

    # In the native upstream controller, join is a separate user action.
    # Reject any accidental attempt to move it into the peek result branch.
    peek_branch = ui_text.split("case let .peek(peer, deadline):", 1)[1].split("case .invalidHash:", 1)[0]
    forbidden = ("joinChatInteractively", "importChatInvite", "messages.getHistory")
    found = [token for token in forbidden if token in peek_branch]
    if found:
        raise SystemExit(f"FAIL: forbidden operation in native peek branch: {found}")

    print("PASS: Telegram returns the authorization decision; the app distinguishes:")
    print("  ALLOWED: chatInvitePeek -> ChatPeekTimeout -> native read-only chat route")
    print("  NOT GRANTED: chatInvite metadata only; no message-preview permission")
    print("  DENIED/INVALID: RPC failure or invalid invite; do not fabricate access")
    print("PASS: no automatic import/join or standalone history request in peek branch")
    return 0

if __name__ == "__main__":
    sys.exit(main())
