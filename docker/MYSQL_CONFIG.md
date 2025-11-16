# MySQL Configuration for TIMESTAMP Fields

## Problem

In MySQL 5.7+ with strict mode, `TIMESTAMP` fields must have a default value. The error `Invalid default value for 'updated'` occurs when creating tables with `TIMESTAMP` fields without explicit defaults.

## Solution

We've configured MySQL to use a modified `sql_mode` that removes `NO_ZERO_DATE`, which allows `TIMESTAMP` fields to be created without explicit default values.

## Configuration Applied

All Docker Compose files have been updated with:

```yaml
command: --sql-mode="ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION"
```

This removes `NO_ZERO_DATE` from the default MySQL 8.0 sql_mode, which was causing the issue.

## For Non-Docker MySQL Setup

If you're using MySQL outside of Docker, you can configure it in one of the following ways:

### Option 1: MySQL Configuration File (my.cnf)

Add to `/etc/mysql/my.cnf` or `/etc/my.cnf`:

```ini
[mysqld]
sql_mode = "ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION"
```

Then restart MySQL:
```bash
sudo systemctl restart mysql
```

### Option 2: Session-Level Configuration

For temporary testing, you can set it per session:

```sql
SET SESSION sql_mode = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION';
```

### Option 3: Global Configuration

To set it globally (affects all connections):

```sql
SET GLOBAL sql_mode = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION';
```

## Verification

To verify the current sql_mode:

```sql
SELECT @@sql_mode;
```

You should see that `NO_ZERO_DATE` is not in the list.

## Notes

- This configuration maintains most strict mode benefits while allowing TIMESTAMP fields without explicit defaults
- The removed `NO_ZERO_DATE` mode was the specific cause of the migration error
- After applying this configuration, restart the MySQL container/service and re-run migrations
