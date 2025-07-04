# Create release
This documentation is intended only for repository maintainers.

We use [release-it](https://github.com/release-it/release-it) for creating new releases.

## Installation
1. Make sure `jq` is installed on your machine
2. Install `release-it` by running `npm install -g release-it` or `brew install release-it`.

## Create a new release
1. Run `release-it`. For pre-releases run `release-it --preRelease=beta` (other possible `preRelease` values are `alpha` or `rc`).
2. Pick whether you want to create a major, minor or patch release. See [semver.org](https://semver.org/) for details.
3. Prepare your release notes. Use the [template](./release-notes-template.md) and remove empty blocks.
4. Follow the wizard.
5. At the end, the wizard will open a browser to create a GitHub release. Paste your prepared release notes, attach `dist/wiser_by_feller.zip` and create the release. You can also configure an [access token](https://github.com/release-it/release-it/blob/main/docs/github-releases.md#automated) to automate this process, but don't forget to replace the release notes.
