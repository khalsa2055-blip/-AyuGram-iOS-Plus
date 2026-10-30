// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "PrivateInviteLinkInspector",
    platforms: [.iOS(.v15)],
    products: [
        .library(name: "PrivateInviteLinkInspector", targets: ["PrivateInviteLinkInspector"])
    ],
    targets: [
        .target(name: "PrivateInviteLinkInspector"),
        .testTarget(name: "PrivateInviteLinkInspectorTests", dependencies: ["PrivateInviteLinkInspector"])
    ]
)
