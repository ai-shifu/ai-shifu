-- MySQL sql_mode Configuration Commands
-- ======================================
-- These commands modify the sql_mode to allow TIMESTAMP fields without explicit defaults
-- by removing the NO_ZERO_DATE restriction

-- ============================================
-- Option 1: Session-Level (Current Connection Only)
-- ============================================
-- This only affects the current database connection/session
-- Use this for testing or temporary fixes

SET SESSION sql_mode = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION';

-- ============================================
-- Option 2: Global-Level (All New Connections)
-- ============================================
-- This affects all new connections to the MySQL server
-- Note: This setting will be lost after MySQL restart unless saved to config file

SET GLOBAL sql_mode = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION';

-- ============================================
-- Option 3: Check Current sql_mode
-- ============================================
-- Verify the current sql_mode setting

SELECT @@SESSION.sql_mode;  -- Current session
SELECT @@GLOBAL.sql_mode;    -- Global setting

-- ============================================
-- Option 4: Remove Specific Mode (Alternative)
-- ============================================
-- If you want to keep other modes but just remove NO_ZERO_DATE

-- Get current mode
SET @current_mode = @@GLOBAL.sql_mode;

-- Remove NO_ZERO_DATE (if present)
SET @new_mode = REPLACE(@current_mode, 'NO_ZERO_DATE', '');

-- Clean up any double commas
SET @new_mode = REPLACE(@new_mode, ',,', ',');

-- Remove leading/trailing commas
SET @new_mode = TRIM(BOTH ',' FROM @new_mode);

-- Apply the new mode
SET GLOBAL sql_mode = @new_mode;

-- ============================================
-- Quick Fix for Migration (Recommended)
-- ============================================
-- Run these commands before executing migrations:

SET GLOBAL sql_mode = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_AUTO_CREATE_USER,NO_ENGINE_SUBSTITUTION';
SELECT @@GLOBAL.sql_mode;  -- Verify it worked

-- Then run your migration:
-- flask db upgrade
