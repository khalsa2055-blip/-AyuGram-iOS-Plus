// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MediaEditArchive",
    platforms: [.iOS(.v15), .macOS(.v13)],
    products: [
        .library(name: "MediaEditArchive", targets: ["MediaEditArchive"])
    ],
    targets: [
        .target(name: "MediaEditArchive"),
        .testTarget(name: "MediaEditArchiveTests", dependencies: ["MediaEditArchive"])
    ]
)
