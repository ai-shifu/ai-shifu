---
name: "AI-Shifu Tracking"
description: "Automates frontend event tracking implementation for AI-Shifu project using Umami analytics"
enabled: true
---

# AI-Shifu Frontend Tracking Skill

This skill helps you implement event tracking (打点/埋点) in the AI-Shifu frontend codebase following established patterns and conventions.

## Overview

AI-Shifu uses **Umami** as the analytics platform with a layered architecture:
- **Tool Layer**: `src/cook-web/src/c-common/tools/tracking.ts` - Core tracking functions
- **Hook Layer**: `src/cook-web/src/c-common/hooks/useTracking.ts` - React integration
- **Component Layer**: Individual components call `trackEvent()`

## When to Use This Skill

Use this skill when you need to:
1. Add new tracking events to components
2. Create new event name constants
3. Understand existing tracking patterns
4. Review tracking implementation for completeness

---

## Implemented Events Registry

> **IMPORTANT**: This section is the authoritative list of all tracking events in the codebase.
> Claude MUST update this section whenever adding new tracking events.

### EVENT_NAMES Constants (tracking.ts)

| Constant | Event Value | Description | Trigger Location |
|----------|-------------|-------------|------------------|
| `VISIT` | `visit` | Page visit | TrackingVisit component |
| `TRIAL_PROGRESS` | `trial_progress` | Trial lesson progress | useChatLogicHook (SSE BREAK) |
| `BLOCK_VIEW` | `learner_block_view` | Module/block view for all lesson types | useChatLogicHook (SSE BREAK) |
| `POP_PAY` | `pop_pay` | Payment modal opened | useChatLogicHook |
| `POP_LOGIN` | `pop_login` | Login modal opened | MainMenuModal |
| `PAY_SUCCEED` | `pay_succeed` | Payment successful | (defined but not implemented) |
| `NAV_BOTTOM_BEIAN` | `nav_bottom_beian` | Click bottom ICP link | (defined but not implemented) |
| `NAV_BOTTOM_SKIN` | `nav_bottom_skin` | Click bottom skin setting | (defined but not implemented) |
| `NAV_BOTTOM_SETTING` | `nav_bottom_setting` | Click bottom settings | (defined but not implemented) |
| `NAV_TOP_LOGO` | `nav_top_logo` | Click top logo | NavHeader |
| `NAV_TOP_EXPAND` | `nav_top_expand` | Expand navigation | NavHeader |
| `NAV_TOP_COLLAPSE` | `nav_top_collapse` | Collapse navigation | NavHeader |
| `NAV_SECTION_SWITCH` | `nav_section_switch` | Switch lesson/chapter | useLessonTree |
| `RESET_CHAPTER` | `reset_chapter` | Click reset chapter | ResetChapterButton |
| `RESET_CHAPTER_CONFIRM` | `reset_chapter_confirm` | Confirm reset chapter | ResetChapterButton |
| `USER_MENU` | `user_menu` | Open user menu | NavDrawer |
| `USER_MENU_BASIC_INFO` | `user_menu_basic_info` | Click basic info in menu | MainMenuModal |
| `USER_MENU_PERSONALIZED` | `user_menu_personalized` | Click personalized settings | MainMenuModal |

### Hardcoded Event Names (not in EVENT_NAMES)

| Event Name | Description | Trigger Location | Data Fields |
|------------|-------------|------------------|-------------|
| `learner_lesson_start` | Start learning a lesson | useChatLogicHook | `shifu_bid`, `outline_bid` |
| `learner_pay_modal_view` | View payment modal | PayModal, PayModalM | `course_id`, `currency_code`, `display_price` |
| `learner_pay_cancel` | Cancel payment | PayModal, PayModalM | `course_id`, `order_id` |
| `learner_coupon_apply` | Apply coupon code | PayModal, PayModalM | `course_id`, `coupon_code`, `pay_channel` |

### Tracking Hook Methods

| Method | Description | Data Fields |
|--------|-------------|-------------|
| `trackEvent(name, data)` | Generic event tracking | Auto-attaches: `user_type`, `user_id`, `device`, `timeStamp` |
| `trackTrailProgress(courseId, blockId)` | Track trial lesson progress | `progress_no`, `progress_desc` (only for trial lessons) |
| `trackBlockView(courseId, blockId)` | Track block/module view | `shifu_bid`, `block_bid`, `position`, `outline_name`, `is_trial` |

---

## Event Naming Conventions

### Creator (Editor) Events
Format: `creator_<module>_<action>`

Examples:
- `creator_shifu_create_click` - Click create Shifu button
- `creator_shifu_create_success` - Shifu created successfully
- `creator_shifu_setting_save` - Save Shifu settings
- `creator_outline_create` - Create outline node
- `creator_outline_setting_save` - Save outline settings
- `creator_lesson_preview_click` - Preview lesson
- `creator_publish_click` - Click publish button
- `creator_publish_confirm` - Confirm publish
- `creator_mdf_convert_click` - Click MDF convert

### Learner (User) Events
Format: `learner_<module>_<action>` or use `EVENT_NAMES.*` constants

Examples:
- `learner_lesson_start` - Start learning a lesson
- `learner_block_view` - View a content block/module
- `learner_pay_modal_view` - View payment modal
- `learner_pay_cancel` - Cancel payment
- `learner_coupon_apply` - Apply coupon code

## Implementation Patterns

### Pattern 1: Basic Event Tracking

```typescript
import { useTracking } from '@/c-common/hooks/useTracking';

const MyComponent = () => {
  const { trackEvent } = useTracking();

  const handleClick = () => {
    trackEvent('creator_button_click', {
      button_name: 'submit',
      context: 'form',
    });
  };

  return <button onClick={handleClick}>Submit</button>;
};
```

### Pattern 2: Using Predefined EVENT_NAMES

```typescript
import { useTracking } from '@/c-common/hooks/useTracking';

const MyComponent = () => {
  const { trackEvent, EVENT_NAMES } = useTracking();

  const handleLogoClick = () => {
    trackEvent(EVENT_NAMES.NAV_TOP_LOGO, {});
  };

  return <div onClick={handleLogoClick}>Logo</div>;
};
```

### Pattern 3: Tracking on Mount/Effect

```typescript
import { useTracking } from '@/c-common/hooks/useTracking';
import { useEffect } from 'react';

const PaymentModal = ({ open, orderId }) => {
  const { trackEvent } = useTracking();

  useEffect(() => {
    if (open) {
      trackEvent('learner_pay_modal_view', {
        order_id: orderId,
      });
    }
  }, [open, orderId, trackEvent]);

  return open ? <div>Payment Modal</div> : null;
};
```

### Pattern 4: Tracking Async Operations

```typescript
import { useTracking } from '@/c-common/hooks/useTracking';

const SaveButton = ({ data, onSave }) => {
  const { trackEvent } = useTracking();

  const handleSave = async (saveType: 'auto' | 'manual') => {
    const startTime = Date.now();

    try {
      await onSave(data);

      trackEvent('creator_data_save_success', {
        save_type: saveType,
        duration_ms: Date.now() - startTime,
        data_size: JSON.stringify(data).length,
      });
    } catch (error) {
      trackEvent('creator_data_save_error', {
        save_type: saveType,
        error_message: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  };

  return <button onClick={() => handleSave('manual')}>Save</button>;
};
```

### Pattern 5: Auto-Save with Tracking

```typescript
import { useTracking } from '@/c-common/hooks/useTracking';
import { useEffect } from 'react';

const AutoSaveForm = ({ data, isDirty, onSave }) => {
  const { trackEvent } = useTracking();

  // Auto-save after 3 seconds of inactivity
  useEffect(() => {
    if (!isDirty) return;

    const timer = setTimeout(() => {
      onSave(data);
      trackEvent('creator_form_save', {
        save_type: 'auto',
        // Include relevant data fields
      });
    }, 3000);

    return () => clearTimeout(timer);
  }, [data, isDirty, onSave, trackEvent]);

  const handleManualSave = () => {
    onSave(data);
    trackEvent('creator_form_save', {
      save_type: 'manual',
    });
  };

  return <button onClick={handleManualSave}>Save</button>;
};
```

## Auto-Attached Data Fields

The `useTracking` hook automatically attaches these fields to every event:

| Field | Description | Values |
|-------|-------------|--------|
| `user_type` | User authentication state | `guest`, `user`, `member` |
| `user_id` | User identifier | String or 0 |
| `device` | Device type | `H5`, `Web` |
| `timeStamp` | Event timestamp | Locale string |

## Common Data Fields by Module

### Shifu Module
- `shifu_bid` - Shifu business ID
- `shifu_name` - Shifu name
- `model` - LLM model name
- `temperature` - Model temperature
- `system_prompt` - System prompt content

### Outline Module
- `outline_bid` - Outline node business ID
- `outline_name` - Outline node name
- `parent_bid` - Parent node ID (empty for root)
- `learning_permission` - `guest`, `trial`, `normal`
- `hide_chapter` - Whether chapter is hidden

### Save Operations
- `save_type` - `auto` or `manual`
- `duration_ms` - Operation duration in milliseconds

### Error Tracking
- `error_message` - Error message string
- `input_length` - Input data length

### Payment Module
- `course_id` - Course identifier
- `order_id` - Order identifier
- `currency_code` - Currency code
- `display_price` - Display price
- `pay_channel` - Payment channel
- `coupon_code` - Applied coupon code

## Adding New EVENT_NAMES Constants

If you need a frequently-used event, add it to `EVENT_NAMES` in `tracking.ts`:

```typescript
// src/cook-web/src/c-common/tools/tracking.ts
export const EVENT_NAMES = {
  // Existing events...
  VISIT: 'visit',

  // Add new event
  NEW_EVENT_NAME: 'new_event_name',
};
```

## Implementation Checklist

When adding tracking to a feature:

- [ ] Identify all user interaction points (clicks, form submissions, etc.)
- [ ] Identify state changes worth tracking (modal opens, data loads, etc.)
- [ ] Use correct naming convention (`creator_*` or `learner_*`)
- [ ] Include relevant context data (IDs, names, states)
- [ ] Track both success and error cases for async operations
- [ ] For auto-save features, distinguish `save_type: 'auto'` vs `'manual'`
- [ ] Consider tracking duration for performance-sensitive operations

## Key Files Reference

| File | Purpose |
|------|---------|
| `src/cook-web/src/c-common/tools/tracking.ts` | Core tracking utilities and EVENT_NAMES |
| `src/cook-web/src/c-common/hooks/useTracking.ts` | React hook for tracking |
| `src/cook-web/src/components/analytics/UmamiLoader.tsx` | Umami script loader |

---

## Instructions for Claude

### When Adding New Tracking Events

1. **Analyze the component** - Understand what interactions and state changes should be tracked
2. **Determine event names** - Follow naming conventions (`creator_*` or `learner_*`)
3. **Choose appropriate pattern** - Select from the patterns above based on the use case
4. **Import useTracking** - Add `import { useTracking } from '@/c-common/hooks/useTracking';`
5. **Add trackEvent calls** - Place tracking at appropriate points in the code
6. **Include relevant data** - Add context-specific data fields to events
7. **Handle errors** - Track error cases for async operations
8. **UPDATE THIS DOCUMENT** - Add new events to the "Implemented Events Registry" section above:
   - If adding to `EVENT_NAMES` constants, update the "EVENT_NAMES Constants" table
   - If using hardcoded event names, update the "Hardcoded Event Names" table
   - If adding new tracking methods to useTracking, update the "Tracking Hook Methods" table

### When Reviewing Tracking Implementation

1. **Check coverage** - Ensure all important interactions are tracked
2. **Verify naming** - Confirm events follow naming conventions
3. **Review data fields** - Ensure relevant context is included
4. **Check error handling** - Verify error cases are tracked
5. **Avoid redundancy** - Don't track the same action multiple times unnecessarily

### CRITICAL: Keeping This Document Updated

**Every time you add a new tracking event, you MUST update the "Implemented Events Registry" section in this file.**

This ensures:
- The team has an authoritative list of all tracking events
- New developers can quickly understand what's being tracked
- Analytics teams can reference this for data analysis
- No duplicate events are accidentally created
