# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0]

- First release: `rate_limit` decorator, `RateLimiter` object, and `RateLimitExceeded`.
- Sliding-window algorithm, thread-safe, zero dependencies.
- Block-or-raise behaviour, with injectable clock and sleep for tests.
