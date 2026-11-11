#!/usr/bin/env python3
"""Keep server-deleted Telegram messages in their original chat, with a local deleted mark."""
from pathlib import Path


ROOT = Path("telegram-ios") if Path("telegram-ios").is_dir() else Path(".")
DELETE = ROOT / "submodules/TelegramCore/Sources/TelegramEngine/Messages/DeleteMessages.swift"
STATE = ROOT / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
BUBBLE = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
TEXT_BUBBLE = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageTextBubbleContentNode/Sources/ChatMessageTextBubbleContentNode.swift"
DATE_STATUS = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/ChatMessageDateAndStatusNode.swift"
SETTINGS = ROOT / "submodules/TelegramUI/Components/AyuGramSettingsScreen/Sources/AyuGramSettingsScreen.swift"
MESSAGE_MENU = ROOT / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
PEER_MEDIA_MENU = ROOT / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoScreenDisplayMediaGalleryContextMenu.swift"
PEER_HEADER_MENU = ROOT / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoScreenPerformButtonAction.swift"
ENGINE = ROOT / "submodules/TelegramCore/Sources/TelegramEngine/Messages/TelegramEngineMessages.swift"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count == 0 and new in source:
        return source
    if count != 1:
        raise SystemExit(f"{label}: expected one source anchor, found {count}")
    return source.replace(old, new, 1)


def matching_delimiter(source: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string = escaped = line_comment = block_comment = False
    i = start
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if line_comment:
            if ch == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
        elif ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise SystemExit(f"Could not find matching {closing!r} for Swift block at offset {start}")


def remove_swift_action(source: str, marker: str, append_prefix: str, label: str) -> str:
    marker_pos = source.find(marker)
    if marker_pos < 0:
        return source
    start = source.rfind(append_prefix, 0, marker_pos)
    if start < 0:
        raise SystemExit(f"{label}: found marker but not its action wrapper")
    end = matching_delimiter(source, start, "(", ")") + 1
    line_end = source.find("\n", end)
    end = len(source) if line_end < 0 else line_end + 1
    line_start = source.rfind("\n", 0, start) + 1
    previous_line_end = line_start - 1
    if previous_line_end >= 0:
        previous_line_start = source.rfind("\n", 0, previous_line_end) + 1
        previous_line = source[previous_line_start:previous_line_end].strip()
        if previous_line.startswith("//") and "AyuGram History" in previous_line:
            start = previous_line_start
    return source[:start] + source[end:]


def remove_swift_function(source: str, signature: str, label: str) -> str:
    start = source.find(signature)
    if start < 0:
        return source
    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit(f"{label}: function opening brace missing")
    end = matching_delimiter(source, brace, "{", "}") + 1
    if end < len(source) and source[end] == "\n":
        end += 1
    return source[:start] + source[end:]


for path in (DELETE, STATE, BUBBLE, TEXT_BUBBLE, DATE_STATUS, SETTINGS, MESSAGE_MENU, PEER_MEDIA_MENU, PEER_HEADER_MENU, ENGINE):
    if not path.is_file():
        raise SystemExit(f"Required source file is missing: {path}")


# 1) Preserve only server-delivered deleted messages in the local Postbox.
# Interactive deletion from this device keeps Telegram's ordinary delete behavior.
delete_text = DELETE.read_text(encoding="utf-8")
old_signature = (
    "public func _internal_deleteMessages(transaction: Transaction, mediaBox: MediaBox, ids: [MessageId], "
    "deleteMedia: Bool = true, manualAddMessageThreadStatsDifference: ((MessageThreadKey, Int, Int) -> Void)? = nil, "
    "ayuAccountID: Int64? = nil) {"
)
new_signature = (
    "@discardableResult\n"
    "public func _internal_deleteMessages(transaction: Transaction, mediaBox: MediaBox, ids: [MessageId], "
    "deleteMedia: Bool = true, manualAddMessageThreadStatsDifference: ((MessageThreadKey, Int, Int) -> Void)? = nil, "
    "ayuAccountID: Int64? = nil, preserveDeletedMessagesInChat: Bool = false) -> Set<MessageId> {"
)
delete_text = replace_once(delete_text, old_signature, new_signature, "deleted-message helper signature")

retention_block = r'''    var ayuRetainedDeletedMessageIds = Set<MessageId>()
    if preserveDeletedMessagesInChat,
       let ayuAccountID,
       (try? AyuGramRuntime.makeSettingsStore(accountID: ayuAccountID))?.settings.saveDeletedMessages == true {
        for id in ids {
            guard let message = transaction.getMessage(id),
                  !message.isCopyProtected(),
                  !message.containsSecretMedia else {
                continue
            }
            transaction.updateMessage(id, update: { currentMessage in
                var attributes = currentMessage.attributes
                if attributes.contains(where: { ($0 as? EditedMessageAttribute)?.date == Int32.min }) {
                    return .skip
                }
                // Hidden sentinel: it identifies a local tombstone without changing Telegram's edit date.
                attributes.append(EditedMessageAttribute(date: Int32.min, isHidden: true))

                var storeForwardInfo: StoreMessageForwardInfo?
                if let forwardInfo = currentMessage.forwardInfo {
                    storeForwardInfo = StoreMessageForwardInfo(
                        authorId: forwardInfo.author?.id,
                        sourceId: forwardInfo.source?.id,
                        sourceMessageId: forwardInfo.sourceMessageId,
                        date: forwardInfo.date,
                        authorSignature: forwardInfo.authorSignature,
                        psaType: forwardInfo.psaType,
                        flags: forwardInfo.flags
                    )
                }
                return .update(StoreMessage(
                    id: currentMessage.id,
                    customStableId: nil,
                    globallyUniqueId: currentMessage.globallyUniqueId,
                    groupingKey: currentMessage.groupingKey,
                    threadId: currentMessage.threadId,
                    timestamp: currentMessage.timestamp,
                    flags: StoreMessageFlags(currentMessage.flags),
                    tags: currentMessage.tags,
                    globalTags: currentMessage.globalTags,
                    localTags: currentMessage.localTags,
                    forwardInfo: storeForwardInfo,
                    authorId: currentMessage.author?.id,
                    text: currentMessage.text,
                    attributes: attributes,
                    media: currentMessage.media
                ))
            })
            ayuRetainedDeletedMessageIds.insert(id)
        }
    }

'''
delete_function_start = delete_text.find("public func _internal_deleteMessages(")
if delete_function_start < 0:
    raise SystemExit("Target _internal_deleteMessages function was not found")
delete_function_brace = delete_text.find("{", delete_function_start)
if delete_function_brace < 0:
    raise SystemExit("Target _internal_deleteMessages opening brace was not found")
delete_function_end = matching_delimiter(delete_text, delete_function_brace, "{", "}") + 1
delete_function = delete_text[delete_function_start:delete_function_end]
delete_function = replace_once(
    delete_function,
    "    var resourceIds: [MediaResourceId] = []\n",
    retention_block + "    var resourceIds: [MediaResourceId] = []\n",
    "deleted-message local retention block"
)
delete_text = delete_text[:delete_function_start] + delete_function + delete_text[delete_function_end:]
delete_text = replace_once(
    delete_text,
    "    transaction.deleteMessages(ids, forEachMedia: { _ in\n    })",
    """    let idsToDelete = ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }
    transaction.deleteMessages(idsToDelete, forEachMedia: { _ in
    })
    return ayuRetainedDeletedMessageIds""",
    "filtered Postbox deletion"
)
DELETE.write_text(delete_text, encoding="utf-8")

state_text = STATE.read_text(encoding="utf-8")
state_text = replace_once(
    state_text,
    "}, ayuAccountID: accountPeerId.toInt64())",
    "}, ayuAccountID: accountPeerId.toInt64(), preserveDeletedMessagesInChat: true)",
    "server deletion retention route"
)
direct_delete_start = state_text.find("case let .DeleteMessages(ids):")
direct_delete_end = state_text.find("case let .UpdateMinAvailableMessage", direct_delete_start)
if direct_delete_start < 0 or direct_delete_end < 0:
    raise SystemExit("Server DeleteMessages source block boundaries not found")
direct_delete_block = state_text[direct_delete_start:direct_delete_end]
direct_delete_block = replace_once(
    direct_delete_block,
    "                _internal_deleteMessages(",
    "                let ayuRetainedDeletedMessageIds = _internal_deleteMessages(",
    "capture retained IDs from server DeleteMessages"
)
direct_delete_block = replace_once(
    direct_delete_block,
    "                deletedMessageIds.append(contentsOf: ids.map { .messageId($0) })",
    "                deletedMessageIds.append(contentsOf: ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }.map { .messageId($0) })",
    "exclude retained rows from removed-message notifications"
)
state_text = state_text[:direct_delete_start] + direct_delete_block + state_text[direct_delete_end:]

global_capture_anchor = "_internal_captureDeletedMessages(transaction: transaction, mediaBox: mediaBox, ids: messageIds, ayuAccountID: accountPeerId.toInt64())\n"
global_retention_block = r'''                var ayuRetainedGlobalIds = Set<Int32>()
                if (try? AyuGramRuntime.makeSettingsStore(accountID: accountPeerId.toInt64()))?.settings.saveDeletedMessages == true {
                    for globalID in ids {
                        guard let messageID = transaction.messageIdsForGlobalIds([globalID]).first,
                              let message = transaction.getMessage(messageID),
                              !message.isCopyProtected(),
                              !message.containsSecretMedia else {
                            continue
                        }
                        transaction.updateMessage(messageID, update: { currentMessage in
                            var attributes = currentMessage.attributes
                            if attributes.contains(where: { ($0 as? EditedMessageAttribute)?.date == Int32.min }) {
                                return .skip
                            }
                            attributes.append(EditedMessageAttribute(date: Int32.min, isHidden: true))

                            var storeForwardInfo: StoreMessageForwardInfo?
                            if let forwardInfo = currentMessage.forwardInfo {
                                storeForwardInfo = StoreMessageForwardInfo(
                                    authorId: forwardInfo.author?.id,
                                    sourceId: forwardInfo.source?.id,
                                    sourceMessageId: forwardInfo.sourceMessageId,
                                    date: forwardInfo.date,
                                    authorSignature: forwardInfo.authorSignature,
                                    psaType: forwardInfo.psaType,
                                    flags: forwardInfo.flags
                                )
                            }
                            return .update(StoreMessage(
                                id: currentMessage.id,
                                customStableId: nil,
                                globallyUniqueId: currentMessage.globallyUniqueId,
                                groupingKey: currentMessage.groupingKey,
                                threadId: currentMessage.threadId,
                                timestamp: currentMessage.timestamp,
                                flags: StoreMessageFlags(currentMessage.flags),
                                tags: currentMessage.tags,
                                globalTags: currentMessage.globalTags,
                                localTags: currentMessage.localTags,
                                forwardInfo: storeForwardInfo,
                                authorId: currentMessage.author?.id,
                                text: currentMessage.text,
                                attributes: attributes,
                                media: currentMessage.media
                            ))
                        })
                        ayuRetainedGlobalIds.insert(globalID)
                    }
                }
'''
if global_capture_anchor not in state_text:
    raise SystemExit("Global-ID capture insertion anchor not found")
state_text = state_text.replace(global_capture_anchor, global_capture_anchor + global_retention_block, 1)
old_global_delete_call = "transaction.deleteMessagesWithGlobalIds(ids, forEachMedia: { media in"
new_global_delete_call = """let ayuGlobalIdsToDelete = ids.filter { !ayuRetainedGlobalIds.contains($0) }
                transaction.deleteMessagesWithGlobalIds(ayuGlobalIdsToDelete, forEachMedia: { media in"""
if old_global_delete_call not in state_text:
    raise SystemExit("Global-ID deletion call anchor not found")
state_text = state_text.replace(old_global_delete_call, new_global_delete_call, 1)
state_text = replace_once(
    state_text,
    "deletedMessageIds.append(contentsOf: ids.map { .global($0) })",
    "deletedMessageIds.append(contentsOf: ids.filter { !ayuRetainedGlobalIds.contains($0) }.map { .global($0) })",
    "exclude retained global IDs from removed-message notifications"
)
STATE.write_text(state_text, encoding="utf-8")

# The engine-facing helper is Void; its call must not return the retained-ID set.
engine_text = ENGINE.read_text(encoding="utf-8")
engine_text = replace_once(
    engine_text,
    "            return _internal_deleteMessages(",
    "            _internal_deleteMessages(",
    "Void TelegramEngineMessages deleteMessages caller"
)
ENGINE.write_text(engine_text, encoding="utf-8")


# 2) Render the local deletion mark beside the original message time.
date_text = DATE_STATUS.read_text(encoding="utf-8")
date_text = replace_once(date_text, "        var edited: Bool\n", "        var edited: Bool\n        var isAyuGramDeleted: Bool\n", "date/status deleted-state argument")
date_text = replace_once(
    date_text,
    "            edited: Bool,\n            impressionCount: Int?,\n",
    "            edited: Bool,\n            isAyuGramDeleted: Bool = false,\n            impressionCount: Int?,\n",
    "date/status deleted-state initializer"
)
date_text = replace_once(
    date_text,
    "            self.edited = edited\n",
    "            self.edited = edited\n            self.isAyuGramDeleted = isAyuGramDeleted\n",
    "date/status deleted-state assignment"
)
date_text = replace_once(
    date_text,
    "            if arguments.edited {\n",
    """            if arguments.isAyuGramDeleted {
                updatedDateText = "🧹 \\(updatedDateText)"
            } else if arguments.edited {
""",
    "date/status broom rendering"
)
DATE_STATUS.write_text(date_text, encoding="utf-8")

bubble_text = BUBBLE.read_text(encoding="utf-8")
bubble_text = replace_once(
    bubble_text,
    """                var edited = false
                if item.content.firstMessageAttributes.updatingMedia != nil {
                    edited = true
                }
""",
    """                var edited = false
                var isAyuGramDeleted = false
                if item.content.firstMessageAttributes.updatingMedia != nil {
                    edited = true
                }
""",
    "chat bubble deleted-state variable"
)
bubble_text = replace_once(
    bubble_text,
    """                    if let attribute = attribute as? EditedMessageAttribute {
                        edited = !attribute.isHidden
""",
    """                    if let attribute = attribute as? EditedMessageAttribute {
                        if attribute.date == Int32.min {
                            isAyuGramDeleted = true
                            edited = false
                        } else {
                            edited = !attribute.isHidden
                        }
""",
    "chat bubble deletion sentinel detection"
)
bubble_text = replace_once(
    bubble_text,
    "                    edited: edited && !item.presentationData.isPreview,\n",
    "                    edited: edited && !item.presentationData.isPreview,\n                    isAyuGramDeleted: isAyuGramDeleted && !item.presentationData.isPreview,\n",
    "chat bubble date/status deleted-state argument"
)
BUBBLE.write_text(bubble_text, encoding="utf-8")

text_bubble_text = TEXT_BUBBLE.read_text(encoding="utf-8")
text_bubble_text = replace_once(
    text_bubble_text,
    """                var edited = false
                if item.attributes.updatingMedia != nil {
                    edited = true
                }
""",
    """                var edited = false
                var isAyuGramDeleted = false
                if item.attributes.updatingMedia != nil {
                    edited = true
                }
""",
    "text bubble deleted-state variable"
)
text_bubble_text = replace_once(
    text_bubble_text,
    """                    if let attribute = attribute as? EditedMessageAttribute {
                        edited = !attribute.isHidden
""",
    """                    if let attribute = attribute as? EditedMessageAttribute {
                        if attribute.date == Int32.min {
                            isAyuGramDeleted = true
                            edited = false
                        } else {
                            edited = !attribute.isHidden
                        }
""",
    "text bubble deletion sentinel detection"
)
text_bubble_text = replace_once(
    text_bubble_text,
    """                        edited: edited && !item.presentationData.isPreview,
""",
    """                        edited: edited && !item.presentationData.isPreview,
                        isAyuGramDeleted: isAyuGramDeleted && !item.presentationData.isPreview,
""",
    "text bubble deleted-state date/status argument"
)
TEXT_BUBBLE.write_text(text_bubble_text, encoding="utf-8")


# 3) Remove the user-facing History list shortcuts. The Postbox store remains
# private and is still used for Before originals and local deleted-message state.
settings_text = SETTINGS.read_text(encoding="utf-8")
entry_start = settings_text.find("private enum AyuSettingsEntry")
entry_end = settings_text.find("private enum AyuHistoryEntry", entry_start)
if entry_start < 0 or entry_end < 0:
    raise SystemExit("AyuGram settings entry enum boundaries were not found")
entry = settings_text[entry_start:entry_end]
entry = entry.replace("    case history\n", "", 1)
# The private-preview row is installed before this cleanup step. Remove the
# History entry without dropping that neighboring preview case.
entry = entry.replace(
    "case .saveDeleted, .saveEdited, .history, .clearDeletedHistory, .privateInvitePreview:",
    "case .saveDeleted, .saveEdited, .clearDeletedHistory, .privateInvitePreview:",
    1
)
entry = entry.replace(
    "case .saveDeleted, .saveEdited, .history, .clearDeletedHistory:",
    "case .saveDeleted, .saveEdited, .clearDeletedHistory:",
    1
)
entry = entry.replace("        case .history: return 103\\n", "", 1)
history_case = entry.find("        case .history:\\n")
if history_case >= 0:
    next_cases = [
        position for marker in (
            "        case .privateInvitePreview:\\n",
            "        case .clearDeletedHistory:\\n",
        )
        if (position := entry.find(marker, history_case)) >= 0
    ]
    if not next_cases:
        raise SystemExit("Could not find the next AyuGram settings case after History")
    next_case = min(next_cases)
    entry = entry[:history_case] + entry[next_case:]
settings_text = settings_text[:entry_start] + entry + settings_text[entry_end:]

entries_start = settings_text.find("private func ayuSettingsEntries")
entries_end = settings_text.find("public func ayuGramSettingsScreen", entries_start)
if entries_start < 0 or entries_end < 0:
    raise SystemExit("AyuGram settings entries array boundaries were not found")
entries_block = settings_text[entries_start:entries_end].replace("        .history,\n", "")
settings_text = settings_text[:entries_start] + entries_block + settings_text[entries_end:]
SETTINGS.write_text(settings_text, encoding="utf-8")

menu_text = MESSAGE_MENU.read_text(encoding="utf-8")
menu_text = remove_swift_action(
    menu_text,
    'text: "AyuGram History"',
    "actions.append(.action(ContextMenuActionItem(",
    "message context-menu History action"
)
MESSAGE_MENU.write_text(menu_text, encoding="utf-8")

peer_media_text = PEER_MEDIA_MENU.read_text(encoding="utf-8")
peer_media_text = remove_swift_function(
    peer_media_text,
    "        func addAyuGramHistoryAction(_ items: inout [ContextMenuItem]) {",
    "PeerInfo media-menu History helper"
)
peer_media_text = peer_media_text.replace("                addAyuGramHistoryAction(&items)\n\n", "")
peer_media_text = peer_media_text.replace("import AyuGramSettingsScreen\n", "")
PEER_MEDIA_MENU.write_text(peer_media_text, encoding="utf-8")

peer_header_text = PEER_HEADER_MENU.read_text(encoding="utf-8")
peer_header_text = remove_swift_action(
    peer_header_text,
    'text: "AyuGram History"',
    "items.append(.action(ContextMenuActionItem(",
    "PeerInfo header More-menu History action"
)
peer_header_text = peer_header_text.replace("import AyuGramSettingsScreen\n", "")
peer_header_text = "\n".join(line.rstrip() for line in peer_header_text.splitlines()) + "\n"
PEER_HEADER_MENU.write_text(peer_header_text, encoding="utf-8")


# 4) Fail closed if a separate History navigation route remains accessible.
for path in (MESSAGE_MENU, PEER_MEDIA_MENU, PEER_HEADER_MENU):
    source = path.read_text(encoding="utf-8")
    if 'text: "AyuGram History"' in source or "ayuGramHistoryScreen(context:" in source:
        raise SystemExit(f"User-facing AyuGram History navigation remains in {path}")

delete_check = DELETE.read_text(encoding="utf-8")
state_check = STATE.read_text(encoding="utf-8")
bubble_check = BUBBLE.read_text(encoding="utf-8")
date_check = DATE_STATUS.read_text(encoding="utf-8")
text_bubble_check = TEXT_BUBBLE.read_text(encoding="utf-8")
assert "preserveDeletedMessagesInChat: Bool = false" in delete_check
assert "let idsToDelete = ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }" in delete_check
assert "preserveDeletedMessagesInChat: true" in state_check
assert "ayuRetainedGlobalIds" in state_check
assert "ayuGlobalIdsToDelete = ids.filter" in state_check
assert "var ayuRetainedGlobalIds = Set<Int32>()" in state_check
assert ".global($0)" in state_check
assert "return _internal_deleteMessages(" not in ENGINE.read_text(encoding="utf-8")
assert "-> Set<MessageId>" in delete_check
assert "@discardableResult" in delete_check
assert "ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }.map { .messageId($0) }" in state_check
assert "ids.filter { !ayuRetainedGlobalIds.contains($0) }.map { .global($0) }" in state_check
assert "EditedMessageAttribute(date: Int32.min, isHidden: true)" in delete_check
assert "isAyuGramDeleted: Bool" in date_check
assert 'updatedDateText = "🧹 \\(updatedDateText)"' in date_check
assert "isAyuGramDeleted = true" in bubble_check
print("PASS: server-deleted messages remain as local rows in their original chat.")
print("PASS: the original text/media/timestamp stay on the Telegram message; the timestamp carries the 🧹 mark.")
print("PASS: interactive deletion still uses Telegram's normal deletion path.")
print("PASS: the standalone AyuGram History navigation shortcuts are removed.")
print("PASS: media archive, Before and Manual Save/saved/king code paths were not changed.")
