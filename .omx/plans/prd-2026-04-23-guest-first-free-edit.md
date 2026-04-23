# PRD — 2026-04-23 guest first free edit

## Goal
Allow a first-time device to complete one full web editing flow without login.

## Required behavior
- Unauthenticated first-time visitors can upload, run test, confirm, preview/export, and finish one job.
- First-time eligibility is judged from server-visible IP plus client/device tracking material, not IP alone.
- Existing signed-in logic remains unchanged:
  - newly registered users still need invite code activation under the current flow;
  - existing users still redeem coupon/invite codes under the current flow.
- After the one free guest use is consumed, the device should no longer receive another free guest session and should be guided back to the normal login/invite flow.

## Product shape
- Introduce a guest session claim API that accepts a device fingerprint payload and binds it to IP + user-agent derived hashes server-side.
- Persist an opaque guest token client-side and let job APIs accept either a signed-in user or a valid guest token.
- Limit a guest session to a single in-progress job and a single final free completion.

## Non-goals
- Changing registered-user activation / coupon accounting.
- Adding new external dependencies or third-party fingerprinting services.
- Perfect bot/device fraud prevention beyond lightweight local/device/IP heuristics.

## Risks / tradeoffs
- Device fingerprinting is heuristic; false positives/negatives are possible.
- Reusing a single guest job is safer than granting unlimited pre-export attempts, but can feel restrictive if the initial job is abandoned.
- Guest state must not break the existing authenticated flow or dev-local auth-disabled mode.
