import {
  buildCourseCreationAttemptAnalytics,
  buildCourseCreationCancelAnalytics,
  buildCourseCreationResultAnalytics,
} from './courseCreationAnalytics';

describe('courseCreationAnalytics', () => {
  test('builds bounded path payloads for attempts and cancellations', () => {
    expect(buildCourseCreationAttemptAnalytics('manual')).toEqual({
      creation_path: 'manual',
    });
    expect(buildCourseCreationCancelAnalytics('manual')).toEqual({
      creation_path: 'manual',
    });
    expect(buildCourseCreationAttemptAnalytics('ai_assistant')).toEqual({
      creation_path: 'ai_assistant',
    });
  });

  test('allows only a stable course id on successful manual creation', () => {
    const payload = buildCourseCreationResultAnalytics({
      creationPath: 'manual',
      outcome: 'success',
      shifuBid: 'course-1',
    });

    expect(payload).toEqual({
      creation_path: 'manual',
      outcome: 'success',
      shifu_bid: 'course-1',
    });
    expect(payload).not.toHaveProperty('shifu_name');
    expect(payload).not.toHaveProperty('prompt');
    expect(payload).not.toHaveProperty('title');
  });

  test('maps failures to a bounded category without raw errors', () => {
    const payload = buildCourseCreationResultAnalytics({
      creationPath: 'manual',
      outcome: 'failed',
      shifuBid: 'must-not-leak-on-failure',
      failureCategory: 'request_failed',
    });

    expect(payload).toEqual({
      creation_path: 'manual',
      outcome: 'failed',
      failure_category: 'request_failed',
    });
    expect(payload).not.toHaveProperty('error');
    expect(payload).not.toHaveProperty('message');
  });
});
