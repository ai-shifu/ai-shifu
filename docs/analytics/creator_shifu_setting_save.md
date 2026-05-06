# Creator Shifu Setting Save Event

## Overview

The `creator_shifu_setting_save` event is an analytics tracking event that captures when a content creator saves changes to a Shifu's (AI master/teacher) configuration settings.

## Purpose

This event is used to:
1. **Track user behavior**: Monitor how creators interact with and configure their Shifu settings
2. **Understand usage patterns**: Analyze which settings are most frequently modified
3. **Distinguish save types**: Differentiate between manual saves and auto-saves
4. **Monitor engagement**: Track creator activity and feature usage in the content management system

## Event Tracking System

The event is tracked using **Umami**, a privacy-friendly, open-source web analytics tool. The tracking implementation:
- Uses the `umami.track()` JavaScript API
- Is non-blocking (errors are silently caught to prevent user experience impact)
- Only tracks when Umami script is loaded
- Includes user identification and session data for authenticated users

## When the Event is Triggered

The event is fired in two scenarios:

### 1. Manual Save (save_type: 'manual')
- When the user explicitly closes the Shifu settings dialog
- When the user submits the form by clicking a save button
- Triggered immediately upon user action

### 2. Auto Save (save_type: 'auto')
- When the form has been modified (isDirty = true)
- After a 3-second delay of inactivity
- Provides automatic persistence without explicit user action
- Ensures no data loss for creators actively editing

## Event Data Collected

The event payload includes the following fields:

### Shifu Configuration Data
| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Shifu's description text |
| `shifu_bid` | string | Shifu's business identifier (unique ID) |
| `keywords` | string[] | Array of keywords/tags associated with the Shifu |
| `model` | string | LLM model name (e.g., "gpt-4", "deepseek-chat") |
| `name` | string | Shifu's display name |
| `price` | number | Price for accessing the Shifu (in currency units) |
| `avatar` | string | URL to the Shifu's avatar image |
| `temperature` | number | LLM temperature setting (0-2, controls randomness) |
| `system_prompt` | string | Custom system prompt for the Shifu's personality |

### Tracking Metadata
| Field | Type | Description |
|-------|------|-------------|
| `save_type` | 'auto' \| 'manual' | Type of save operation |
| `user_type` | string | User status: 'guest', 'user', or 'member' |
| `user_id` | number | Unique user identifier |
| `device` | string | Device type: 'H5' (mobile) or 'Web' (desktop) |
| `timeStamp` | string | Local timestamp when event was triggered |

## Code Location

- **Event trigger**: `/src/cook-web/src/components/shifu-setting/ShifuSetting.tsx` (line 251)
- **Tracking hook**: `/src/cook-web/src/c-common/hooks/useTracking.ts`
- **Tracking utility**: `/src/cook-web/src/c-common/tools/tracking.ts`
- **Analytics loader**: `/src/cook-web/src/components/analytics/UmamiLoader.tsx`

## Implementation Details

```typescript
// Event is triggered after successful API save
trackEvent('creator_shifu_setting_save', {
  ...payload,           // All Shifu configuration fields
  save_type: saveType,  // 'auto' or 'manual'
});
```

## Related Events

Other creator-focused tracking events include:
- `creator_shifu_preview_click`: When creator previews their Shifu
- `creator_lesson_preview_click`: When creator previews a lesson
- `creator_publish_click`: When creator initiates publish
- `creator_publish_confirm`: When creator confirms publish
- `creator_shifu_create_success`: When a new Shifu is created
- `creator_shifu_create_click`: When creator starts creating a Shifu

## Privacy Considerations

- No personally identifiable information (PII) beyond user_id is collected
- User identification uses internal system IDs, not email or names
- The system prompt may contain sensitive configuration data but is stored within the authenticated analytics system
- Umami is designed to be privacy-friendly and GDPR-compliant

## Use Cases for Analytics

This event data can be used to:
1. Identify popular LLM models among creators
2. Analyze typical price points for Shifu content
3. Understand temperature setting preferences
4. Monitor auto-save vs manual-save patterns
5. Track creator engagement and activity levels
6. Identify which fields are most frequently modified
7. Detect potential issues (e.g., frequent saves might indicate UI problems)

## Configuration

Umami analytics is configured via environment variables:
- `UMAMI_SCRIPT_SRC`: URL to the Umami tracking script
- `UMAMI_WEBSITE_ID`: Unique website identifier for Umami

These are loaded through the Cook Web frontend environment configuration system.
