# AyuGram-iOS-Plus

An experimental iOS Telegram client project exploring a Swiftgram-based foundation and selected AyuGram-inspired features.

## Goals

- Keep the interface close to native Telegram for iOS.
- Investigate which AyuGram-inspired privacy and customization features can be implemented on iOS.
- Build and package an iOS app through GitHub Actions where the upstream project's licensing and build requirements permit it.
- Produce a testable IPA artifact for installation with iLoader.

## Current status

This repository is a project shell only. No upstream source has been imported yet, no features have been ported, and no IPA has been built.

## Planned workflow

1. Verify the upstream iOS source repository, its license, build instructions, and current compatibility.
2. Import or fork the appropriate source and preserve required license notices.
3. Set up a reproducible GitHub Actions build based on the upstream project's documented process.
4. Add and test features incrementally; do not mark a feature complete until it has been verified.
5. Publish build artifacts only after a successful build.

## Important

- This is an unofficial community project and is not affiliated with Telegram, Swiftgram, or AyuGram.
- A successful CI build does not by itself guarantee that an IPA can be installed or will run on every iPhone.
- Signing and installation depend on the user's Apple account, provisioning, and available app IDs.
