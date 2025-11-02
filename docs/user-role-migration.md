# User Role Migration Notes

## Schema Changes
- Added `is_creator` column to `user_users` with default `0`, including a covering index for role lookups.
- Dropped the legacy `is_admin` column from `user_info` to prevent stale role data from resurfacing.
- Removed `sys_user_is_admin` and `sys_user_is_creator` records from `user_profile`; role state now lives exclusively in `user_users`.

## Migration Behavior
- Backfills the new `user_users.is_creator` column from the latest `user_profile` creator flags; no legacy `user_info` data is read.
- Cleans up leftover `user_profile` role records after data is copied so repeated deploys remain idempotent.

## Deployment Checklist
1. Run Alembic migration `4d8f8b9a1c2e_move_creator_flag_to_user_users`.
2. Verify creator access paths by spot-checking API responses for known creator accounts (`is_creator` should reflect truthy values).
3. No additional data-seeding steps are required; the migration removes obsolete profile records automatically.
