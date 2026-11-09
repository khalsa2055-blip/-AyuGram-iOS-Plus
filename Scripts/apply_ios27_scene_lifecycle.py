#!/usr/bin/env python3
"""Backport Swiftgram's iOS 27 UIKit scene lifecycle onto the pinned Telegram baseline.

This is intentionally a narrow source migration. It does not replace the Telegram
baseline or touch AyuGram feature implementations.
"""
from pathlib import Path

ROOT = Path(".")
BUILD = ROOT / "Telegram" / "BUILD"
APP_DELEGATE = ROOT / "submodules" / "TelegramUI" / "Sources" / "AppDelegate.swift"
SCENE_DELEGATE = ROOT / "submodules" / "TelegramUI" / "Sources" / "SceneDelegate.swift"
NATIVE_WINDOW = ROOT / "submodules" / "Display" / "Source" / "NativeWindowHostView.swift"
WINDOW_CONTENT = ROOT / "submodules" / "Display" / "Source" / "WindowContent.swift"
LEGACY_CONTROLLER = ROOT / "submodules" / "LegacyUI" / "Sources" / "LegacyController.swift"

def read(path: Path) -> str:
    if not path.is_file():
        raise SystemExit("Required source file is missing: " + str(path))
    return path.read_text(encoding="utf-8")

def write(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one source match, found {count}")
    return source.replace(old, new, 1)

# 1) Advertise a single application-role scene. The app constructs its window in
#    didFinishLaunching and attaches that same window in SceneDelegate.
scene_manifest = """    <key>UIApplicationSceneManifest</key>
    <dict>
        <key>UIApplicationSupportsMultipleScenes</key>
        <false/>
        <key>UISceneConfigurations</key>
        <dict>
            <key>UIWindowSceneSessionRoleApplication</key>
            <array>
                <dict>
                    <key>UISceneConfigurationName</key>
                    <string>Default Configuration</string>
                    <key>UISceneDelegateClassName</key>
                    <string>SceneDelegate</string>
                </dict>
            </array>
        </dict>
    </dict>
"""
source = read(BUILD)
manifest_count = source.count("<key>UIApplicationSceneManifest</key>")
if manifest_count == 0:
    source = replace_once(source, '    <key>UIBackgroundModes</key>', scene_manifest + '    <key>UIBackgroundModes</key>', "app scene manifest")
elif manifest_count != 1 or "<string>SceneDelegate</string>" not in source:
    raise SystemExit("Existing UIApplicationSceneManifest is unexpected; refusing to overwrite it")
write(BUILD, source)

# 2) Stop the legacy root controller from overwriting UIKit's SceneDelegate.
source = read(NATIVE_WINDOW)
legacy_conformance = "private final class WindowRootViewController: UIViewController, UIWindowSceneDelegate"
if legacy_conformance in source:
    source = replace_once(
        source,
        legacy_conformance,
        "private final class WindowRootViewController: UIViewController",
        "remove accidental UIWindowSceneDelegate conformance from root controller",
    )
elif "private final class WindowRootViewController: UIViewController" not in source:
    raise SystemExit("WindowRootViewController declaration is missing")
delegate_assignment = """        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene {
            windowScene.delegate = self
        }
"""
if delegate_assignment in source:
    source = replace_once(source, delegate_assignment, "", "remove root-controller scene delegate replacement")
elif "windowScene.delegate = self" in source:
    raise SystemExit("Unexpected scene delegate assignment remains in NativeWindowHostView")
preferred_windowing = """    @available(iOS 26.0, *)
    func preferredWindowingControlStyle(for windowScene: UIWindowScene) -> UIWindowScene.WindowingControlStyle {
        return .minimal
    }
    
"""
if preferred_windowing in source:
    source = replace_once(source, preferred_windowing, "", "move preferred windowing style to SceneDelegate")
elif "func preferredWindowingControlStyle(for windowScene" in source:
    raise SystemExit("Unexpected preferredWindowingControlStyle implementation remains")
write(NATIVE_WINDOW, source)

# 3) Window1 is created before a scene is attached. Refresh device metrics after
#    UIKit supplies the scene/status-bar height, before first visible layout.
source = read(WINDOW_CONTENT)
metrics_method = """    /// Re-derives device metrics after the app window has been attached to its scene.
    /// Window1 is initialized before the scene exists, when the status bar height is 0.
    public func updateDeviceMetrics() {
        self.deviceMetrics = DeviceMetrics(
            screenSize: UIScreen.main.bounds.size,
            scale: UIScreen.main.scale,
            statusBarHeight: self.statusBarHost?.statusBarFrame.height ?? 0.0,
            onScreenNavigationHeight: self.hostView.onScreenNavigationHeight
        )
    }

"""
if "public func updateDeviceMetrics()" not in source:
    source = replace_once(source, "    private var forceBadgeHidden = true", metrics_method + "    private var forceBadgeHidden = true", "add post-scene device metric refresh")
elif source.count("public func updateDeviceMetrics()") != 1:
    raise SystemExit("Unexpected duplicate updateDeviceMetrics method")
write(WINDOW_CONTENT, source)

# 4) The scene is absent until UIKit connects it. This legacy status-bar query
#    must therefore be optional while didFinishLaunching is still running.
source = read(LEGACY_CONTROLLER)
force_unwrap = "window!?.windowScene!.statusBarManager?.statusBarFrame"
safe_lookup = "window!?.windowScene?.statusBarManager?.statusBarFrame"
if force_unwrap in source:
    source = replace_once(source, force_unwrap, safe_lookup, "make LegacyController status-bar lookup safe before scene attachment")
elif safe_lookup not in source:
    raise SystemExit("LegacyController status-bar lookup is in an unexpected state")
write(LEGACY_CONTROLLER, source)

# 5) Add a thin SceneDelegate. Only the primary application scene forwards
#    app-wide lifecycle/URL/shortcut callbacks; external display scenes are ignored.
scene_delegate_source = """import UIKit

@objc(SceneDelegate) final class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    private var isPrimaryScene = false

    private var appDelegate: AppDelegate? {
        return UIApplication.shared.delegate as? AppDelegate
    }

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard session.role == .windowApplication, let windowScene = scene as? UIWindowScene else {
            return
        }
        guard let appDelegate = self.appDelegate else {
            return
        }
        self.isPrimaryScene = true
        appDelegate.attach(scene: windowScene, connectionOptions: connectionOptions)
        self.window = appDelegate.window
    }

    func sceneDidBecomeActive(_ scene: UIScene) {
        guard self.isPrimaryScene else { return }
        self.appDelegate?.handleDidBecomeActive()
    }

    func sceneWillResignActive(_ scene: UIScene) {
        guard self.isPrimaryScene else { return }
        self.appDelegate?.handleWillResignActive()
    }

    func sceneDidEnterBackground(_ scene: UIScene) {
        guard self.isPrimaryScene else { return }
        self.appDelegate?.handleDidEnterBackground()
    }

    func sceneWillEnterForeground(_ scene: UIScene) {
        guard self.isPrimaryScene else { return }
        self.appDelegate?.handleWillEnterForeground()
    }

    func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
        guard self.isPrimaryScene, let appDelegate = self.appDelegate else { return }
        for context in URLContexts {
            appDelegate.handleOpenURL(context.url)
        }
    }

    func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
        guard self.isPrimaryScene else { return }
        self.appDelegate?.handleUserActivity(userActivity)
    }

    func windowScene(_ windowScene: UIWindowScene, performActionFor shortcutItem: UIApplicationShortcutItem, completionHandler: @escaping (Bool) -> Void) {
        guard self.isPrimaryScene, let appDelegate = self.appDelegate else {
            completionHandler(false)
            return
        }
        appDelegate.handleShortcutItem(shortcutItem, completionHandler: completionHandler)
    }

    @available(iOS 26.0, *)
    func preferredWindowingControlStyle(for windowScene: UIWindowScene) -> UIWindowScene.WindowingControlStyle {
        return .minimal
    }
}
"""
if SCENE_DELEGATE.exists():
    if read(SCENE_DELEGATE) != scene_delegate_source:
        raise SystemExit("A different SceneDelegate.swift already exists; refusing to overwrite it")
else:
    SCENE_DELEGATE.parent.mkdir(parents=True, exist_ok=True)
    write(SCENE_DELEGATE, scene_delegate_source)

# 6) Migrate the AppDelegate's window/lifecycle entry points to the new delegate.
source = read(APP_DELEGATE)
source = replace_once(
    source,
    "    private weak var scene: UIWindowScene?",
    "    weak var scene: UIWindowScene?",
    "expose status-bar scene to AppDelegate.attach",
)

# iOS 27 moved the remote keyboard into a scene-owned keyboard scene.
# The pre-iOS-27 no-argument private getter calls
# UIRemoteKeyboardWindow.remoteKeyboardWindowForScreen(create:), which traps
# on iOS 27 during Window1's first layout. Use the scene-aware UIKit getter.
keyboard_window_legacy = """    var keyboardWindow: UIWindow? {
        if #available(iOS 16.0, *) {
            return UIApplication.shared.internalGetKeyboard()
        }

        for window in UIApplication.shared.windows {
            if isKeyboardWindow(window: window) {
                return window
            }
        }
        return nil
    }
"""
keyboard_window_scene_aware = """    var keyboardWindow: UIWindow? {
        if #available(iOS 27.0, *) {
            return UIApplication.shared.internalGetKeyboard(for: self.scene)
        }
        if #available(iOS 16.0, *) {
            return UIApplication.shared.internalGetKeyboard()
        }

        for window in UIApplication.shared.windows {
            if isKeyboardWindow(window: window) {
                return window
            }
        }
        return nil
    }
"""
if keyboard_window_scene_aware in source:
    pass
else:
    # The pinned Swiftgram source contains whitespace-only blank lines inside
    # this computed property. Match the property structurally instead of
    # requiring byte-for-byte blank-line formatting.
    import re
    pattern = re.compile(
        r"(?ms)^    var keyboardWindow: UIWindow\? \{\n.*?^    \}\n(?=[ \t]*\n[ \t]*var keyboardView:)"
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise SystemExit(
            "ApplicationStatusBarHost.keyboardWindow: expected one property block, found "
            + str(len(matches))
        )
    current = matches[0].group(0)
    if current.count("return UIApplication.shared.internalGetKeyboard()") != 1:
        raise SystemExit(
            "ApplicationStatusBarHost.keyboardWindow has an unexpected getter; refusing migration"
        )
    source = source[:matches[0].start()] + keyboard_window_scene_aware.rstrip("\n") + "\n" + source[matches[0].end():]
source = replace_once(
    source,
    "    var mainWindow: Window1!\n",
    "    var mainWindow: Window1!\n    private var statusBarHost: ApplicationStatusBarHost?\n",
    "retain status-bar host for later scene attachment",
)
source = replace_once(
    source,
    "        let statusBarHost = ApplicationStatusBarHost(scene: window.windowScene)\n        self.mainWindow = Window1(hostView: hostView, statusBarHost: statusBarHost)",
    "        let statusBarHost = ApplicationStatusBarHost(scene: window.windowScene)\n        self.statusBarHost = statusBarHost\n        self.mainWindow = Window1(hostView: hostView, statusBarHost: statusBarHost)",
    "retain ApplicationStatusBarHost instance",
)
lines = source.splitlines()
visibility_matches = []
for index, line in enumerate(lines):
    if line.strip() != "self.window?.makeKeyAndVisible()":
        continue
    before = "\n".join(lines[max(0, index - 24):index])
    after = "\n".join(lines[index + 1:min(len(lines), index + 24)])
    # Match the launch-time call by nearby setup, not one exact line layout.
    if "GlobalExperimentalSettings.enableFeed = false" in before and "hasActiveCalls" in after:
        visibility_matches.append(index)
if len(visibility_matches) != 1:
    raise SystemExit("defer showing main window until its scene is attached: expected one launch-time visibility call, found " + str(len(visibility_matches)))
del lines[visibility_matches[0]]
source = "\n".join(lines) + "\n"
source = replace_once(
    source,
    '            window.makeKeyAndVisible()\n\n            NSLog("[DeleteAccount] starting',
    '            NSLog("[DeleteAccount] starting',
    "remove pre-scene visibility from account-delete harness",
)

# UIApplicationDelegate launchOptions URL handling is replaced by
# UIScene.ConnectionOptions in attach(scene:connectionOptions:).
launch_url_start = "        if let url = launchOptions?[.url] {\n"
launch_url_end = "\n        if application.applicationState == .active {"
start = source.find(launch_url_start)
if start < 0:
    raise SystemExit("Could not find didFinishLaunching URL block")
end = source.find(launch_url_end, start)
if end < 0:
    raise SystemExit("Could not find end of didFinishLaunching URL block")
source = source[:start] + source[end + 1:]

# Rename app-wide lifecycle handlers so SceneDelegate, not UIApplicationDelegate,
# forwards the primary scene's state. Keep all existing method bodies intact.
lifecycle_renames = [
    ("    func applicationWillResignActive(_ application: UIApplication) {", "    func handleWillResignActive() {"),
    ("    func applicationDidEnterBackground(_ application: UIApplication) {", "    func handleDidEnterBackground() {"),
    ("    func applicationWillEnterForeground(_ application: UIApplication) {", "    func handleWillEnterForeground() {"),
    ("    func applicationDidBecomeActive(_ application: UIApplication) {", "    func handleDidBecomeActive() {"),
]
for old, new in lifecycle_renames:
    source = replace_once(source, old, new, "rename " + old.strip())
source = replace_once(
    source,
    "taskIdHolder.taskId = application.beginBackgroundTask(withName: \"lock\", expirationHandler:",
    "taskIdHolder.taskId = UIApplication.shared.beginBackgroundTask(withName: \"lock\", expirationHandler:",
    "use UIApplication.shared for background task after lifecycle method rename",
)

# URL open callbacks move to SceneDelegate. Retain the existing URL dedupe.
url_start_marker = "    func application(_ application: UIApplication, open url: URL, sourceApplication: String?) -> Bool {"
url_end_marker = "    private func openUrl(url: URL) {"
start = source.find(url_start_marker)
end = source.find(url_end_marker, start)
if start < 0 or end < 0:
    raise SystemExit("Could not locate the complete UIApplicationDelegate URL-open callback block")
handle_open_url = """    func handleOpenURL(_ url: URL) {
        guard self.openUrlInProgress != url else {
            return
        }
        self.openUrl(url: url)
    }

"""
source = source[:start] + handle_open_url + source[end:]

source = replace_once(
    source,
    "    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {",
    "    @discardableResult func handleUserActivity(_ userActivity: NSUserActivity) -> Bool {",
    "move user activity handling to SceneDelegate",
)
source = replace_once(
    source,
    "    @available(iOS 9.0, *)\n    func application(_ application: UIApplication, performActionFor shortcutItem: UIApplicationShortcutItem, completionHandler: @escaping (Bool) -> Void) {",
    "    func handleShortcutItem(_ shortcutItem: UIApplicationShortcutItem, completionHandler: @escaping (Bool) -> Void) {",
    "move shortcut handling to SceneDelegate",
)

# Install the app-role scene configuration and attach the pre-created window.
attach_methods = """    func application(_ application: UIApplication, configurationForConnecting connectingSceneSession: UISceneSession, options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let configuration = UISceneConfiguration(name: "Default Configuration", sessionRole: connectingSceneSession.role)
        if connectingSceneSession.role == .windowApplication {
            configuration.delegateClass = SceneDelegate.self
        }
        return configuration
    }

    func attach(scene: UIWindowScene, connectionOptions: UIScene.ConnectionOptions) {
        self.statusBarHost?.scene = scene
        self.window?.windowScene = scene
        self.mainWindow?.updateDeviceMetrics()
        self.window?.makeKeyAndVisible()

        for context in connectionOptions.urlContexts {
            let url = context.url
            if let buildConfig = self.buildConfig, url.scheme == "tg" || url.scheme == buildConfig.appSpecificUrlScheme {
                self.openUrlWhenReady(url: sgActionRequestHandlerSanitizer(url), external: true)
            } else {
                self.handleOpenURL(url)
            }
        }

        for userActivity in connectionOptions.userActivities {
            self.handleUserActivity(userActivity)
        }

        if let shortcutItem = connectionOptions.shortcutItem {
            self.handleShortcutItem(shortcutItem, completionHandler: { _ in })
        }
    }

"""
source = replace_once(
    source,
    "    private var backgroundSessionSourceDataDisposables:",
    attach_methods + "    private var backgroundSessionSourceDataDisposables:",
    "add application-scene connection and window attachment methods",
)
write(APP_DELEGATE, source)

# 7) Assert all critical lifecycle hooks are wired and the old clobbering
#    behavior is gone. The second makeKeyAndVisible occurrence is only the
#    early hard-reset callback; the other is now inside attach(scene:).
build_text = read(BUILD)
app_text = read(APP_DELEGATE)
native_text = read(NATIVE_WINDOW)
scene_text = read(SCENE_DELEGATE)
assert build_text.count("<key>UIApplicationSceneManifest</key>") == 1
assert "<string>SceneDelegate</string>" in build_text
assert "configurationForConnecting connectingSceneSession" in app_text
assert "func attach(scene: UIWindowScene, connectionOptions: UIScene.ConnectionOptions)" in app_text
assert "self.window?.windowScene = scene" in app_text
assert "func handleDidBecomeActive()" in app_text
assert "func handleWillResignActive()" in app_text
assert "func handleDidEnterBackground()" in app_text
assert "func handleWillEnterForeground()" in app_text
assert "func handleOpenURL(_ url: URL)" in app_text
assert "handleUserActivity(_ userActivity: NSUserActivity)" in app_text
assert "handleShortcutItem(_ shortcutItem: UIApplicationShortcutItem" in app_text
scene_keyboard_lookup = app_text.find("return UIApplication.shared.internalGetKeyboard(for: self.scene)")
legacy_keyboard_lookup = app_text.find("return UIApplication.shared.internalGetKeyboard()")
assert scene_keyboard_lookup >= 0 and legacy_keyboard_lookup > scene_keyboard_lookup, "iOS 27 must use the scene-aware keyboard lookup before the legacy getter"
assert "windowScene.delegate = self" not in native_text
assert "UIWindowSceneDelegate" not in native_text
assert "launchOptions?[.url]" not in app_text
assert "window!?.windowScene!.statusBarManager" not in read(LEGACY_CONTROLLER)
assert "public func updateDeviceMetrics()" in read(WINDOW_CONTENT)
assert app_text.count("self.window?.makeKeyAndVisible()") == 2
assert "SceneDelegate" in scene_text and "isPrimaryScene" in scene_text
assert (ROOT / "submodules" / "TelegramUI" / "BUILD").is_file()
assert '\"Sources/**/*.swift\"' in read(ROOT / "submodules" / "TelegramUI" / "BUILD")

print("PASS: iOS 27 single-scene lifecycle manifest + SceneDelegate.")
print("PASS: existing Telegram window attached to the primary application scene.")
print("PASS: lifecycle, URLs, user activities and shortcuts forwarded to AppDelegate.")
print("PASS: SceneDelegate is not overwritten by NativeWindowHostView.")
print("PASS: AyuGram feature implementations were not modified by this migration script.")
