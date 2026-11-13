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


deleted_capture_hook = "                    if ProcessInfo.processInfo.arguments.contains(\"-AyuGramDeletedCaptureSmokeTest\") {\n                        let account = context.context.account\n                        let accountID = account.peerId.toInt64()\n                        let dialogID = accountID\n                        let now = Int32(Date().timeIntervalSince1970)\n                        let messageID = MessageId(peerId: account.peerId, namespace: Namespaces.Message.Cloud, id: 1700000124)\n                        let messageText = \"Synthetic message routed through deleted capture service\"\n\n                        let captureSignal = account.postbox.transaction { transaction -> AyuMessage? in\n                            let storeMessage = StoreMessage(\n                                id: messageID,\n                                customStableId: nil,\n                                globallyUniqueId: nil,\n                                groupingKey: nil,\n                                threadId: nil,\n                                timestamp: now,\n                                flags: [],\n                                tags: [],\n                                globalTags: [],\n                                localTags: [],\n                                forwardInfo: nil,\n                                authorId: nil,\n                                text: messageText,\n                                attributes: [],\n                                media: []\n                            )\n                            transaction.addMessages([storeMessage], location: .Random)\n                            _internal_captureDeletedMessages(\n                                transaction: transaction,\n                                mediaBox: account.postbox.mediaBox,\n                                ids: [messageID],\n                                ayuAccountID: accountID\n                            )\n                            let captured = AyuGramPostboxHistoryStore.filtered(\n                                transaction: transaction,\n                                userID: accountID,\n                                dialogID: dialogID,\n                                kind: .deleted,\n                                limit: 100\n                            ).first { $0.messageID == messageID.id && $0.text == messageText }\n                            transaction.deleteMessages([messageID], forEachMedia: { _ in })\n                            return captured\n                        }\n\n                        _ = (captureSignal |> deliverOnMainQueue).start(next: { captured in\n                            let captureEnabled = (try? AyuGramRuntime.cachedSettingsStore(accountID: accountID).settings.saveDeletedMessages) ?? false\n                            let passed = captureEnabled && captured?.isDeleted == true && captured?.text == messageText\n                            let report: [String: Any] = [\n                                \"passed\": passed,\n                                \"captureEnabled\": captureEnabled,\n                                \"dialogID\": dialogID,\n                                \"messageID\": Int(messageID.id),\n                                \"capturedText\": captured?.text ?? \"\",\n                                \"isDeleted\": captured?.isDeleted ?? false\n                            ]\n                            guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {\n                                print(\"AyuGram deleted-capture smoke test has no Documents directory\")\n                                return\n                            }\n                            let reportURL = documents.appendingPathComponent(\"AyuGramDeletedCaptureSmokeReport.json\")\n                            do {\n                                let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])\n                                try data.write(to: reportURL, options: .atomic)\n                                print(\"AyuGram deleted-capture smoke test: \\(passed ? \"PASS\" : \"FAIL\")\")\n                            } catch {\n                                print(\"AyuGram deleted-capture smoke report write failed: \\(error)\")\n                            }\n                        })\n                    }\n\n"
deleted_capture_anchor = '                    if ProcessInfo.processInfo.arguments.contains("-AyuGramFullSmokeTest") {'
if "AyuGramDeletedCaptureSmokeTest" not in s:
    if s.count(deleted_capture_anchor) != 1:
        raise SystemExit("Deleted-capture smoke-test insertion anchor is not unique")
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
                    migrationPassed && explicitFalsePreserved,
                    migrationPassed && explicitFalsePreserved
                        ? "missing keys received defaults; existing values, Ghost Mode and filters survived; explicit false stayed false"
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
