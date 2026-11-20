#!/usr/bin/env python3
"""Keep server-deleted Telegram messages in their original chat, with a local deleted mark."""
from pathlib import Path
import re


ROOT = Path("telegram-ios") if Path("telegram-ios").is_dir() else Path(".")
DELETE = ROOT / "submodules/TelegramCore/Sources/TelegramEngine/Messages/DeleteMessages.swift"
STATE = ROOT / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
BUBBLE = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
TEXT_BUBBLE = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageTextBubbleContentNode/Sources/ChatMessageTextBubbleContentNode.swift"
MEDIA_BUBBLE = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageMediaBubbleContentNode/Sources/ChatMessageMediaBubbleContentNode.swift"
INTERACTIVE_MEDIA = ROOT / "submodules/TelegramUI/Components/Chat/ChatMessageInteractiveMediaNode/Sources/ChatMessageInteractiveMediaNode.swift"
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


def find_case_block(source: str, case_label: str, required: str):
    pattern = re.compile(r"(?m)^(?P<indent> *)" + re.escape(case_label) + r"\n")
    for match in pattern.finditer(source):
        indent = match.group("indent")
        sibling_pattern = re.compile(r"(?m)^" + re.escape(indent) + r"case ")
        sibling = sibling_pattern.search(source, match.end())
        end = sibling.start() if sibling else len(source)
        block = source[match.start():end]
        if required in block:
            return match.start(), end, block
    return None

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


for path in (DELETE, STATE, BUBBLE, TEXT_BUBBLE, MEDIA_BUBBLE, INTERACTIVE_MEDIA, DATE_STATUS, SETTINGS, MESSAGE_MENU, PEER_MEDIA_MENU, PEER_HEADER_MENU, ENGINE):
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
       (try? AyuGramRuntime.makeSettingsStore(accountID: ayuAccountID))?.settings.saveDeletedMessages != false {
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
global_helper_signature = "public func _internal_retainDeletedMessagesWithGlobalIds("
if global_helper_signature not in state_text:
    state_import_anchor = "import AyuGramIOS\n"
    if state_import_anchor not in state_text:
        raise SystemExit("AccountStateManagementUtils AyuGramIOS import anchor not found")
    state_text = state_text.replace(state_import_anchor, state_import_anchor + "\n" + "public func _internal_retainDeletedMessagesWithGlobalIds(transaction: Transaction, ids: [Int32], accountID: Int64) -> Set<Int32> {\n    var retainedGlobalIds = Set<Int32>()\n    guard (try? AyuGramRuntime.makeSettingsStore(accountID: accountID))?.settings.saveDeletedMessages != false else {\n        return retainedGlobalIds\n    }\n\n    for globalID in ids {\n        guard let messageID = transaction.messageIdsForGlobalIds([globalID]).first,\n              let message = transaction.getMessage(messageID),\n              !message.isCopyProtected(),\n              !message.containsSecretMedia else {\n            continue\n        }\n        transaction.updateMessage(messageID, update: { currentMessage in\n            var attributes = currentMessage.attributes\n            if attributes.contains(where: { ($0 as? EditedMessageAttribute)?.date == Int32.min }) {\n                return .skip\n            }\n            attributes.append(EditedMessageAttribute(date: Int32.min, isHidden: true))\n\n            var storeForwardInfo: StoreMessageForwardInfo?\n            if let forwardInfo = currentMessage.forwardInfo {\n                storeForwardInfo = StoreMessageForwardInfo(\n                    authorId: forwardInfo.author?.id,\n                    sourceId: forwardInfo.source?.id,\n                    sourceMessageId: forwardInfo.sourceMessageId,\n                    date: forwardInfo.date,\n                    authorSignature: forwardInfo.authorSignature,\n                    psaType: forwardInfo.psaType,\n                    flags: forwardInfo.flags\n                )\n            }\n            return .update(StoreMessage(\n                id: currentMessage.id,\n                customStableId: nil,\n                globallyUniqueId: currentMessage.globallyUniqueId,\n                groupingKey: currentMessage.groupingKey,\n                threadId: currentMessage.threadId,\n                timestamp: currentMessage.timestamp,\n                flags: StoreMessageFlags(currentMessage.flags),\n                tags: currentMessage.tags,\n                globalTags: currentMessage.globalTags,\n                localTags: currentMessage.localTags,\n                forwardInfo: storeForwardInfo,\n                authorId: currentMessage.author?.id,\n                text: currentMessage.text,\n                attributes: attributes,\n                media: currentMessage.media\n            ))\n        })\n        retainedGlobalIds.insert(globalID)\n    }\n    return retainedGlobalIds\n}" + "\n", 1)
# Share the exact server-delete operations between replayFinalState and its runtime test.
server_handlers = r"""
public func _internal_applyAyuGramServerDeleteMessages(transaction: Transaction, mediaBox: MediaBox, ids: [MessageId], accountID: Int64) -> Set<MessageId> {
    return _internal_deleteMessages(
        transaction: transaction,
        mediaBox: mediaBox,
        ids: ids,
        ayuAccountID: accountID,
        preserveDeletedMessagesInChat: true
    )
}

public func _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(transaction: Transaction, mediaBox: MediaBox, ids: [Int32], accountID: Int64) -> Set<Int32> {
    let messageIds = transaction.messageIdsForGlobalIds(ids)
    _internal_captureDeletedMessages(transaction: transaction, mediaBox: mediaBox, ids: messageIds, ayuAccountID: accountID)
    return _internal_retainDeletedMessagesWithGlobalIds(transaction: transaction, ids: ids, accountID: accountID)
}
"""
if "_internal_applyAyuGramServerDeleteMessages(" not in state_text:
    helper_start = state_text.find(global_helper_signature)
    if helper_start < 0:
        raise SystemExit("Global-ID retention helper not found before shared server handlers")
    helper_brace = state_text.find("{", helper_start)
    helper_end = matching_delimiter(state_text, helper_brace, "{", "}") + 1
    state_text = state_text[:helper_end] + "\n\n" + server_handlers + state_text[helper_end:]
elif "_internal_applyAyuGramServerDeleteMessagesWithGlobalIds(" not in state_text:
    raise SystemExit("Only one shared server-delete handler exists; refusing partial update")
direct_delete_start = state_text.find("case let .DeleteMessages(ids):")
direct_delete_end = state_text.find("case let .UpdateMinAvailableMessage", direct_delete_start)
if direct_delete_start < 0 or direct_delete_end < 0:
    raise SystemExit("Server DeleteMessages source block boundaries not found")
direct_delete_block = state_text[direct_delete_start:direct_delete_end]
old_direct_delete_call = """                _internal_deleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, manualAddMessageThreadStatsDifference: { id, add, remove in
                    addMessageThreadStatsDifference(threadKey: id, remove: remove, addedMessagePeer: nil, addedMessageId: nil, isOutgoing: false)
                }, ayuAccountID: accountPeerId.toInt64())"""
new_direct_delete_call = """                let ayuRetainedDeletedMessageIds = _internal_applyAyuGramServerDeleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, accountID: accountPeerId.toInt64())"""
direct_delete_block = replace_once(
    direct_delete_block,
    old_direct_delete_call,
    new_direct_delete_call,
    "shared server DeleteMessages handler"
)
direct_delete_block = replace_once(
    direct_delete_block,
    "                deletedMessageIds.append(contentsOf: ids.map { .messageId($0) })",
    "                deletedMessageIds.append(contentsOf: ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }.map { .messageId($0) })",
    "exclude retained rows from removed-message notifications"
)
state_text = state_text[:direct_delete_start] + direct_delete_block + state_text[direct_delete_end:]

global_capture_anchor = "_internal_captureDeletedMessages(transaction: transaction, mediaBox: mediaBox, ids: messageIds, ayuAccountID: accountPeerId.toInt64())\n"
global_handler_call = "                let ayuRetainedGlobalIds = _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(transaction: transaction, mediaBox: mediaBox, ids: ids, accountID: accountPeerId.toInt64())"
if global_capture_anchor in state_text:
    state_text = state_text.replace(global_capture_anchor, global_handler_call + "\n", 1)
elif global_handler_call not in state_text:
    raise SystemExit("Global-ID event is not routed through the shared production handler")
unused_global_lookup = "                let messageIds = transaction.messageIdsForGlobalIds(ids)\n"
if unused_global_lookup in state_text:
    state_text = state_text.replace(unused_global_lookup, "", 1)
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

# Channel/supergroup updates have a PTS gate. The stock code queued DeleteMessages
# only for contiguous PTS. When the PTS had a gap or channel state was unknown,
# it polled the channel without queuing the deletion operation, bypassing our
# replayFinalState retention handler. Queue every non-stale channel deletion.
channel_delete_case = find_case_block(
    state_text,
    "case let .updateDeleteChannelMessages(updateDeleteChannelMessagesData):",
    "previousState.pts + ptsCount == pts"
)
if channel_delete_case is None:
    raise SystemExit("Channel/supergroup updateDeleteChannelMessages PTS handler was not found")
channel_delete_start, channel_delete_end, channel_delete_block = channel_delete_case
channel_delete_block = replace_once(
    channel_delete_block,
    "let peerId = PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(channelId))\n",
    "let peerId = PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(channelId))\n                let channelDeletedMessageIds = messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) })\n",
    "channel deletion message IDs"
)
channel_delete_block = replace_once(
    channel_delete_block,
    "updatedState.deleteMessages(messages.map({ MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) }))",
    "updatedState.deleteMessages(channelDeletedMessageIds)",
    "contiguous channel delete operation"
)
channel_delete_block = replace_once(
    channel_delete_block,
    "} else {\n                        if !missingUpdatesFromChannels.contains(peerId) {",
    r"""} else {
                        updatedState.deleteMessages(channelDeletedMessageIds)
                        print("[AyuGram] queued channel deletion before PTS repair: channel=\(channelId), count=\(messages.count), previousPts=\(previousState.pts), pts=\(pts), ptsCount=\(ptsCount)")
                        if !missingUpdatesFromChannels.contains(peerId) {""",
    "channel deletion when PTS has a gap"
)
channel_delete_block = replace_once(
    channel_delete_block,
    "} else {\n                    if case .none = channelsToPoll[peerId] {",
    r"""} else {
                    updatedState.deleteMessages(channelDeletedMessageIds)
                    print("[AyuGram] queued channel deletion with unknown PTS state: channel=\(channelId), count=\(messages.count), pts=\(pts)")
                    if case .none = channelsToPoll[peerId] {""",
    "channel deletion when PTS state is unknown"
)
state_text = state_text[:channel_delete_start] + channel_delete_block + state_text[channel_delete_end:]
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


# Media-only messages use ChatMessageMediaBubbleContentNode and then pass
# ChatMessageDateAndStatus through ChatMessageInteractiveMediaNode. They do
# not use the text-bubble date path above, so explicitly carry the tombstone
# marker through this separate image/video status pipeline.
media_bubble_text = MEDIA_BUBBLE.read_text(encoding="utf-8")
media_bubble_text = replace_once(
    media_bubble_text,
    """            var edited = false
            if item.attributes.updatingMedia != nil {
                edited = true
            }
""",
    """            var edited = false
            var isAyuGramDeleted = false
            if item.attributes.updatingMedia != nil {
                edited = true
            }
""",
    "media-only deleted-state variable"
)
media_bubble_text = replace_once(
    media_bubble_text,
    """                if let attribute = attribute as? EditedMessageAttribute {
                    if case .mosaic = preparePosition {
                    } else {
                        edited = !attribute.isHidden
                    }
""",
    """                if let attribute = attribute as? EditedMessageAttribute {
                    if attribute.date == Int32.min {
                        isAyuGramDeleted = true
                        edited = false
                    } else if case .mosaic = preparePosition {
                    } else {
                        edited = !attribute.isHidden
                    }
""",
    "media-only deleted sentinel detection"
)
media_bubble_text = replace_once(
    media_bubble_text,
    """                    edited: edited,
                    viewCount: viewCount,
""",
    """                    edited: edited,
                    isAyuGramDeleted: isAyuGramDeleted,
                    viewCount: viewCount,
""",
    "media-only status marker handoff"
)
MEDIA_BUBBLE.write_text(media_bubble_text, encoding="utf-8")

interactive_media_text = INTERACTIVE_MEDIA.read_text(encoding="utf-8")
interactive_media_text = replace_once(
    interactive_media_text,
    "    public var edited: Bool\n    public var viewCount: Int?\n",
    "    public var edited: Bool\n    public var isAyuGramDeleted: Bool\n    public var viewCount: Int?\n",
    "interactive media status marker property"
)
interactive_media_text = replace_once(
    interactive_media_text,
    "        edited: Bool,\n        viewCount: Int?,\n",
    "        edited: Bool,\n        isAyuGramDeleted: Bool = false,\n        viewCount: Int?,\n",
    "interactive media status marker initializer"
)
interactive_media_text = replace_once(
    interactive_media_text,
    "        self.edited = edited\n        self.viewCount = viewCount\n",
    "        self.edited = edited\n        self.isAyuGramDeleted = isAyuGramDeleted\n        self.viewCount = viewCount\n",
    "interactive media status marker assignment"
)
interactive_media_text = replace_once(
    interactive_media_text,
    "                    edited: dateAndStatus.edited && !presentationData.isPreview,\n                    impressionCount:",
    "                    edited: dateAndStatus.edited && !presentationData.isPreview,\n                    isAyuGramDeleted: dateAndStatus.isAyuGramDeleted && !presentationData.isPreview,\n                    impressionCount:",
    "interactive media status marker passed to date node"
)
INTERACTIVE_MEDIA.write_text(interactive_media_text, encoding="utf-8")


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
entry = entry.replace("        case .history: return 103\n", "", 1)
history_case = entry.find("        case .history:\n")
if history_case >= 0:
    next_case = None
    for marker in (
        "        case .privateInvitePreview:\n",
        "        case .clearDeletedHistory:\n",
    ):
        position = entry.find(marker, history_case)
        if position >= 0 and (next_case is None or position < next_case):
            next_case = position
    if next_case is None:
        raise SystemExit("Could not find the next AyuGram settings case after History")
    entry = entry[:history_case] + entry[next_case:]
if "case .privateInvitePreview:" not in entry:
    raise SystemExit("Private group preview action was removed with the History shortcut")
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
media_bubble_check = MEDIA_BUBBLE.read_text(encoding="utf-8")
interactive_media_check = INTERACTIVE_MEDIA.read_text(encoding="utf-8")
assert "preserveDeletedMessagesInChat: Bool = false" in delete_check
assert "?.settings.saveDeletedMessages != false" in delete_check
assert "?.settings.saveDeletedMessages != false" in state_check
assert "let idsToDelete = ids.filter { !ayuRetainedDeletedMessageIds.contains($0) }" in delete_check
assert "preserveDeletedMessagesInChat: true" in state_check
assert "ayuRetainedGlobalIds" in state_check
# Basic-group deletion uses Global IDs; supergroup deletion uses channel-scoped local IDs.
channel_delete_case = find_case_block(
    state_check,
    "case let .updateDeleteChannelMessages(updateDeleteChannelMessagesData):",
    "previousState.pts + ptsCount == pts"
)
assert channel_delete_case is not None, "Supergroup/channel delete update handler is missing"
_, _, channel_delete_block = channel_delete_case
assert "let channelDeletedMessageIds = messages.map" in channel_delete_block
assert channel_delete_block.count("updatedState.deleteMessages(channelDeletedMessageIds)") == 3, "Channel/supergroup deletes must be queued for contiguous PTS, PTS gaps and unknown channel state"
assert "queued channel deletion before PTS repair" in channel_delete_block
assert "queued channel deletion with unknown PTS state" in channel_delete_block
assert "ayuGlobalIdsToDelete = ids.filter" in state_check
assert "_internal_applyAyuGramServerDeleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ids, accountID: accountPeerId.toInt64())" in state_check
assert "_internal_applyAyuGramServerDeleteMessagesWithGlobalIds(transaction: transaction, mediaBox: mediaBox, ids: ids, accountID: accountPeerId.toInt64())" in state_check
assert "public func _internal_applyAyuGramServerDeleteMessages(" in state_check
assert "public func _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(" in state_check
assert "public func _internal_retainDeletedMessagesWithGlobalIds" in state_check
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
assert "isAyuGramDeleted = true" in media_bubble_check
assert "isAyuGramDeleted: isAyuGramDeleted" in media_bubble_check
assert "public var isAyuGramDeleted: Bool" in interactive_media_check
assert "isAyuGramDeleted: dateAndStatus.isAyuGramDeleted && !presentationData.isPreview" in interactive_media_check
print("PASS: deleted markers are routed for text bubbles and media-only image/video status overlays.")
print("PASS: server-deleted messages remain as local rows in their original chat.")
print("PASS: the original text/media/timestamp stay on the Telegram message; the timestamp carries the 🧹 mark.")
print("PASS: interactive deletion still uses Telegram's normal deletion path.")
print("PASS: the standalone AyuGram History navigation shortcuts are removed.")
print("PASS: media archive, Before and Manual Save/saved/king code paths were not changed.")
