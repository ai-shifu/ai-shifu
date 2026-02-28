# Analytics Events Documentation

This directory contains documentation for analytics events tracked in the AI-Shifu platform.

## Overview

AI-Shifu uses [Umami](https://umami.is/), a privacy-friendly, open-source web analytics tool, to track user interactions and understand usage patterns. All tracking is designed to be:

- **Privacy-focused**: No personally identifiable information (PII) is collected
- **Non-blocking**: Tracking errors don't affect user experience
- **Optional**: Only tracks when analytics scripts are loaded
- **GDPR-compliant**: Follows privacy regulations

## Event Categories

### Creator Events
Events related to content creation and management:

- **[creator_shifu_setting_save](./creator_shifu_setting_save.md)** - When a creator saves Shifu configuration settings
- `creator_shifu_preview_click` - When a creator previews their Shifu
- `creator_lesson_preview_click` - When a creator previews a lesson
- `creator_publish_click` - When a creator initiates content publish
- `creator_publish_confirm` - When a creator confirms publish action
- `creator_shifu_create_success` - When a new Shifu is created successfully
- `creator_shifu_create_click` - When a creator starts creating a Shifu

### Learner Events
Events related to the learning experience:

- `learner_login_success` - When a learner successfully logs in
- `learner_lesson_start` - When a learner starts a lesson
- `trial_progress` - Progress through trial lessons

### Navigation Events
Events related to UI navigation:

- `nav_bottom_beian` - Bottom navigation beian link click
- `nav_bottom_skin` - Theme/skin switcher interaction
- `nav_bottom_setting` - Settings navigation
- `nav_top_logo` - Top logo click
- `nav_top_expand` - Navigation expand action
- `nav_top_collapse` - Navigation collapse action
- `nav_section_switch` - Section navigation switch

### Other Events
- `visit` - Page visit tracking
- `pop_pay` - Payment modal display
- `pop_login` - Login modal display
- `pay_succeed` - Successful payment
- `reset_chapter` - Chapter reset action
- `reset_chapter_confirm` - Chapter reset confirmation
- `user_menu` - User menu interaction
- `user_menu_basic_info` - Basic info menu access
- `user_menu_personalized` - Personalized settings access

## Implementation

### Core Files

- **Tracking Hook**: `/src/cook-web/src/c-common/hooks/useTracking.ts`
- **Tracking Utility**: `/src/cook-web/src/c-common/tools/tracking.ts`
- **Analytics Loader**: `/src/cook-web/src/components/analytics/UmamiLoader.tsx`

### Usage Example

```typescript
import { useTracking } from '@/c-common/hooks/useTracking';

function MyComponent() {
  const { trackEvent } = useTracking();
  
  const handleSave = async () => {
    // Your save logic
    await saveData();
    
    // Track the event
    trackEvent('my_event_name', {
      // Event data
      field1: 'value1',
      field2: 'value2',
    });
  };
}
```

## Event Data Structure

All events automatically include the following metadata:

| Field | Description |
|-------|-------------|
| `user_type` | User status: 'guest', 'user', or 'member' |
| `user_id` | Unique user identifier (0 for guests) |
| `device` | Device type: 'H5' (mobile) or 'Web' (desktop) |
| `timeStamp` | Local timestamp when event was triggered |

## Configuration

Analytics is configured through environment variables:

```bash
UMAMI_SCRIPT_SRC=https://analytics.example.com/script.js
UMAMI_WEBSITE_ID=your-website-id
```

## Privacy & Compliance

- User identification uses internal system IDs only
- No personal information (email, name, etc.) is tracked
- Users can be identified by user_id for session continuity
- All tracking can be disabled by not loading the Umami script
- Compliant with GDPR and other privacy regulations

## Adding New Events

To add a new tracked event:

1. Add the event name to `EVENT_NAMES` constant in `/src/cook-web/src/c-common/tools/tracking.ts` (optional, for commonly reused events)
2. Use the `trackEvent` function from `useTracking` hook
3. Document the event in this directory
4. Include relevant event data in the payload

Example:
```typescript
trackEvent('my_new_event', {
  custom_field: 'value',
  // Any relevant data
});
```

## Best Practices

1. **Event Naming**: Use snake_case, be descriptive and specific
2. **Event Data**: Only include necessary, non-sensitive data
3. **Error Handling**: Tracking should never block user actions
4. **Documentation**: Document new events with purpose and data structure
5. **Privacy**: Never track PII or sensitive user data
6. **Testing**: Verify events fire correctly in development

## Resources

- [Umami Documentation](https://umami.is/docs)
- [Umami Event Tracking API](https://umami.is/docs/track-events)
- [GDPR Compliance Guide](https://umami.is/docs/gdpr)
