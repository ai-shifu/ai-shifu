# Operator Order Management

## Goal

Add a new operator-only global order management page under `运营`, while keeping the existing creator-facing `/admin/orders` page unchanged.

## Scope

- Add a new operator menu entry: `运营 > 订单管理`
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
- coupon / redemption code summary
- updated at
- action

### Detail drawer

Reuse the existing order-detail information structure, but call the new operator detail API.

## Testing

- backend unit tests for operator list/detail behavior and order-source derivation
- frontend tests for menu visibility and the new operator page filter/request behavior
- regenerate i18n key typings after adding translations
