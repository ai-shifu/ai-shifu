---
title: Billing Credit Domain Terminology
status: accepted
owner_surface: backend
last_reviewed: 2026-07-29
canonical: true
---

# Billing Credit Domain Terminology

## Purpose

This document defines the product terms, code mappings, and refactoring
boundaries for the AI-Shifu credit domain. It is the shared reference for the
Billing-R refactoring series and should be read together with
`docs/billing-subscription-design.md` and
`docs/design-docs/billing-subscription-preorder.md`.

The goal is to align product language with the current implementation without
forcing a risky mass rename. Existing code may keep table and class names such
as `CreditWallet`, but new design discussions should use the product terms in
this document and explicitly map them to code entities when needed.

## Product Terms

| Product term | English term | Current code mapping | Notes |
| --- | --- | --- | --- |
| 积分 | Credits | `CreditLedgerEntry.amount`, bucket credit columns, wallet snapshots | The virtual unit teachers buy and consume. Avoid using “分” in new product docs. |
| 积分账户 | Credit Account | `CreditWallet` | Stores account-level available and reserved snapshots. The code name `Wallet` remains for compatibility. |
| 积分桶 | Credit Bucket | `CreditWalletBucket` | Mutable projection for source, validity window, priority, and remaining balances. |
| 账本 | Ledger | `CreditLedgerEntry` | Audit trail for credit changes. Long-term direction is append-only ledger plus explicit grant/allocation state. |
| 积分套餐 | Plan | `BillingProduct.product_type=plan`, subscription orders, subscription buckets | Recurring product for teachers. It grants plan credits per effective cycle. |
| 积分包 | Credit Pack | `BillingProduct.product_type=topup`, topup orders, topup buckets | One-time credit product. Product target: pack credits should remain owned and only require an effective plan to be consumable. Current implementation still aligns topup bucket windows to the active subscription and can expire their available balance at that boundary; track this gap in R3/R5 before relying on the target invariant. |
| 订阅 | Subscription | `BillingSubscription` | Contract between a teacher and a plan. Do not use it as the generic product name. |
| 续订 | Renew | renewal order, renewal event | Continue the same plan for the next cycle. Avoid “续费” in product docs unless the payment action itself is meant. |
| 升级 | Upgrade | `subscription_upgrade` order, preorder absorption path | Higher-tier plan switch. Immediate upgrades merge current remaining plan credits into the new cycle. |
| 降级 | Downgrade | preorder metadata, downgrade effective renewal event | Lower-tier plan that takes effect at the current cycle boundary. |
| 预购 | Pre-order | paid order with preorder metadata | Paid now, effective later. At most one pending preorder per active subscription. |
| 自动续订 | Auto-renew | renewal task/provider renewal settings | System-driven renewal; do not call it “自动续费” in new product docs. |

## Credit Types

| Product term | Current code mapping | Lifecycle rule |
| --- | --- | --- |
| 套餐积分 | `CREDIT_BUCKET_CATEGORY_SUBSCRIPTION` | Bound to the current plan cycle. Unused balance expires at cycle end unless an immediate upgrade merges it into the new cycle. |
| 积分包积分 | `CREDIT_BUCKET_CATEGORY_TOPUP` | Purchased independently. Product target: remains owned by the teacher and consumption requires an active subscription. Current implementation may expire topup buckets because `_resolve_topup_bucket_effective_to()` aligns them to the active subscription period; do not audit current data as if the target invariant is already true. |
| 试用积分 | `CREDIT_BUCKET_CATEGORY_SUBSCRIPTION` for current bootstrap, legacy `CREDIT_BUCKET_CATEGORY_FREE` for older/free records | New creator trial bootstrap currently persists subscription-category buckets. Runtime category normalization collapses legacy free buckets into subscription ordering, while `wallet_bucket_requires_active_subscription()` still treats explicitly free buckets as not requiring an active subscription. |

The runtime consumption order for current normalized categories is:

```text
subscription-like buckets -> topup
```

Legacy free buckets may still bypass the active-subscription requirement, but
category normalization treats them as subscription-like for ordering. New trial
bootstrap records should be audited as subscription-category records unless a
legacy `free` bucket is explicitly present.

Product-facing docs may describe the normal paid-user order as:

```text
套餐积分 -> 积分包积分
```

When legacy free or bootstrap credits are relevant, call out their persisted
category and active-subscription requirement explicitly instead of hiding them
behind the paid-user wording.

## Credit Change Verbs

These verbs should be used consistently in product docs, audit surfaces, and new
backend design notes.

| Verb | Meaning | Current implementation surface | Audit direction |
| --- | --- | --- | --- |
| 充值 | Credits enter the account after purchase or grant. | grant ledger, bucket available/reserved increase, wallet snapshot refresh | Show as a positive change, such as buying a plan or credit pack. |
| 消耗 | Credits are used by a learning, preview, or debug task. | usage settlement, consume ledger, bucket consumed increase | Show as a negative change tied to the usage actor and operation. |
| 过期 | Remaining plan credits expire at cycle end. | expire ledger, bucket available decrease, expired increase | Show as a negative system change. |
| 冻结 | Credit pack credits become unavailable because there is no effective plan. | eligibility/admission projection today; no dedicated frozen mutation yet | Future audit model should make this visible without subtracting owned pack credits. |
| 解冻 | Credit pack credits become usable again after a plan is active. | eligibility/admission projection today; no dedicated unfrozen mutation yet | Future audit model should show restored usability without double-counting credits. |
| 退还 | Credits return after a failed or reversed task. | refund ledger and bucket/wallet adjustment paths | Show as a positive correction tied to the original usage when possible. |
| 合并 | Immediate upgrade carries remaining plan credits into the new plan window. | upgrade transition, bucket realignment, grant/expire handling | Show as a positive/realignment event for upgrade transparency. |

## Current State Sources

The current system expresses one credit fact across several mutable projections:

| Entity | Role today | Refactoring note |
| --- | --- | --- |
| `BillingOrder` | Payment and purchase truth source, including preorder metadata. | Keep as the source for paid evidence and immutable order snapshots. |
| `BillingSubscription` | Current plan contract and cycle window. | Cycle changes should eventually flow through a single transition service. |
| `BillingRenewalEvent` | Scheduled or compensating cycle work. | Terminal states must not be overwritten by ordinary lifecycle sync. |
| `CreditWallet` | Account-level available/reserved snapshot. | Treat as a projection that must match eligible buckets. |
| `CreditWalletBucket` | Mutable balance, validity, source, and priority projection. | Long-term direction is one allocation or cycle per bucket, not pooled reuse. |
| `CreditLedgerEntry` | Ledger and current grant-state carrier. | Long-term direction is append-only ledger plus explicit `CreditGrant`/`CreditAllocation`. |

## Refactoring Boundaries

The Billing-R series should progress in small, independently mergeable PRs.
Each PR must remain safe if the following PR is delayed.

### R0: Terminology And Domain Boundary

- Define product terms and current code mappings.
- Document what should not be renamed yet.
- Document audit expectations for future ledger and allocation work.
- No runtime behavior change.

### R1: Credit Mutation / Grant Transition

- Introduce shared helpers for low-level credit state transitions.
- Return typed results with expected amount, moved amount, completion state, and
  failure reason.
- Start with narrow paths such as reserved grant activation before migrating
  reserve, void, absorb, expire, refund, or consume paths.
- Keep existing business behavior and transaction ownership unchanged unless a
  later PR explicitly changes them.

### R2: Invariant Audit And Diagnostics

- Add a read-only diagnostic model before adding more incident-specific repair
  commands.
- Cover wallet/bucket mismatch, bucket conservation, overdue reserved grants,
  expire projection drift, and subscription-cycle/bucket-window mismatch.
- Evidence-poor cases should be classified for manual review, not auto-repaired.

### R3: Cycle Transition

- Move subscription cycle advancement, due reserved grant activation, old-cycle
  plan credit expiration, topup eligibility alignment, and renewal event status
  handling behind one cycle transition entry point.
- Migrate callers one at a time so renewal and repair do not diverge.

### R4: Transaction And Concurrency Protocol

- Define transaction ownership, lock order, retryable conflicts, and fail-closed
  cases.
- Fold MySQL two-session concurrency tests, deadlock retry, wallet CAS retry,
  and settlement lock behavior into this protocol instead of creating many
  unrelated follow-up PRs.

### R5: Allocation Model And Append-Only Ledger

- Introduce explicit `CreditGrant` or `CreditAllocation` state when the lower
  layers are stable.
- Move grant current state out of ledger metadata.
- Stop cross-order and cross-cycle pooled bucket reuse for new allocations.
- Keep historical pooled buckets readable during migration; do not migrate all
  history in one step.

## Testing Expectations

Use the smallest test set that covers the changed layer, then widen when a PR
changes shared contracts or write paths.

| Change type | Expected verification |
| --- | --- |
| Docs-only R0 change | `python scripts/check_repo_harness.py` and relevant markdown review. |
| Behavior-preserving helper extraction | Targeted billing tests plus full `tests/service/billing/`. |
| Real write-path migration | Targeted business regression for the migrated path, full billing tests, and dry-run if repair candidates may change. |
| Cycle transition changes | Renewal, preorder, upgrade, expiration, campaign bonus, referral renewal, and repair dry-run/apply regression. |
| Data model changes | Migration review, backward-compatible reads, dual-write or backfill plan, and post-merge dry-run/audit. |

## Non-Goals For The Refactoring Series

- Do not rewrite all billing code at once.
- Do not immediately rename every `Wallet` symbol to `Account`.
- Do not introduce full event sourcing as the first step.
- Do not migrate all historical ledger and bucket data in one PR.
- Do not make Redis locks the final source of correctness.
- Do not auto-repair data without sufficient evidence; route ambiguous findings
  to manual review.
