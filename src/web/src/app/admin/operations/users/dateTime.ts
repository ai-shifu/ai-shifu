// Operator pages follow the shared admin datetime contract. Naive aliases are
// kept only for legacy tests/callers and should not be used for new timestamps.
export {
  formatAdminNaiveDateTime as formatOperatorNaiveDateTime,
  formatAdminUtcDateTime as formatOperatorUtcDateTime,
  parseAdminNaiveDateTime as parseOperatorNaiveDateTime,
  parseAdminUtcDateTime as parseOperatorUtcDateTime,
} from '@/app/admin/lib/dateTime';
