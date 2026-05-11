-- Production credit_usage_rates update for LLM learning-production token rates.
-- Generated from a read-only production lookup on 2026-05-11.
-- Scope:
--   usage_type = 1101 (LLM)
--   usage_scene = 1203 (learning production)
--   billing_metric in 7451, 7452, 7453 (input/cache/output tokens)
--   existing rows only; GLM-5.1 is intentionally not included.
-- Execute this file against the production ai-shifu database after taking a DB backup.

START TRANSACTION;

-- Pre-check: confirm these IDs still point to the expected rows before applying.
SELECT
  id,
  rate_bid,
  provider,
  model,
  usage_type,
  usage_scene,
  billing_metric,
  credits_per_unit,
  unit_size,
  effective_from
FROM credit_usage_rates
WHERE id IN (
  33, 36, 39,
  42, 45, 48,
  51, 54, 57,
  60, 63, 66,
  69, 72, 75,
  78, 81, 84,
  87, 90, 93,
  96, 99, 102
)
ORDER BY id;

-- DeepSeek V4 flash: 0.000066667
UPDATE credit_usage_rates
SET credits_per_unit = 0.0000666670,
    unit_size = 1,
    updated_at = NOW()
WHERE id IN (33, 36, 39)
  AND deleted = 0
  AND usage_type = 1101
  AND usage_scene = 1203
  AND billing_metric IN (7451, 7452, 7453);

-- DeepSeek V4 Pro + Doubao 2.0 lite: 0.0002
UPDATE credit_usage_rates
SET credits_per_unit = 0.0002000000,
    unit_size = 1,
    updated_at = NOW()
WHERE id IN (42, 45, 48, 51, 54, 57)
  AND deleted = 0
  AND usage_type = 1101
  AND usage_scene = 1203
  AND billing_metric IN (7451, 7452, 7453);

-- Doubao 2.0 pro: 0.0008
UPDATE credit_usage_rates
SET credits_per_unit = 0.0008000000,
    unit_size = 1,
    updated_at = NOW()
WHERE id IN (60, 63, 66)
  AND deleted = 0
  AND usage_type = 1101
  AND usage_scene = 1203
  AND billing_metric IN (7451, 7452, 7453);

-- Kimi K2.5: 0.000533333
UPDATE credit_usage_rates
SET credits_per_unit = 0.0005333330,
    unit_size = 1,
    updated_at = NOW()
WHERE id IN (69, 72, 75)
  AND deleted = 0
  AND usage_type = 1101
  AND usage_scene = 1203
  AND billing_metric IN (7451, 7452, 7453);

-- MiniMax-M2.5: 0.000333333
UPDATE credit_usage_rates
SET credits_per_unit = 0.0003333330,
    unit_size = 1,
    updated_at = NOW()
WHERE id IN (78, 81, 84)
  AND deleted = 0
  AND usage_type = 1101
  AND usage_scene = 1203
  AND billing_metric IN (7451, 7452, 7453);

-- GLM-5 + test model gemini-3-flash-preview: 0.000733333
UPDATE credit_usage_rates
SET credits_per_unit = 0.0007333330,
    unit_size = 1,
    updated_at = NOW()
WHERE id IN (87, 90, 93, 96, 99, 102)
  AND deleted = 0
  AND usage_type = 1101
  AND usage_scene = 1203
  AND billing_metric IN (7451, 7452, 7453);

-- Post-check: should return the requested target values.
SELECT
  id,
  rate_bid,
  provider,
  model,
  billing_metric,
  credits_per_unit,
  unit_size,
  updated_at
FROM credit_usage_rates
WHERE id IN (
  33, 36, 39,
  42, 45, 48,
  51, 54, 57,
  60, 63, 66,
  69, 72, 75,
  78, 81, 84,
  87, 90, 93,
  96, 99, 102
)
ORDER BY id;

COMMIT;
