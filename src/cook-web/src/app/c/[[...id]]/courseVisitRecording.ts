import { useEffect, useRef } from 'react';
import { recordCourseVisit } from '@/c-api/course';

type CourseVisitRecordingParams = {
  initialized: boolean;
  isLoggedIn: boolean;
  previewMode: boolean;
  urlPreviewMode: boolean;
  routeCourseId: string;
  loadedCourseId: string | null;
  userId: string;
};

const inFlightCourseVisits = new Map<string, Promise<unknown>>();

const normalizeId = (value: string | null) => String(value || '').trim();

export const resolveCourseVisitRecording = ({
  initialized,
  isLoggedIn,
  previewMode,
  urlPreviewMode,
  routeCourseId,
  loadedCourseId,
  userId,
}: CourseVisitRecordingParams) => {
  const normalizedRouteCourseId = normalizeId(routeCourseId);
  const normalizedLoadedCourseId = normalizeId(loadedCourseId);
  const normalizedUserId = normalizeId(userId);

  if (
    !initialized ||
    !isLoggedIn ||
    previewMode ||
    urlPreviewMode ||
    !normalizedRouteCourseId ||
    !normalizedUserId ||
    normalizedLoadedCourseId !== normalizedRouteCourseId
  ) {
    return null;
  }

  return {
    key: `${normalizedUserId}:${normalizedRouteCourseId}`,
    courseId: normalizedRouteCourseId,
  };
};

const getOrCreateCourseVisitRequest = (key: string, courseId: string) => {
  const existingRequest = inFlightCourseVisits.get(key);
  if (existingRequest) {
    return existingRequest;
  }

  const request = recordCourseVisit(courseId).finally(() => {
    if (inFlightCourseVisits.get(key) === request) {
      inFlightCourseVisits.delete(key);
    }
  });
  inFlightCourseVisits.set(key, request);
  return request;
};

export const useCourseVisitRecording = (params: CourseVisitRecordingParams) => {
  const attemptedKeysRef = useRef(new Set<string>());
  const recording = resolveCourseVisitRecording(params);
  const recordingKey = recording?.key || '';
  const recordingCourseId = recording?.courseId || '';

  // Attempt once per eligible user/course key for this mount. A rejected
  // best-effort write is swallowed and can retry after a real remount, without
  // turning frequent chat rerenders into a request storm.
  useEffect(() => {
    if (!recordingKey || attemptedKeysRef.current.has(recordingKey)) {
      return;
    }

    attemptedKeysRef.current.add(recordingKey);
    void getOrCreateCourseVisitRequest(recordingKey, recordingCourseId).catch(
      () => undefined,
    );
  }, [recordingCourseId, recordingKey]);
};
