from pathlib import Path

p = Path("submodules/TelegramUI/Sources/AppDelegate.swift")
s = p.read_text(encoding="utf-8")

if "import AyuGramIOS" not in s:
    s = s.replace("import UIKit\n", "import UIKit\nimport AyuGramIOS\n", 1)
if "import AyuGramSettingsScreen" not in s:
    s = s.replace("import AyuGramIOS\n", "import AyuGramIOS\nimport AyuGramSettingsScreen\n", 1)

anchor = "                    self.mainWindow.viewController = context.rootController\n"
if anchor not in s:
    raise SystemExit("AppDelegate History hook anchor not found")

hook = """                    self.mainWindow.viewController = context.rootController

                    if ProcessInfo.processInfo.arguments.contains("-AyuGramHistoryListSmokeTest") {
                        let accountID = context.context.account.peerId.toInt64()
                        let dialogID: Int64 = 933000001
                        let now = Int32(Date().timeIntervalSince1970)
                        let messageID: Int32 = 1700000123
                        let fixtureMessage = AyuMessage(
                            fakeID: 0,
                            userID: accountID,
                            dialogID: dialogID,
                            peerID: dialogID,
                            fromID: accountID,
                            fromName: "Smoke Test Sender",
                            messageID: messageID,
                            date: now - 60,
                            text: "Synthetic deleted message for History UI smoke test",
                            isDeleted: true,
                            deletedAt: now
                        )

                        let fixtureSignal = context.context.account.postbox.transaction { transaction -> Bool in
                            AyuGramPostboxHistoryStore.clearDeleted(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: dialogID
                            )
                            _ = AyuGramPostboxHistoryStore.appendDeleted(
                                transaction: transaction,
                                messages: [fixtureMessage]
                            )
                            let rows = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: dialogID,
                                kind: .deleted,
                                limit: 25
                            )
                            return rows.contains {
                                $0.text == fixtureMessage.text
                                    && $0.fromName == "Smoke Test Sender"
                                    && $0.deletedAt == now
                            }
                        }

                        _ = (fixtureSignal |> deliverOnMainQueue).start(next: { ready in
                            guard ready else {
                                print("AyuGram History list fixture failed to persist")
                                return
                            }

                            self.mainWindow.present(
                                ayuGramHistoryScreen(context: context.context, dialogID: dialogID),
                                on: .root
                            )

                            DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                                guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
                                    print("AyuGram History list fixture has no Documents directory")
                                    return
                                }
                                let reportURL = documents.appendingPathComponent("AyuGramHistoryListSmokeReport.json")
                                let markerURL = documents.appendingPathComponent("AyuGramHistoryListHarnessReady.txt")
                                let report: [String: Any] = [
                                    "passed": true,
                                    "dialogID": dialogID,
                                    "messageID": messageID,
                                    "senderName": "Smoke Test Sender",
                                    "text": fixtureMessage.text,
                                    "deletedAt": now
                                ]
                                do {
                                    let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
                                    try data.write(to: reportURL, options: .atomic)
                                    try Data("History list fixture ready".utf8).write(to: markerURL, options: .atomic)
                                    print("AyuGram History list fixture rendered for dialog \(dialogID)")
                                } catch {
                                    print("AyuGram History list fixture report write failed: \(error)")
                                }
                            }
                        })
                    }

                    if ProcessInfo.processInfo.arguments.contains("-AyuGramFullSmokeTest") {
                        let accountID = context.context.account.peerId.toInt64()
                        let reportURL = (try? AyuGramRuntime.baseDirectory(accountID: accountID))?
                            .appendingPathComponent("AyuGramSmokeReport.json")

                        let testReportSignal = context.context.account.postbox.transaction { transaction in
                            AyuGramSmokeTest.run(accountID: accountID, transaction: transaction)
                        }

                        _ = (testReportSignal |> deliverOnMainQueue).start(next: { report in
                            if let reportURL {
                                do {
                                    let data = try JSONEncoder().encode(report)
                                    try data.write(to: reportURL, options: .atomic)
                                    let historyMarker = reportURL.deletingLastPathComponent().appendingPathComponent("AyuGramHistoryPresented.txt")
                                    try? Data("AyuGram History ready".utf8).write(to: historyMarker, options: .atomic)
                                } catch {
                                    print("AyuGram smoke report write failed: \(error)")
                                }
                            }

                            self.mainWindow.present(
                                ayuGramHistoryScreen(context: context.context),
                                on: .root
                            )
                        })
                    }

"""

if "AyuGram History ready" not in s:
    s = s.replace(anchor, hook, 1)


deleted_capture_hook = """                    if ProcessInfo.processInfo.arguments.contains("-AyuGramDeletedCaptureSmokeTest"), let context = context {
                        let account = context.account
                        // This smoke hook runs in Telegram's logged-out UnauthorizedAccount fixture,
                        // which has AccountRecordId but no peerId. Use its isolated record namespace here;
                        // production deletion updates continue to key settings by accountPeerId.toInt64().
                        let accountID = account.id.int64
                        let testPeerId = PeerId(933000001)
                        let dialogID = testPeerId.toInt64()
                        let now = Int32(Date().timeIntervalSince1970)
                        let messageID = MessageId(peerId: testPeerId, namespace: Namespaces.Message.Cloud, id: 1700000124)
                        let messageText = "Synthetic message routed through deleted retention helper"

                        let settingsStore = try? AyuGramRuntime.cachedSettingsStore(accountID: accountID)
                        let originalSaveDeletedMessages = settingsStore?.settings.saveDeletedMessages
                        // Do not switch the feature ON inside this test: production must arrive here
                        // with auto-save already enabled by defaults or the one-time account migration.
                        let captureEnabledOnEntry = originalSaveDeletedMessages == true

                        let captureSignal = account.postbox.transaction { transaction -> (AyuMessage?, [String: Bool]) in
                            let storeMessage = StoreMessage(
                                id: messageID,
                                customStableId: nil,
                                globallyUniqueId: nil,
                                groupingKey: nil,
                                threadId: nil,
                                timestamp: now,
                                flags: [],
                                tags: [],
                                globalTags: [],
                                localTags: [],
                                forwardInfo: nil,
                                authorId: nil,
                                text: messageText,
                                attributes: [],
                                media: []
                            )
                            transaction.addMessages([storeMessage], location: .Random)

                            let retainedIDs = _internal_applyAyuGramServerDeleteMessages(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [messageID],
                                accountID: accountID
                            )
                            let retainedMessage = transaction.getMessage(messageID)
                            let retainedInChat = retainedMessage?.text == messageText
                            let hasDeletedMarker = retainedMessage?.attributes.contains(where: {
                                ($0 as? EditedMessageAttribute)?.date == Int32.min
                            }) ?? false
                            let captured = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: dialogID,
                                kind: .deleted,
                                limit: 100
                            ).first { $0.messageID == messageID.id && $0.text == messageText }

                            let globalTestPeerId = PeerId(933000002)
                            let globalMessageID = MessageId(peerId: globalTestPeerId, namespace: Namespaces.Message.Cloud, id: 1700000125)
                            let globalMessageText = "Synthetic message routed through Global ID deleted retention"
                            let globalStoreMessage = StoreMessage(
                                id: globalMessageID,
                                customStableId: nil,
                                globallyUniqueId: nil,
                                groupingKey: nil,
                                threadId: nil,
                                timestamp: now,
                                flags: [],
                                tags: [],
                                globalTags: [],
                                localTags: [],
                                forwardInfo: nil,
                                authorId: nil,
                                text: globalMessageText,
                                attributes: [],
                                media: []
                            )
                            transaction.addMessages([globalStoreMessage], location: .Random)

                            let resolvedGlobalMessageID = transaction.messageIdsForGlobalIds([globalMessageID.id]).first
                            let globalLookupSucceeded = resolvedGlobalMessageID == globalMessageID
                            let retainedGlobalIDs = _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [globalMessageID.id],
                                accountID: accountID
                            )
                            let globalIDsToDelete = [globalMessageID.id].filter { !retainedGlobalIDs.contains($0) }
                            transaction.deleteMessagesWithGlobalIds(globalIDsToDelete, forEachMedia: { _ in })
                            let retainedGlobalMessage = transaction.getMessage(globalMessageID)
                            let globalRetainedInChat = retainedGlobalMessage?.text == globalMessageText
                            let globalHasDeletedMarker = retainedGlobalMessage?.attributes.contains(where: {
                                ($0 as? EditedMessageAttribute)?.date == Int32.min
                            }) ?? false
                            let globalReturnedRetainedID = retainedGlobalIDs.contains(globalMessageID.id)
                            let globalDeletionFiltered = globalIDsToDelete.isEmpty && retainedGlobalMessage != nil

                            // Basic groups use GlobalMessageIdsTable (CloudGroup); test that namespace,
                            // not only the private-chat CloudUser namespace used above.
                            let cloudGroupPeerId = PeerId(
                                namespace: Namespaces.Peer.CloudGroup,
                                id: PeerId.Id._internalFromInt64Value(933000004)
                            )
                            let cloudGroupMessageID = MessageId(
                                peerId: cloudGroupPeerId,
                                namespace: Namespaces.Message.Cloud,
                                id: 1700000127
                            )
                            let cloudGroupMessageText = "Synthetic CloudGroup deletion must be retained"
                            let cloudGroupStoreMessage = StoreMessage(
                                id: cloudGroupMessageID,
                                customStableId: nil,
                                globallyUniqueId: nil,
                                groupingKey: nil,
                                threadId: nil,
                                timestamp: now,
                                flags: [],
                                tags: [],
                                globalTags: [],
                                localTags: [],
                                forwardInfo: nil,
                                authorId: nil,
                                text: cloudGroupMessageText,
                                attributes: [],
                                media: []
                            )
                            transaction.addMessages([cloudGroupStoreMessage], location: .Random)
                            let cloudGroupLookupSucceeded = transaction.messageIdsForGlobalIds([cloudGroupMessageID.id]).first == cloudGroupMessageID
                            let cloudGroupRetainedIDs = _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [cloudGroupMessageID.id],
                                accountID: accountID
                            )
                            let cloudGroupIDsToDelete = [cloudGroupMessageID.id].filter { !cloudGroupRetainedIDs.contains($0) }
                            transaction.deleteMessagesWithGlobalIds(cloudGroupIDsToDelete, forEachMedia: { _ in })
                            let cloudGroupRetainedMessage = transaction.getMessage(cloudGroupMessageID)
                            let cloudGroupRetainedInChat = cloudGroupRetainedMessage?.text == cloudGroupMessageText
                            let cloudGroupHasDeletedMarker = cloudGroupRetainedMessage?.attributes.contains(where: {
                                ($0 as? EditedMessageAttribute)?.date == Int32.min
                            }) ?? false
                            let cloudGroupReturnedRetainedID = cloudGroupRetainedIDs.contains(cloudGroupMessageID.id)
                            let cloudGroupDeletionFiltered = cloudGroupIDsToDelete.isEmpty && cloudGroupRetainedMessage != nil
                            let cloudGroupHistoryCaptured = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: cloudGroupPeerId.toInt64(),
                                kind: .deleted,
                                limit: 100
                            ).contains { $0.messageID == cloudGroupMessageID.id && $0.text == cloudGroupMessageText && $0.isDeleted }
                            let cloudGroupDuplicateRetainedIDs = _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [cloudGroupMessageID.id],
                                accountID: accountID
                            )
                            let cloudGroupHistoryCount = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: cloudGroupPeerId.toInt64(),
                                kind: .deleted,
                                limit: 100
                            ).filter { $0.messageID == cloudGroupMessageID.id && $0.text == cloudGroupMessageText && $0.isDeleted }.count
                            let cloudGroupDuplicateIsIdempotent = cloudGroupDuplicateRetainedIDs.contains(cloudGroupMessageID.id)
                                && cloudGroupHistoryCount == 1

                            // Supergroups/channels use updateDeleteChannelMessages and local MessageIds.
                            let cloudChannelPeerId = PeerId(
                                namespace: Namespaces.Peer.CloudChannel,
                                id: PeerId.Id._internalFromInt64Value(933000005)
                            )
                            let cloudChannelMessageID = MessageId(
                                peerId: cloudChannelPeerId,
                                namespace: Namespaces.Message.Cloud,
                                id: 1700000128
                            )
                            let cloudChannelMessageText = "Synthetic CloudChannel deletion must be retained"
                            let cloudChannelStoreMessage = StoreMessage(
                                id: cloudChannelMessageID,
                                customStableId: nil,
                                globallyUniqueId: nil,
                                groupingKey: nil,
                                threadId: nil,
                                timestamp: now,
                                flags: [],
                                tags: [],
                                globalTags: [],
                                localTags: [],
                                forwardInfo: nil,
                                authorId: nil,
                                text: cloudChannelMessageText,
                                attributes: [],
                                media: []
                            )
                            transaction.addMessages([cloudChannelStoreMessage], location: .Random)
                            let cloudChannelRetainedIDs = _internal_applyAyuGramServerDeleteMessages(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [cloudChannelMessageID],
                                accountID: accountID
                            )
                            let cloudChannelRetainedMessage = transaction.getMessage(cloudChannelMessageID)
                            let cloudChannelRetainedInChat = cloudChannelRetainedMessage?.text == cloudChannelMessageText
                            let cloudChannelHasDeletedMarker = cloudChannelRetainedMessage?.attributes.contains(where: {
                                ($0 as? EditedMessageAttribute)?.date == Int32.min
                            }) ?? false
                            let cloudChannelReturnedRetainedID = cloudChannelRetainedIDs.contains(cloudChannelMessageID)
                            let cloudChannelHistoryCaptured = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: cloudChannelPeerId.toInt64(),
                                kind: .deleted,
                                limit: 100
                            ).contains { $0.messageID == cloudChannelMessageID.id && $0.text == cloudChannelMessageText && $0.isDeleted }
                            let cloudChannelDuplicateRetainedIDs = _internal_applyAyuGramServerDeleteMessages(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [cloudChannelMessageID],
                                accountID: accountID
                            )
                            let cloudChannelHistoryCount = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: cloudChannelPeerId.toInt64(),
                                kind: .deleted,
                                limit: 100
                            ).filter { $0.messageID == cloudChannelMessageID.id && $0.text == cloudChannelMessageText && $0.isDeleted }.count
                            let cloudChannelDuplicateIsIdempotent = cloudChannelDuplicateRetainedIDs.contains(cloudChannelMessageID)
                                && cloudChannelHistoryCount == 1

                            // A message cached on receipt must still be recoverable if its Postbox
                            // row disappears before the later server deletion update is replayed.
                            let receiveCacheChannelPeer = PeerId(
                                namespace: Namespaces.Peer.CloudChannel,
                                id: PeerId.Id._internalFromInt64Value(933000006)
                            )
                            let receiveCacheChannelID = MessageId(
                                peerId: receiveCacheChannelPeer,
                                namespace: Namespaces.Message.Cloud,
                                id: 1700000130
                            )
                            let receiveCacheChannelText = "Synthetic receive-cache CloudChannel fallback"
                            let receiveCacheChannelStoreMessage = StoreMessage(
                                id: receiveCacheChannelID,
                                customStableId: nil,
                                globallyUniqueId: nil,
                                groupingKey: nil,
                                threadId: nil,
                                timestamp: now,
                                flags: [],
                                tags: [],
                                globalTags: [],
                                localTags: [],
                                forwardInfo: nil,
                                authorId: nil,
                                text: receiveCacheChannelText,
                                attributes: [],
                                media: []
                            )
                            transaction.addMessages([receiveCacheChannelStoreMessage], location: .Random)
                            _internal_cacheAyuGramReceivedMessages(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [receiveCacheChannelID],
                                ayuAccountID: accountID
                            )
                            let receiveCacheChannelUpdatedText = "Synthetic receive-cache CloudChannel latest edited revision"
                            let receiveCacheChannelUpdatedStoreMessage = StoreMessage(
                                id: receiveCacheChannelID,
                                customStableId: nil,
                                globallyUniqueId: nil,
                                groupingKey: nil,
                                threadId: nil,
                                timestamp: now,
                                flags: [],
                                tags: [],
                                globalTags: [],
                                localTags: [],
                                forwardInfo: nil,
                                authorId: nil,
                                text: receiveCacheChannelUpdatedText,
                                attributes: [],
                                media: []
                            )
                            transaction.updateMessage(receiveCacheChannelID, update: { _ in
                                return .update(receiveCacheChannelUpdatedStoreMessage)
                            })
                            _internal_cacheAyuGramReceivedMessages(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [receiveCacheChannelID],
                                ayuAccountID: accountID
                            )
                            transaction.deleteMessages([receiveCacheChannelID], forEachMedia: { _ in })
                            _ = _internal_applyAyuGramServerDeleteMessages(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [receiveCacheChannelID],
                                accountID: accountID
                            )
                            let receiveCacheChannelRecovered = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: receiveCacheChannelPeer.toInt64(),
                                kind: .deleted,
                                limit: 100
                            ).contains {
                                $0.messageID == receiveCacheChannelID.id
                                    && $0.text == receiveCacheChannelUpdatedText
                                    && $0.isDeleted
                                    && $0.deletedAt != nil
                            }
                            // Replaying the same delete after the cache entry was consumed
                            // must not create a second History row.
                            _ = _internal_applyAyuGramServerDeleteMessages(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [receiveCacheChannelID],
                                accountID: accountID
                            )
                            let receiveCacheChannelHistoryCount = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: receiveCacheChannelPeer.toInt64(),
                                kind: .deleted,
                                limit: 100
                            ).filter {
                                $0.messageID == receiveCacheChannelID.id
                                    && $0.text == receiveCacheChannelUpdatedText
                                    && $0.isDeleted
                            }.count
                            let receiveCacheChannelReplayIsIdempotent = receiveCacheChannelHistoryCount == 1

                            // Basic groups use Global IDs. Remove both the row and its lookup
                            // mapping before replaying deletion to prove the cache fallback works.
                            let receiveCacheGroupPeer = PeerId(
                                namespace: Namespaces.Peer.CloudGroup,
                                id: PeerId.Id._internalFromInt64Value(933000007)
                            )
                            let receiveCacheGroupID = MessageId(
                                peerId: receiveCacheGroupPeer,
                                namespace: Namespaces.Message.Cloud,
                                id: 1700000131
                            )
                            let receiveCacheGroupText = "Synthetic receive-cache CloudGroup Global ID fallback"
                            let receiveCacheGroupStoreMessage = StoreMessage(
                                id: receiveCacheGroupID,
                                customStableId: nil,
                                globallyUniqueId: nil,
                                groupingKey: nil,
                                threadId: nil,
                                timestamp: now,
                                flags: [],
                                tags: [],
                                globalTags: [],
                                localTags: [],
                                forwardInfo: nil,
                                authorId: nil,
                                text: receiveCacheGroupText,
                                attributes: [],
                                media: []
                            )
                            transaction.addMessages([receiveCacheGroupStoreMessage], location: .Random)
                            _internal_cacheAyuGramReceivedMessages(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [receiveCacheGroupID],
                                ayuAccountID: accountID
                            )
                            transaction.deleteMessages([receiveCacheGroupID], forEachMedia: { _ in })
                            let receiveCacheGroupLookupAfterDelete = transaction.messageIdsForGlobalIds([receiveCacheGroupID.id]).isEmpty
                            _ = _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [receiveCacheGroupID.id],
                                accountID: accountID
                            )
                            let receiveCacheGroupRecovered = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: receiveCacheGroupPeer.toInt64(),
                                kind: .deleted,
                                limit: 100
                            ).contains {
                                $0.messageID == receiveCacheGroupID.id
                                    && $0.text == receiveCacheGroupText
                                    && $0.isDeleted
                                    && $0.deletedAt != nil
                            }
                            // A repeated Global-ID delete must remain a single row.
                            _ = _internal_applyAyuGramServerDeleteMessagesWithGlobalIds(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [receiveCacheGroupID.id],
                                accountID: accountID
                            )
                            let receiveCacheGroupHistoryCount = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: accountID,
                                dialogID: receiveCacheGroupPeer.toInt64(),
                                kind: .deleted,
                                limit: 100
                            ).filter {
                                $0.messageID == receiveCacheGroupID.id
                                    && $0.text == receiveCacheGroupText
                                    && $0.isDeleted
                            }.count
                            let receiveCacheGroupReplayIsIdempotent = receiveCacheGroupHistoryCount == 1

                            let fallbackAccountID = accountID + Int64(now) + 9_000_000_000
                            let fallbackPeerId = PeerId(933000003)
                            let fallbackDialogID = fallbackPeerId.toInt64()
                            let fallbackMessageID = MessageId(peerId: fallbackPeerId, namespace: Namespaces.Message.Cloud, id: 1700000126)
                            let fallbackMessageText = "Synthetic deletion with unreadable settings must default ON"
                            let fallbackSettingsURL = (try? AyuGramRuntime.baseDirectory(accountID: fallbackAccountID))?
                                .appendingPathComponent("settings.json")
                            let fallbackSettingsPrepared: Bool
                            if let fallbackSettingsURL {
                                do {
                                    try Data("invalid-settings-json".utf8).write(to: fallbackSettingsURL, options: .atomic)
                                    fallbackSettingsPrepared = true
                                } catch {
                                    fallbackSettingsPrepared = false
                                }
                            } else {
                                fallbackSettingsPrepared = false
                            }
                            let fallbackStoreMessage = StoreMessage(
                                id: fallbackMessageID,
                                customStableId: nil,
                                globallyUniqueId: nil,
                                groupingKey: nil,
                                threadId: nil,
                                timestamp: now,
                                flags: [],
                                tags: [],
                                globalTags: [],
                                localTags: [],
                                forwardInfo: nil,
                                authorId: nil,
                                text: fallbackMessageText,
                                attributes: [],
                                media: []
                            )
                            transaction.addMessages([fallbackStoreMessage], location: .Random)
                            let fallbackRetainedIDs = _internal_applyAyuGramServerDeleteMessages(
                                transaction: transaction,
                                mediaBox: account.postbox.mediaBox,
                                ids: [fallbackMessageID],
                                accountID: fallbackAccountID
                            )
                            let fallbackPostboxMessage = transaction.getMessage(fallbackMessageID)
                            let fallbackHasDeletedMarker = fallbackPostboxMessage?.attributes.contains(where: {
                                ($0 as? EditedMessageAttribute)?.date == Int32.min
                            }) ?? false
                            let fallbackHistoryCaptured = AyuGramPostboxHistoryStore.filtered(
                                transaction: transaction,
                                userID: fallbackAccountID,
                                dialogID: fallbackDialogID,
                                kind: .deleted,
                                limit: 100
                            ).contains { $0.messageID == fallbackMessageID.id && $0.text == fallbackMessageText }
                            let fallbackSettingsUnavailable = (try? AyuGramRuntime.makeSettingsStore(accountID: fallbackAccountID)) == nil
                            let fallbackCasePassed = fallbackSettingsPrepared
                                && fallbackSettingsUnavailable
                                && fallbackRetainedIDs.contains(fallbackMessageID)
                                && fallbackPostboxMessage?.text == fallbackMessageText
                                && fallbackHasDeletedMarker
                                && fallbackHistoryCaptured

                            return (
                                captured,
                                [
                                    "retainedInChat": retainedInChat,
                                    "hasDeletedMarker": hasDeletedMarker,
                                    "returnedRetainedID": retainedIDs.contains(messageID),
                                    "globalLookupSucceeded": globalLookupSucceeded,
                                    "globalRetainedInChat": globalRetainedInChat,
                                    "globalHasDeletedMarker": globalHasDeletedMarker,
                                    "globalReturnedRetainedID": globalReturnedRetainedID,
                                    "globalDeletionFiltered": globalDeletionFiltered,
                                    "cloudGroupLookupSucceeded": cloudGroupLookupSucceeded,
                                    "cloudGroupRetainedInChat": cloudGroupRetainedInChat,
                                    "cloudGroupHasDeletedMarker": cloudGroupHasDeletedMarker,
                                    "cloudGroupReturnedRetainedID": cloudGroupReturnedRetainedID,
                                    "cloudGroupDeletionFiltered": cloudGroupDeletionFiltered,
                                    "cloudGroupHistoryCaptured": cloudGroupHistoryCaptured,
                                    "cloudGroupDuplicateIsIdempotent": cloudGroupDuplicateIsIdempotent,
                                    "cloudChannelRetainedInChat": cloudChannelRetainedInChat,
                                    "cloudChannelHasDeletedMarker": cloudChannelHasDeletedMarker,
                                    "cloudChannelReturnedRetainedID": cloudChannelReturnedRetainedID,
                                    "cloudChannelHistoryCaptured": cloudChannelHistoryCaptured,
                                    "cloudChannelDuplicateIsIdempotent": cloudChannelDuplicateIsIdempotent,
                                    "receiveCacheChannelRecovered": receiveCacheChannelRecovered,
                                    "receiveCacheChannelReplayIsIdempotent": receiveCacheChannelReplayIsIdempotent,
                                    "receiveCacheGroupLookupAfterDelete": receiveCacheGroupLookupAfterDelete,
                                    "receiveCacheGroupRecovered": receiveCacheGroupRecovered,
                                    "receiveCacheGroupReplayIsIdempotent": receiveCacheGroupReplayIsIdempotent,
                                    "settingsFallbackCapture": fallbackCasePassed
                                ]
                            )
                        }

                        _ = (captureSignal |> deliverOnMainQueue).start(next: { result in
                            let captureEnabled = settingsStore?.settings.saveDeletedMessages ?? false
                            let historyCaptured = result.0?.isDeleted == true && result.0?.text == messageText
                            let passed = captureEnabledOnEntry
                                && captureEnabled
                                && historyCaptured
                                && result.1["retainedInChat"] == true
                                && result.1["hasDeletedMarker"] == true
                                && result.1["returnedRetainedID"] == true
                                && result.1["globalLookupSucceeded"] == true
                                && result.1["globalRetainedInChat"] == true
                                && result.1["globalHasDeletedMarker"] == true
                                && result.1["globalReturnedRetainedID"] == true
                                && result.1["globalDeletionFiltered"] == true
                                && result.1["cloudGroupLookupSucceeded"] == true
                                && result.1["cloudGroupRetainedInChat"] == true
                                && result.1["cloudGroupHasDeletedMarker"] == true
                                && result.1["cloudGroupReturnedRetainedID"] == true
                                && result.1["cloudGroupDeletionFiltered"] == true
                                && result.1["cloudGroupHistoryCaptured"] == true
                                && result.1["cloudGroupDuplicateIsIdempotent"] == true
                                && result.1["cloudChannelRetainedInChat"] == true
                                && result.1["cloudChannelHasDeletedMarker"] == true
                                && result.1["cloudChannelReturnedRetainedID"] == true
                                && result.1["cloudChannelHistoryCaptured"] == true
                                && result.1["cloudChannelDuplicateIsIdempotent"] == true
                                && result.1["receiveCacheChannelRecovered"] == true
                                && result.1["receiveCacheChannelReplayIsIdempotent"] == true
                                && result.1["receiveCacheGroupLookupAfterDelete"] == true
                                && result.1["receiveCacheGroupRecovered"] == true
                                && result.1["receiveCacheGroupReplayIsIdempotent"] == true
                                && result.1["settingsFallbackCapture"] == true
                            if let settingsStore, let originalSaveDeletedMessages {
                                try? settingsStore.update { $0.saveDeletedMessages = originalSaveDeletedMessages }
                            }
                            let report: [String: Any] = [
                                "passed": passed,
                                "captureEnabled": captureEnabled,
                                "captureEnabledOnEntry": captureEnabledOnEntry,
                                "historyCaptured": historyCaptured,
                                "retainedInChat": result.1["retainedInChat"] == true,
                                "hasDeletedMarker": result.1["hasDeletedMarker"] == true,
                                "returnedRetainedID": result.1["returnedRetainedID"] == true,
                                "dialogID": dialogID,
                                "messageID": Int(messageID.id),
                                "capturedText": result.0?.text ?? "",
                                "isDeleted": result.0?.isDeleted ?? false,
                                "globalLookupSucceeded": result.1["globalLookupSucceeded"] == true,
                                "globalRetainedInChat": result.1["globalRetainedInChat"] == true,
                                "globalHasDeletedMarker": result.1["globalHasDeletedMarker"] == true,
                                "globalReturnedRetainedID": result.1["globalReturnedRetainedID"] == true,
                                "globalDeletionFiltered": result.1["globalDeletionFiltered"] == true,
                                "cloudGroupLookupSucceeded": result.1["cloudGroupLookupSucceeded"] == true,
                                "cloudGroupRetainedInChat": result.1["cloudGroupRetainedInChat"] == true,
                                "cloudGroupHasDeletedMarker": result.1["cloudGroupHasDeletedMarker"] == true,
                                "cloudGroupReturnedRetainedID": result.1["cloudGroupReturnedRetainedID"] == true,
                                "cloudGroupDeletionFiltered": result.1["cloudGroupDeletionFiltered"] == true,
                                "cloudGroupHistoryCaptured": result.1["cloudGroupHistoryCaptured"] == true,
                                "cloudChannelRetainedInChat": result.1["cloudChannelRetainedInChat"] == true,
                                "cloudChannelHasDeletedMarker": result.1["cloudChannelHasDeletedMarker"] == true,
                                "cloudChannelReturnedRetainedID": result.1["cloudChannelReturnedRetainedID"] == true,
                                "cloudChannelHistoryCaptured": result.1["cloudChannelHistoryCaptured"] == true,
                                "receiveCacheChannelRecovered": result.1["receiveCacheChannelRecovered"] == true,
                                "receiveCacheChannelReplayIsIdempotent": result.1["receiveCacheChannelReplayIsIdempotent"] == true,
                                "receiveCacheGroupLookupAfterDelete": result.1["receiveCacheGroupLookupAfterDelete"] == true,
                                "receiveCacheGroupRecovered": result.1["receiveCacheGroupRecovered"] == true,
                                "receiveCacheGroupReplayIsIdempotent": result.1["receiveCacheGroupReplayIsIdempotent"] == true,
                                "settingsFallbackCapture": result.1["settingsFallbackCapture"] == true
                            ]
                            guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
                                print("AyuGram deleted-retention smoke test has no Documents directory")
                                return
                            }
                            let reportURL = documents.appendingPathComponent("AyuGramDeletedCaptureSmokeReport.json")
                            do {
                                let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
                                try data.write(to: reportURL, options: .atomic)
                                print("AyuGram deleted-retention smoke test: \\(passed ? "PASS" : "FAIL")")
                            } catch {
                                print("AyuGram deleted-retention smoke report write failed: \\(error)")
                            }
                        })
                    }
"""

deleted_capture_anchor = "            self.authContextValue = context\n"
if "AyuGramDeletedCaptureSmokeTest" not in s:
    if s.count(deleted_capture_anchor) != 1:
        raise SystemExit("Unauthorized-account deleted-capture insertion anchor is not unique")
    s = s.replace(deleted_capture_anchor, deleted_capture_hook + deleted_capture_anchor, 1)

launch_anchor = "        let launchStartTime = CFAbsoluteTimeGetCurrent()"
standalone_hook = """        if ProcessInfo.processInfo.arguments.contains("-AyuGramFullSmokeTest") {
            var items: [AyuGramSmokeTestItem] = []
            func add(_ name: String, _ passed: Bool, _ details: String) {
                items.append(AyuGramSmokeTestItem(name: name, passed: passed, details: details))
            }

            var ghost = GhostModeSettings()
            ghost.sendWithoutSound = .inGhostMode
            ghost.setGhostModeEnabled(true)
            let policy = GhostModePolicy(settings: ghost)
            add("Ghost Mode policy", !policy.shouldSend(.readMessages) && !policy.shouldSend(.onlineStatus) && ghost.shouldSendWithoutSound, "read/online packet gates")

            let accountID: Int64 = 922337203
            let dialogID: Int64 = 933000001
            let messageID: Int32 = 1700000001

            // Verify the actual user-facing Saved layout:
            // Documents/Telegram/AyuGram/saved/Media
            // Documents/Telegram/AyuGram/saved/Messages
            let savedRoot = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first?
                .appendingPathComponent("Telegram", isDirectory: true)
                .appendingPathComponent("AyuGram", isDirectory: true)
                .appendingPathComponent("saved", isDirectory: true)
            let mediaRoot = savedRoot?.appendingPathComponent("Media", isDirectory: true)
            let messagesRoot = savedRoot?.appendingPathComponent("Messages", isDirectory: true)

            let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent("ayugram-standalone-smoke-media", isDirectory: true)
            try? FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
            let firstMedia = tempRoot.appendingPathComponent("0.jpg")
            let secondMedia = tempRoot.appendingPathComponent("1.mp4")
            try? Data("ayugram-smoke-photo".utf8).write(to: firstMedia, options: .atomic)
            try? Data("ayugram-smoke-video".utf8).write(to: secondMedia, options: .atomic)

            let message = AyuMessage(
                fakeID: 0,
                userID: accountID,
                dialogID: dialogID,
                peerID: dialogID,
                fromID: accountID,
                messageID: messageID,
                date: Int32(Date().timeIntervalSince1970),
                text: "standalone saved media",
                mediaPath: firstMedia.path,
                mimeType: "image/jpeg",
                isDeleted: true
            )
            let savedMedia = AyuGramMediaArchive.saveToSaved(message: message)
            let savedStem = "account-\\(accountID)-dialog-\\(dialogID)-message-\\(messageID)"
            let firstSaved = mediaRoot?.appendingPathComponent("\\(savedStem)-media-1.jpg")
            let secondSaved = mediaRoot?.appendingPathComponent("\\(savedStem)-media-2.mp4")
            let mediaMetadata = messagesRoot?.appendingPathComponent("\\(savedStem).json")
            let mediaText = messagesRoot?.appendingPathComponent("\\(savedStem).txt")
            let mediaOK = savedMedia
                && (firstSaved.map { FileManager.default.fileExists(atPath: $0.path) } ?? false)
                && (secondSaved.map { FileManager.default.fileExists(atPath: $0.path) } ?? false)
                && (mediaMetadata.map { FileManager.default.fileExists(atPath: $0.path) } ?? false)
                && (mediaText.map { FileManager.default.fileExists(atPath: $0.path) } ?? false)
            add("History → Saved media copy", mediaOK, "album media + text + metadata copied to Media/Messages")

            let sameIDOtherDialog = AyuMessage(
                fakeID: 0,
                userID: accountID,
                dialogID: dialogID + 2,
                peerID: dialogID + 2,
                fromID: accountID,
                messageID: messageID,
                date: Int32(Date().timeIntervalSince1970),
                text: "same message ID in another dialog",
                mediaPath: firstMedia.path,
                mimeType: "image/jpeg",
                isDeleted: true
            )
            let sameIDSaved = AyuGramMediaArchive.saveToSaved(message: sameIDOtherDialog)
            let otherDialogStem = "account-\\(accountID)-dialog-\\(dialogID + 2)-message-\\(messageID)"
            let otherDialogFile = mediaRoot?.appendingPathComponent("\\(otherDialogStem)-media-1.jpg")
            let isolatedSaveOK = sameIDSaved && (otherDialogFile.map { FileManager.default.fileExists(atPath: $0.path) } ?? false)
            add("Saved media isolation by dialog", isolatedSaveOK, "same message ID in another dialog receives a separate file")

            try? FileManager.default.removeItem(at: tempRoot)

            let textMessage = AyuMessage(
                fakeID: 0,
                userID: accountID,
                dialogID: dialogID + 1,
                peerID: dialogID + 1,
                fromID: accountID,
                messageID: messageID + 1,
                date: Int32(Date().timeIntervalSince1970),
                text: "standalone saved text",
                isDeleted: true
            )
            let savedText = AyuGramMediaArchive.saveToSaved(message: textMessage)
            let textSavedStem = "account-\\(accountID)-dialog-\\(dialogID + 1)-message-\\(messageID + 1)"
            let textFile = messagesRoot?.appendingPathComponent("\\(textSavedStem).txt")
            let textMetadata = messagesRoot?.appendingPathComponent("\\(textSavedStem).json")
            let textOK = savedText
                && (textFile.map { FileManager.default.fileExists(atPath: $0.path) } ?? false)
                && (textMetadata.map { FileManager.default.fileExists(atPath: $0.path) } ?? false)
            add("History → Saved text copy", textOK, "text + metadata copied to Messages")
            
            if let mediaRoot {
                try? FileManager.default.removeItem(at: mediaRoot.deletingLastPathComponent())
            }
            
            let now = Int64(Date().timeIntervalSince1970 * 1000.0)
            do {
                let legacySettingsURL = FileManager.default.temporaryDirectory
                    .appendingPathComponent("AyuGramLegacySettings-\(UUID().uuidString).json")
                defer { try? FileManager.default.removeItem(at: legacySettingsURL) }
                let legacyObject: [String: Any] = [
                    "saveMessagesHistory": false,
                    "translationProvider": "google",
                    "ghostByAccount": [
                        Int64(7) as Any,
                        ["sendReadMessages": false] as [String: Any] as Any
                    ],
                    "regexFilters": [
                        ["id": UUID().uuidString, "text": "legacy-filter"]
                    ]
                ]
                let legacyData = try JSONSerialization.data(withJSONObject: legacyObject, options: [.sortedKeys])
                try legacyData.write(to: legacySettingsURL, options: .atomic)
                let migratedStore = try AyuSettingsStore(url: legacySettingsURL)
                let migratedSettings = migratedStore.settings
                let reloadedStore = try AyuSettingsStore(url: legacySettingsURL)
                let reloadedSettings = reloadedStore.settings
                let ghostSettings = reloadedSettings.ghostSettings(for: 7)
                let preservedFilter = reloadedSettings.regexFilters.first
                let migrationPassed = migratedSettings.saveDeletedMessages
                    && !migratedSettings.saveMessagesHistory
                    && migratedSettings.translationProvider == .google
                    && !ghostSettings.sendReadMessages
                    && preservedFilter?.text == "legacy-filter"
                    && preservedFilter?.enabled == true
                    && reloadedSettings.saveDeletedMessages
                let runtimeMigrationAccountID = accountID + Int64(Date().timeIntervalSince1970) + 8_000_000_000
                let runtimeMigrationDirectory = try AyuGramRuntime.baseDirectory(accountID: runtimeMigrationAccountID)
                defer { try? FileManager.default.removeItem(at: runtimeMigrationDirectory) }
                var runtimeLegacySettings = AyuSettings()
                runtimeLegacySettings.saveDeletedMessages = false
                runtimeLegacySettings.saveMessagesHistory = false
                let runtimeSettingsURL = runtimeMigrationDirectory.appendingPathComponent("settings.json")
                try JSONEncoder().encode(runtimeLegacySettings).write(to: runtimeSettingsURL, options: .atomic)
                let runtimeMigrationMarker = runtimeMigrationDirectory.appendingPathComponent("deleted-messages-auto-enabled-v2")
                try? FileManager.default.removeItem(at: runtimeMigrationMarker)
                let concurrentStores = NSMutableArray()
                let concurrentStoresLock = NSLock()
                DispatchQueue.concurrentPerform(iterations: 32) { _ in
                    if let candidate = try? AyuGramRuntime.cachedSettingsStore(accountID: runtimeMigrationAccountID) {
                        concurrentStoresLock.lock()
                        concurrentStores.add(candidate)
                        concurrentStoresLock.unlock()
                    }
                }
                let runtimeMigratedStore = concurrentStores.firstObject as? AyuSettingsStore
                var runtimeAllCallsSharedOneStore = concurrentStores.count == 32
                if let runtimeMigratedStore {
                    for index in 0..<concurrentStores.count {
                        guard let entryStore = concurrentStores.object(at: index) as? AyuSettingsStore,
                              entryStore === runtimeMigratedStore else {
                            runtimeAllCallsSharedOneStore = false
                            break
                        }
                    }
                } else {
                    runtimeAllCallsSharedOneStore = false
                }
                let runtimeAutoEnabled = runtimeMigratedStore?.settings.saveDeletedMessages == true
                    && runtimeMigratedStore?.settings.saveMessagesHistory == false
                    && FileManager.default.fileExists(atPath: runtimeMigrationMarker.path)
                let runtimeMarkerRespected: Bool
                if let runtimeMigratedStore {
                    try runtimeMigratedStore.update { $0.saveDeletedMessages = false }
                    runtimeMarkerRespected = !(try AyuGramRuntime.cachedSettingsStore(accountID: runtimeMigrationAccountID)).settings.saveDeletedMessages
                } else {
                    runtimeMarkerRespected = false
                }
                let runtimeMigrationPassed = runtimeAutoEnabled && runtimeMarkerRespected && runtimeAllCallsSharedOneStore
                let explicitFalseURL = FileManager.default.temporaryDirectory
                    .appendingPathComponent("AyuGramLegacySettingsFalse-\(UUID().uuidString).json")
                defer { try? FileManager.default.removeItem(at: explicitFalseURL) }
                let explicitFalseData = try JSONSerialization.data(
                    withJSONObject: ["saveDeletedMessages": false, "saveMessagesHistory": true],
                    options: [.sortedKeys]
                )
                try explicitFalseData.write(to: explicitFalseURL, options: .atomic)
                let explicitFalseStore = try AyuSettingsStore(url: explicitFalseURL)
                let explicitFalsePreserved = !explicitFalseStore.settings.saveDeletedMessages
                    && explicitFalseStore.settings.saveMessagesHistory
                add(
                    "Legacy AyuGram settings migration",
                    migrationPassed && runtimeMigrationPassed && explicitFalsePreserved,
                    migrationPassed && runtimeMigrationPassed && explicitFalsePreserved
                        ? "legacy decoding preserved values; 32 concurrent first accesses shared one auto-enabled store; later OFF was respected"
                        : "legacy settings migration did not preserve the expected values"
                )
            } catch {
                add("Legacy AyuGram settings migration", false, String(describing: error))
            }

            let report = AyuGramSmokeTestReport(version: AyuGramRuntime.version, accountID: 0, startedAt: now, finishedAt: now, items: items)
            let reportURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first?.appendingPathComponent("AyuGram", isDirectory: true).appendingPathComponent("AyuGramSmokeReport.json")
            if let reportURL {
                do {
                    try FileManager.default.createDirectory(at: reportURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                    try JSONEncoder().encode(report).write(to: reportURL, options: .atomic)
                    print("AyuGram standalone smoke report written: \\(reportURL.path)")
                } catch {
                    print("AyuGram standalone smoke report write failed: \\(error)")
                }
            }
        }
"""
if "AyuGram standalone smoke report written" not in s:
    if launch_anchor not in s:
        raise SystemExit("AppDelegate launch anchor not found")
    s = s.replace(launch_anchor, launch_anchor + "\n" + standalone_hook, 1)

s = "\n".join(line.rstrip() for line in s.splitlines()) + "\n"

p.write_text(s, encoding="utf-8")
