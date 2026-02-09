import request from '@/lib/request';

export const getCourseInfo = async (courseId: string, previewMode: boolean) => {
  return request
    .get(
      `/api/learn/shifu/${courseId}?preview_mode=${previewMode}`,
      // `/api/course/get-course-info?course_id=${courseId}&preview_mode=${previewMode}`,
    )
    .then(res => {
      const resolvedTtsEnabled =
        typeof res?.tts_enabled === 'boolean'
          ? res.tts_enabled
          : typeof res?.tts_enabled === 'number'
            ? res.tts_enabled > 0
            : typeof res?.tts_enabled === 'string'
              ? ['true', '1'].includes(res.tts_enabled.toLowerCase())
              : null;
      // Do processing at the model layer to adapt the new interface to the old interface format
      // Reduce the impact on the view layer
      const data = {
        course_desc: res.description,
        course_id: res.bid,
        course_keywords: res.keywords,
        course_name: res.title,
        course_price: res.price,
        course_teacher_avatar: res.avatar,
        course_avatar: res.avatar,
        course_tts_enabled: resolvedTtsEnabled,
      };
      return data;
    })
    .catch(err => {
      return null;
    });
};
