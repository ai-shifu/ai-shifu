# Operator Order Management

## Goal

Add a new operator-only global order management page under `Operations`, while keeping the existing creator-facing `/admin/orders` page unchanged.

## Scope

- Add a new operator menu entry: `Operations > Order Management`
- Add a new operator page route: `/admin/operations/orders`
- Add operator-only backend list/detail APIs for global orders
- Support richer operator filters and fields than the legacy creator order page
- Reuse existing shared admin table/pagination/filter components where possible

## Non-goals

- Do not change the existing creator order page behavior or route
- Do not merge creator and operator order pages into one shared large abstraction
- Do not change order persistence schema

## Data coverage

The new operator order page must include all legacy course-order records from the `order_orders` domain, including:

- user-initiated purchase orders
- coupon / redemption-based zero-paid orders
- import-activation orders (`manual`)
- Open API grant orders (`open_api`)
- platform-domain learner orders paid through a teacher-owned Alipay or WeChat
  Pay integration

Custom-domain learner orders are a separate reporting scope. They may still be
stored in `order_orders`, but the default platform-domain operator view should
not silently mix them in once checkout captures domain attribution. Operator
audit/search can expose them through an explicit source filter.

## Independent payment scope

The first order-management upgrade targets the case where a teacher has no
custom domain but has a configured independent payment channel.

These orders are still platform orders because course discovery, checkout, and
authorization happen on the AI-Shifu domain. The platform does not collect the
funds, so order reporting must distinguish:

- `order_surface`: platform domain
- `settlement_owner`: platform or teacher
- `payment_channel`: Ping++, Stripe, Alipay, or WeChat Pay
- `payment_integration_bid`: blank for platform credentials, populated for a
  teacher-owned integration

GMV and order-count metrics may include both platform and teacher-collected
orders. Platform revenue/collections must exclude `settlement_owner=teacher`.

## Backend design

### Routes

Add new operator routes under the existing operator namespace:

- `GET /shifu/admin/operations/orders`
- `GET /shifu/admin/operations/orders/<order_bid>/detail`

### Query behavior

The operator list API is global and must not be limited to the current creator's own courses.

Supported filters:

- `user_keyword`
- `order_bid`
- `shifu_bid`
- `course_name`
- `status`
- `order_source`
- `payment_channel`
- `settlement_owner`
- `payment_integration`: platform credentials or teacher-owned credentials
- `start_time`
- `end_time`

### Derived order source

Return a backend-derived `order_source` + `order_source_key`:

- `import_activation`
- `open_api`
- `coupon_redeem`
- `user_purchase`

Suggested mapping:

- `payment_channel == manual` -> `import_activation`
- `payment_channel == open_api` -> `open_api`
- has coupon usage and `paid_price == 0` -> `coupon_redeem`
- otherwise -> `user_purchase`

### DTO strategy

Extend the existing admin order summary/detail DTO payloads instead of creating a parallel incompatible shape, so the new operator detail drawer can reuse existing display patterns.

Add non-secret payment attribution fields to list and detail DTOs:

- `settlement_owner`
- `settlement_owner_key`
- `is_custom_payment`
- `payment_integration_bid`
- `payment_integration_label` or a masked provider summary when available

Do not return merchant secrets.

## Frontend design

### Route

- `src/cook-web/src/app/admin/operations/orders/page.tsx`

### Layout

Match existing operator pages:

- title
- filter panel
- table shell
- right-side detail drawer

### Filters

- user: BID / mobile / email
- order ID
- course ID
- course name
- status
- order source
- payment channel
- settlement owner: platform collection / teacher collection
- payment credential scope: platform credentials / teacher independent payment
- order created time range

### Table fields

- created at
- order ID
- user
- course
- order source
- status
- amount block (`paid`, `payable`, `discount`)
- payment channel
- settlement owner
- payment credential scope
- coupon / redemption code summary
- updated at
- action

### Metrics

Overview cards should avoid treating teacher-collected orders as platform
collections. Recommended cards:

- total order count
- paid GMV
- platform-collected amount
- teacher-collected amount

Existing paid-count/status metrics can stay unchanged.

## Implementation Plan: Platform Domain + Independent Payment

1. Backend DTO and query preparation:
   - derive `settlement_owner=teacher` when `payment_integration_bid` is present
     on a learner order;
   - derive `settlement_owner=platform` otherwise;
   - add list/detail DTO fields and filters without changing old default query
     behavior.
2. Operator order APIs:
   - extend `GET /shifu/admin/operations/orders` filters with
     `settlement_owner` and payment credential scope;
   - extend overview aggregation to return GMV, platform-collected amount, and
     teacher-collected amount.
3. Teacher order APIs:
   - expose the same non-secret settlement fields on the existing creator order
     list/detail payloads so teachers can identify independent-payment orders.
4. Frontend:
   - add filters and columns to the operator order page;
   - add a lightweight settlement marker to the teacher order menu;
   - update i18n strings and generated key typings.
5. Tests:
   - add backend coverage for platform-domain orders paid by a teacher-owned
     integration;
   - assert operator and creator lists both include the order;
   - assert platform-collected metrics exclude it and teacher-collected metrics
     include it;
   - add focused frontend request/column rendering tests.

### Detail drawer

Reuse the existing order-detail information structure, but call the new operator detail API.

## Testing

- backend unit tests for operator list/detail behavior and order-source derivation
- frontend tests for menu visibility and the new operator page filter/request behavior
- regenerate i18n key typings after adding translations
