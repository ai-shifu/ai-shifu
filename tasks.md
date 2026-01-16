# Order Feature Plan

## Current State
- Admin UI uses `src/cook-web/src/app/admin/layout.tsx` with a single Shifu menu item and `src/cook-web/src/app/admin/page.tsx` for the shifu list.
- There is no shared table component under `src/cook-web/src/components/ui`.
- Shifu permissions are checked via `shifu_permission_verification` in `src/api/flaskr/service/shifu/funcs.py`, while `get_shifu_draft_list` in `src/api/flaskr/service/shifu/shifu_draft_funcs.py` manually unions creator + shared shifus without a reusable permission abstraction.
- Order backend supports user purchase flows in `src/api/flaskr/route/order.py` and has models (`Order`, `ActiveUserRecord`, `CouponUsage`, `StripeOrder`, `PingxxOrder`), but no admin list/detail endpoints.
- i18n already includes `server.order.*` status strings in `src/i18n/*/modules/backend/order.json`; no admin order UI namespace exists.

## Plan
1. Shared shifu-permission abstraction (backend)
   - Add a helper (e.g., `service/shifu/permissions.py`) that returns authorized shifu IDs and permission sets for a user (creator = full permissions).
   - Refactor `get_shifu_draft_list` to use this helper so it becomes the single source of truth.

2. Admin order list + detail services (backend)
   - Create an order admin service (e.g., `service/order/admin.py`) with:
     - `list_orders(...)` filtered by authorized shifu IDs from the shared helper.
     - `get_order_detail(order_bid, ...)` to aggregate base order, active records, coupon usage, and payment details.
   - Enforce the "no joins" rule: query orders first, then fetch related data via IN queries (including user phone lookup by `user_bid`).
   - Return status codes/keys (not hardcoded labels) so the frontend can localize via i18n.

3. Admin order endpoints (backend routing)
   - Expose `/api/order/admin/orders` (list) and `/api/order/admin/orders/{order_bid}` (detail) in `src/api/flaskr/route/order.py`.
   - Require creator access similar to `ShifuTokenValidation(..., is_creator=True)`.
   - Add DTOs to swagger if needed.

4. Global table component (frontend)
   - Add `src/cook-web/src/components/ui/Table.tsx` with composable subcomponents (Table, TableHeader, TableRow, TableCell, EmptyState).
   - Match existing admin theme (rounded borders, subtle separators, typography consistent with `Card`/`Button` styles).

5. Admin order list page (frontend)
   - Add `src/cook-web/src/app/admin/orders/page.tsx` and new API entries in `src/cook-web/src/api/api.ts`.
   - Use the shared table component for pagination, search, and status display.
   - Ensure the backend already filters to authorized shifu orders; frontend can optionally apply local shifu filters.

6. Order detail drawer (frontend)
   - Create a right-side sheet component (e.g., `components/order/OrderDetailSheet.tsx`) using `Sheet`.
   - Show activity, coupon, and payment sections with localized status fields and formatted amounts/timestamps.

7. Navigation + i18n
   - Add an “Order” item to the admin sidebar in `src/cook-web/src/app/admin/layout.tsx`.
   - Add new i18n keys for order list/detail labels and payment statuses in `src/i18n/en-US` and `src/i18n/zh-CN`, and update `src/cook-web/src/types/i18n-keys.d.ts` if required by the build.

8. Validation
   - Add backend unit tests for order list/detail services (especially permission filtering and no-join query behavior).
   - Manual checks: admin navigation, order list loads, detail drawer content, and language switching.
