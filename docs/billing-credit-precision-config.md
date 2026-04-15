# Billing Credit Precision Config Design

## Context

Billing credit values are currently inconsistent across layers:

- backend settlement rounds usage charges to a fixed `DECIMAL(20,10)` helper
- backend serializers emit raw decimal values without a shared display precision
- frontend credit formatting always renders `7` fractional digits

This makes it possible for a stored usage charge, a reported usage charge, and
the rendered value in Cook Web to diverge.

## Goal

Introduce one system-level billing config that defines credit precision and use
it as the single source of truth for:

- all credit display values returned by backend billing APIs
- all frontend credit formatting
- usage credit consumption rounding before persistence

The result must keep displayed credit values consistent with settled and
reported values.

## Non-Goals

- No schema change to `DECIMAL(20,10)` credit columns.
- No retroactive data migration of historical credit rows.
- No change to usage rate lookup, bucket priority, or ledger/report query shape.

## Config Contract

### Key

- system config key: `BILLING_CREDIT_PRECISION`
- semantic: number of fractional digits for credit values
- default: `2`
- valid range: `0..10`

### Runtime Contract

`GET /api/runtime-config` must expose the resolved precision so Cook Web can
format credits with the same rule as backend settlement and serialization.

## Rounding Rules

### Canonical Rule

- use decimal quantization with `ROUND_HALF_UP`
- derive the quantizer from the configured precision
- for example:
  - precision `0` => quantizer `1`
  - precision `2` => quantizer `0.01`

### Settlement Rule

- usage metric `consumed_credits` must be quantized before writing ledger rows
- bucket-level consumed amounts written into usage metadata must use the same
  quantized value
- aggregated daily usage metrics derived from settled usage must reuse the same
  precision

### Serialization Rule

- billing product `credit_amount`
- wallet snapshot credits
- wallet bucket credits
- ledger `amount` / `balance_after`
- ledger metadata credit amounts
- daily usage report `consumed_credits`
- daily ledger report `amount`
- trial credit amount

All of the above must be serialized with the configured precision so API
responses match settlement math and frontend display.

## Compatibility Notes

- historical rows may still physically store more than the configured precision
  because column scale remains `10`
- backend responses must quantize those historical values on read
- new usage settlement writes must quantize before persistence so new rows are
  natively aligned

## Test Plan

- backend config/runtime-config tests for the new key and DTO field
- backend settlement tests that verify rounding occurs before ledger persistence
- backend serializer/report tests that verify configured precision is applied
- frontend billing formatting tests that verify runtime precision replaces the
  old hardcoded `7`
