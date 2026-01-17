# AI-Shifu Existing Tracking Events Reference

This document lists all existing tracking events in the AI-Shifu frontend codebase.

## EVENT_NAMES Constants

Defined in `src/cook-web/src/c-common/tools/tracking.ts`:

| Constant | Event Name | Description |
|----------|------------|-------------|
| `VISIT` | `visit` | Page visit |
| `TRIAL_PROGRESS` | `trial_progress` | Trial course progress |
| `POP_PAY` | `pop_pay` | Payment popup shown |
| `POP_LOGIN` | `pop_login` | Login popup shown |
| `PAY_SUCCEED` | `pay_succeed` | Payment succeeded |
| `NAV_BOTTOM_BEIAN` | `nav_bottom_beian` | Click bottom ICP link |
| `NAV_BOTTOM_SKIN` | `nav_bottom_skin` | Click bottom skin option |
| `NAV_BOTTOM_SETTING` | `nav_bottom_setting` | Click bottom settings |
| `NAV_TOP_LOGO` | `nav_top_logo` | Click top logo |
| `NAV_TOP_EXPAND` | `nav_top_expand` | Expand navigation |
| `NAV_TOP_COLLAPSE` | `nav_top_collapse` | Collapse navigation |
| `NAV_SECTION_SWITCH` | `nav_section_switch` | Switch section |
| `RESET_CHAPTER` | `reset_chapter` | Click reset chapter |
| `RESET_CHAPTER_CONFIRM` | `reset_chapter_confirm` | Confirm chapter reset |
| `USER_MENU` | `user_menu` | Open user menu |
| `USER_MENU_BASIC_INFO` | `user_menu_basic_info` | Click basic info menu |
| `USER_MENU_PERSONALIZED` | `user_menu_personalized` | Click personalized menu |

## Creator (Editor) Events

### Shifu Management

| Event Name | File | Description | Key Data |
|------------|------|-------------|----------|
| `creator_shifu_create_click` | `app/admin/page.tsx` | Click create Shifu | - |
| `creator_shifu_create_success` | `app/admin/page.tsx` | Shifu created | `shifu_bid`, `shifu_name` |
| `creator_shifu_setting_save` | `components/shifu-setting/ShifuSetting.tsx` | Save Shifu settings | `shifu_bid`, `save_type`, `model`, `temperature`, `system_prompt` |
| `creator_shifu_preview_click` | `components/shifu-edit/Preview.tsx` | Preview entire Shifu | `shifu_bid` |

### Outline Management

| Event Name | File | Description | Key Data |
|------------|------|-------------|----------|
| `creator_outline_create` | `store/useShifu.tsx` | Create outline node | `shifu_bid`, `outline_bid`, `outline_name`, `parent_bid` |
| `creator_outline_setting_save` | `components/chapter-setting/ChapterSetting.tsx` | Save lesson settings | `outline_bid`, `shifu_bid`, `save_type`, `variant`, `learning_permission`, `hide_chapter`, `system_prompt` |
| `creator_outline_prompt_save` | `components/chapter-setting/ChapterSetting.tsx` | Save chapter prompt | `outline_bid`, `shifu_bid`, `system_prompt`, `save_type` |
| `creator_lesson_preview_click` | `components/shifu-edit/ShifuEdit.tsx` | Preview single lesson | `shifu_bid`, `outline_bid` |

### MDF Conversion

| Event Name | File | Description | Key Data |
|------------|------|-------------|----------|
| `creator_mdf_dialog_open` | `components/shifu-edit/ShifuEdit.tsx` | Open MDF dialog | - |
| `creator_mdf_convert_click` | `components/mdf-convert/MdfConvertDialog.tsx` | Click convert | `input_length` |
| `creator_mdf_convert_success` | `components/mdf-convert/MdfConvertDialog.tsx` | Conversion success | `input_length`, `duration_ms` |
| `creator_mdf_convert_error` | `components/mdf-convert/MdfConvertDialog.tsx` | Conversion failed | `input_length`, `error_message` |
| `creator_mdf_copy_click` | `components/mdf-convert/MdfConvertDialog.tsx` | Copy result | - |
| `creator_mdf_apply_click` | `components/mdf-convert/MdfConvertDialog.tsx` | Apply to editor | - |
| `creator_mdf_cancel_click` | `components/mdf-convert/MdfConvertDialog.tsx` | Cancel conversion | `input_length` |
| `creator_mdf_back_click` | `components/mdf-convert/MdfConvertDialog.tsx` | Back to edit | - |
| `creator_mdf_close_click` | `components/mdf-convert/MdfConvertDialog.tsx` | Close dialog | - |

### Publishing

| Event Name | File | Description | Key Data |
|------------|------|-------------|----------|
| `creator_publish_click` | `components/header/Header.tsx` | Click publish | `shifu_bid`, `is_published` |
| `creator_publish_confirm` | `components/header/Header.tsx` | Confirm publish | `shifu_bid`, `publish_state` |
| `creator_publish_cancel` | `components/header/Header.tsx` | Cancel publish | `shifu_bid` |

## Learner (User) Events

### Learning Progress

| Event Name | File | Description | Key Data |
|------------|------|-------------|----------|
| `learner_lesson_start` | `app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx` | Start lesson | `course_id`, `lesson_id`, `outline_bid` |
| `trial_progress` | via `trackTrailProgress()` | Trial progress | `progress_no`, `progress_desc` |

### Payment

| Event Name | File | Description | Key Data |
|------------|------|-------------|----------|
| `learner_pay_modal_view` | `app/c/[[...id]]/Components/Pay/PayModalM.tsx` | View payment modal | `course_id`, `currency_code`, `display_price` |
| `learner_pay_cancel` | `app/c/[[...id]]/Components/Pay/PayModalM.tsx` | Cancel payment | `course_id`, `order_id` |
| `learner_coupon_apply` | `app/c/[[...id]]/Components/Pay/PayModalM.tsx` | Apply coupon | `course_id`, `coupon_code`, `pay_channel` |
| `pop_pay` | `app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx` | Payment popup | `from` |
| `pay_succeed` | via `EVENT_NAMES.PAY_SUCCEED` | Payment success | - |

### Navigation

| Event Name | File | Description | Key Data |
|------------|------|-------------|----------|
| `nav_top_logo` | `app/c/[[...id]]/Components/NavDrawer/NavHeader.tsx` | Click logo | - |
| `nav_top_expand` | `app/c/[[...id]]/Components/NavDrawer/NavHeader.tsx` | Expand nav | - |
| `nav_top_collapse` | `app/c/[[...id]]/Components/NavDrawer/NavHeader.tsx` | Collapse nav | - |
| `nav_section_switch` | `app/c/[[...id]]/hooks/useLessonTree.ts` | Switch section | - |

### User Menu

| Event Name | File | Description | Key Data |
|------------|------|-------------|----------|
| `user_menu_basic_info` | `app/c/[[...id]]/Components/NavDrawer/MainMenuModal.tsx` | Click basic info | - |
| `user_menu_personalized` | `app/c/[[...id]]/Components/NavDrawer/MainMenuModal.tsx` | Click personalized | - |
| `pop_login` | Multiple files | Login popup shown | `from` |

### Chapter Operations

| Event Name | File | Description | Key Data |
|------------|------|-------------|----------|
| `reset_chapter` | `app/c/[[...id]]/Components/CourseCatalog/ResetChapterButton.tsx` | Click reset | `chapter_id`, `chapter_name` |
| `reset_chapter_confirm` | `app/c/[[...id]]/Components/CourseCatalog/ResetChapterButton.tsx` | Confirm reset | `chapter_id`, `chapter_name` |

## Data Field Reference

### Common Fields (Auto-attached by useTracking)

| Field | Type | Description |
|-------|------|-------------|
| `user_type` | `guest` \| `user` \| `member` | User state |
| `user_id` | `string` \| `0` | User identifier |
| `device` | `H5` \| `Web` | Device type |
| `timeStamp` | `string` | Event timestamp |

### ID Fields

| Field | Description |
|-------|-------------|
| `shifu_bid` | Shifu business identifier |
| `outline_bid` | Outline node business identifier |
| `course_id` | Course identifier |
| `lesson_id` | Lesson identifier |
| `chapter_id` | Chapter identifier |
| `order_id` | Order identifier |
| `parent_bid` | Parent node identifier |

### Operation Fields

| Field | Values | Description |
|-------|--------|-------------|
| `save_type` | `auto`, `manual` | How save was triggered |
| `from` | varies | Source of action (e.g., `user_menu`, `show-btn`) |
| `variant` | `chapter`, `lesson` | Type variant |
| `learning_permission` | `guest`, `trial`, `normal` | Access level |

### Measurement Fields

| Field | Type | Description |
|-------|------|-------------|
| `duration_ms` | `number` | Operation duration in milliseconds |
| `input_length` | `number` | Input text/data length |
| `progress_no` | `number` | Progress number |

### Error Fields

| Field | Type | Description |
|-------|------|-------------|
| `error_message` | `string` | Error message text |

### Payment Fields

| Field | Description |
|-------|-------------|
| `currency_code` | Payment currency |
| `display_price` | Displayed price |
| `pay_channel` | Payment channel |
| `coupon_code` | Applied coupon |
