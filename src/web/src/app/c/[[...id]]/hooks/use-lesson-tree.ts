import { useState, useCallback, useRef } from 'react';
import { useIsomorphicLayoutEffect } from 'react-use';
import { produce } from 'immer';
import { getLessonTree } from '@/api/lesson';
import { LESSON_STATUS_VALUE } from '@/constants/course-constants';
import { useTracking } from '@/hooks/use-tracking';
import { useEnvStore } from '@/store/env-store';
import { useSystemStore } from '@/store/use-system-store';
import { LEARNING_PERMISSION } from '@/api/learning';
import { useUserStore } from '@/store';
import { useCourseStore } from '@/store/use-course-store';
import { useShallow } from 'zustand/react/shallow';
import { debugError, debugInfo, debugWarn } from '@/lib/debug-console';
import {
  buildLessonNavigationAnalytics,
  LESSON_NAVIGATION_EVENT,
  shouldTrackLessonNavigation,
} from './lesson-navigation-analytics';

type LessonTreeApiLesson = {
  bid: string;
  title: string;
  status: string;
  type: string;
  is_paid: boolean;
  has_content_update_for_current_user?: boolean;
  follow_up_mode?: 'text' | 'live_voice' | 'disabled';
};

type LessonTreeApiCatalog = {
  bid: string;
  title: string;
  status: string;
  type: string;
  is_paid: boolean;
  children: LessonTreeApiLesson[];
};

type LessonTreeApiResponse = {
  outline_items?: LessonTreeApiCatalog[];
  banner_info?: unknown;
  title_language?: string;
  content_language?: string;
};

export type LessonTreeLesson = {
  id: string;
  name: string;
  status: string;
  type: string;
  is_paid: boolean;
  has_content_update_for_current_user?: boolean;
  follow_up_mode: 'text' | 'live_voice' | 'disabled';
  status_value: string;
  canLearning: boolean;
  user_input?: string;
};

export type LessonTreeCatalog = {
  id: string;
  name: string;
  status: string;
  is_paid: boolean;
  status_value: string;
  type: string;
  lessons: LessonTreeLesson[];
  collapse: boolean;
};

export type LessonTreeData = {
  bannerInfo?: unknown;
  titleLanguage?: string;
  contentLanguage?: string;
  catalogs: LessonTreeCatalog[];
};

export type LessonTree = LessonTreeData | null;

type LessonStatusLike = {
  status_value: string;
};

type LessonSelectionResult = {
  catalog: LessonTreeCatalog | null;
  lesson: LessonTreeLesson | null;
};

type ToggleCollapseParams = {
  id: string;
};

type LessonUpdatePatch = Partial<LessonTreeLesson>;

type ChapterStatusPatch = {
  status: string;
  status_value: string;
};

type OutlineProgressPatch =
  | {
      kind: 'lesson';
      id: string;
      patch: LessonUpdatePatch;
      refreshMissingLesson?: boolean;
    }
  | { kind: 'chapter'; id: string; patch: ChapterStatusPatch };

type LessonSelectTrackingParams = {
  lessonId: string;
};

export const checkChapterCanLearning = ({ status_value }: LessonStatusLike) => {
  const canLearn =
    status_value === LESSON_STATUS_VALUE.LEARNING ||
    status_value === LESSON_STATUS_VALUE.COMPLETED ||
    status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING;
  return canLearn;
};

const isMissingHistoryLesson = (
  tree: LessonTreeData,
  update: OutlineProgressPatch,
) =>
  update.kind === 'lesson' &&
  update.refreshMissingLesson === true &&
  !tree.catalogs.some(catalog =>
    catalog.lessons.some(lesson => lesson.id === update.id),
  );

const applyOutlineProgress = (
  tree: LessonTree,
  updates: OutlineProgressPatch[],
) => {
  if (!tree || !updates.length) return tree;

  return produce(tree, draft => {
    for (const { kind, id, patch } of updates) {
      if (kind === 'chapter') {
        const chapter = draft.catalogs.find(catalog => catalog.id === id);
        if (chapter) Object.assign(chapter, patch);
      } else {
        for (const catalog of draft.catalogs) {
          const lesson = catalog.lessons.find(entry => entry.id === id);
          if (!lesson) continue;
          Object.assign(lesson, patch);
          lesson.canLearning = checkChapterCanLearning(lesson);
        }
      }
    }
  });
};

export const useLessonTree = (routeCourseId?: string) => {
  const [tree, setTree] = useState<LessonTree>(null);
  const loadedOutline = useRef<LessonTree>(null);
  const pendingOutlineRequest = useRef<{
    updates: OutlineProgressPatch[];
  } | null>(null);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);
  const latestSelection = useRef<{ lessonId: string | null }>({
    lessonId: null,
  });
  const selectLesson = useCallback((lessonId: string) => {
    if (latestSelection.current.lessonId !== lessonId) {
      latestSelection.current = { lessonId };
    }
    setSelectedLessonId(lessonId);
  }, []);
  const { trackEvent } = useTracking();
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const previewMode = useSystemStore(state => state.previewMode);

  useIsomorphicLayoutEffect(
    () => () => {
      loadedOutline.current = null;
      pendingOutlineRequest.current = null;
    },
    [routeCourseId, previewMode],
  );
  const { openPayModal } = useCourseStore(
    useShallow(state => ({
      openPayModal: state.openPayModal,
    })),
  );

  const getCurrElement =
    useCallback(async (): Promise<LessonSelectionResult> => {
      if (!tree || !selectedLessonId) {
        return { catalog: null, lesson: null };
      }

      for (const catalog of tree.catalogs) {
        const lesson = catalog.lessons.find(v => v.id === selectedLessonId);
        if (lesson) {
          return { catalog, lesson };
        }
      }
      return { catalog: null, lesson: null };
    }, [selectedLessonId, tree]);

  const ensureLessonAccessible = useCallback(
    (lesson: LessonTreeLesson, chapterId: string) => {
      const needsLogin =
        (lesson.type === LEARNING_PERMISSION.TRIAL ||
          lesson.type === LEARNING_PERMISSION.NORMAL) &&
        !isLoggedIn;
      if (!previewMode && needsLogin) {
        window.location.href = `/login?redirect=${encodeURIComponent(location.pathname + location.search)}`;
        return false;
      }

      if (
        !previewMode &&
        lesson.type === LEARNING_PERMISSION.NORMAL &&
        !lesson.is_paid
      ) {
        openPayModal({
          type: lesson.type,
          payload: {
            chapterId,
            lessonId: lesson.id,
          },
        });
        return false;
      }

      return true;
    },
    [isLoggedIn, openPayModal, previewMode],
  );

  const initialSelectedChapter = useCallback(
    (treeData: LessonTreeData | null) => {
      if (!treeData) {
        return;
      }
      let catalog = treeData.catalogs.find(
        v => v.status_value === LESSON_STATUS_VALUE.LEARNING,
      );
      let lesson: LessonTreeLesson | undefined;
      if (catalog) {
        lesson = catalog.lessons.find(
          v =>
            v.status_value === LESSON_STATUS_VALUE.LEARNING ||
            v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING,
        );
      } else {
        catalog = treeData.catalogs.find(
          v => v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING,
        );
        if (catalog) {
          lesson = catalog.lessons.find(
            v =>
              v.status_value === LESSON_STATUS_VALUE.LEARNING ||
              v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING,
          );
        }
      }
      if (lesson) {
        if (!ensureLessonAccessible(lesson, catalog?.id || '')) {
          return;
        }
        selectLesson(lesson.id);
      } else {
        // find the last chapter that is completed
        let lastChapter: LessonTreeCatalog | undefined;
        for (let i = treeData.catalogs.length - 1; i >= 0; i -= 1) {
          const chapter = treeData.catalogs[i];
          if (chapter.status_value === LESSON_STATUS_VALUE.COMPLETED) {
            lastChapter = chapter;
            break;
          }
        }
        if (lastChapter) {
          selectLesson(lastChapter.lessons[lastChapter.lessons.length - 1].id);
        }
      }
    },
    [ensureLessonAccessible, selectLesson],
  );

  const loadTreeInner = useCallback(
    async (background = false) => {
      const courseId = routeCourseId || useEnvStore.getState().courseId;
      debugInfo('[lesson-tree] request start', {
        courseId,
        previewMode,
        path:
          typeof window !== 'undefined'
            ? `${window.location.pathname}${window.location.search}`
            : '',
      });

      try {
        const treeData = (await (background
          ? getLessonTree(courseId, previewMode, { skipErrorToast: true })
          : getLessonTree(courseId, previewMode))) as LessonTreeApiResponse;
        if (!treeData) {
          debugWarn('[lesson-tree] empty response', {
            courseId,
            previewMode,
          });
          return null;
        }

        // new api without course_id
        // if (treeData.course_id !== useEnvStore.getState().courseId) {
        //   await updateCourseId(treeData.course_id);
        // }

        const catalogs: LessonTreeCatalog[] = (
          treeData.outline_items || []
        ).map(l => {
          const lessons: LessonTreeLesson[] = l.children.map(c => {
            return {
              id: c.bid,
              name: c.title,
              status: c.status,
              type: c.type,
              is_paid: c.is_paid,
              has_content_update_for_current_user:
                c.has_content_update_for_current_user,
              follow_up_mode:
                c.follow_up_mode === 'live_voice' ||
                c.follow_up_mode === 'disabled'
                  ? c.follow_up_mode
                  : 'text',
              status_value: c.status, // TODO: DELETE status_value
              canLearning: checkChapterCanLearning({ status_value: c.status }),
            };
          });

          return {
            id: l.bid,
            name: l.title,
            status: l.status,
            is_paid: l.is_paid,
            status_value: l.status,
            type: l.type,
            lessons,
            collapse: false,
          };
        });

        const newTree: LessonTreeData = {
          catalogs,
          bannerInfo: treeData.banner_info,
          titleLanguage: treeData.title_language,
          contentLanguage: treeData.content_language,
        };

        debugInfo('[lesson-tree] request success', {
          courseId,
          previewMode,
          outlineItemCount: treeData.outline_items?.length || 0,
          catalogCount: catalogs.length,
        });

        return newTree;
      } catch (error) {
        debugError('[lesson-tree] request failed', {
          courseId,
          previewMode,
          errorMessage: error instanceof Error ? error.message : String(error),
          businessCode: (error as { code?: number | string })?.code ?? '',
          httpStatus: (error as { status?: number | string })?.status ?? '',
        });
        throw error;
      }
    },
    [previewMode, routeCourseId],
  );

  const setSelectedState = useCallback(
    (treeData: LessonTreeData | null, chapterId: string, lessonId?: string) => {
      if (!treeData) {
        return false;
      }

      let chapter = treeData.catalogs.find(v => v.id === chapterId);
      let lesson: LessonTreeLesson | undefined;

      if (chapter && lessonId) {
        lesson = chapter.lessons.find(v => v.id === lessonId);
      }

      if (!lesson && lessonId) {
        for (const catalog of treeData.catalogs) {
          const matchedLesson = catalog.lessons.find(v => v.id === lessonId);
          if (matchedLesson) {
            chapter = catalog;
            lesson = matchedLesson;
            break;
          }
        }
      }

      if (!chapter) {
        return false;
      }

      if (!lesson) {
        lesson = chapter.lessons.find(
          v =>
            v.status_value === LESSON_STATUS_VALUE.LEARNING ||
            v.status === LESSON_STATUS_VALUE.PREPARE_LEARNING,
        );
      }

      if (lesson) {
        if (!ensureLessonAccessible(lesson, chapter.id)) {
          return false;
        }
        selectLesson(lesson.id);
        return true;
      }
      return true;
    },
    [ensureLessonAccessible, selectLesson],
  );

  const loadOutline = useCallback(
    async function loadOutline({
      select,
      updates = [],
      targetLessonId,
    }: {
      select?: (newTree: LessonTree) => void;
      updates?: OutlineProgressPatch[];
      targetLessonId?: string;
    }): Promise<LessonTree | undefined> {
      const request = { updates };
      pendingOutlineRequest.current = request;
      const selection = latestSelection.current;
      const isSelectionCurrent = () =>
        !select ||
        latestSelection.current === selection ||
        latestSelection.current.lessonId === targetLessonId;
      try {
        const loadedTree = await loadTreeInner(!select);
        if (pendingOutlineRequest.current !== request) return;
        const shouldSelect = isSelectionCurrent();
        if (!loadedTree) return shouldSelect ? null : undefined;

        // The response can be older than progress that arrived from history or SSE.
        const newTree = applyOutlineProgress(loadedTree, request.updates);
        loadedOutline.current = newTree;
        if (select && shouldSelect) {
          setSelectedLessonId(null);
          select(newTree);
        }
        setTree(previousTree => {
          if (!newTree) return previousTree;
          return {
            ...newTree,
            catalogs: newTree.catalogs.map(catalog => ({
              ...catalog,
              collapse:
                previousTree?.catalogs.find(
                  previous => previous.id === catalog.id,
                )?.collapse ?? catalog.collapse,
            })),
          };
        });
        if (select && newTree) {
          const missing = request.updates.filter(update =>
            isMissingHistoryLesson(newTree, update),
          );
          if (missing.length) {
            // The pending foreground snapshot can predate a catalog edit too.
            void loadOutline({ updates: missing });
          }
        }
        return shouldSelect ? newTree : undefined;
      } catch (error) {
        if (
          select &&
          pendingOutlineRequest.current === request &&
          isSelectionCurrent()
        ) {
          throw error;
        }
      } finally {
        if (pendingOutlineRequest.current === request) {
          pendingOutlineRequest.current = null;
        }
      }
    },
    [loadTreeInner],
  );

  const updateOutlineProgress = useCallback(
    (update: OutlineProgressPatch) => {
      setTree(current => applyOutlineProgress(current, [update]));
      const pending = pendingOutlineRequest.current;
      if (pending) {
        pending.updates.push(update);
      } else if (
        loadedOutline.current &&
        isMissingHistoryLesson(loadedOutline.current, update)
      ) {
        // An authorized progress update names a row missing from the cached catalog.
        void loadOutline({ updates: [update] });
      }
    },
    [loadOutline],
  );

  const reloadTree = useCallback(
    (chapterId?: string, lessonId?: string) =>
      loadOutline({
        targetLessonId: lessonId,
        select: newTree => {
          if (chapterId === undefined) {
            initialSelectedChapter(newTree);
          } else {
            setSelectedState(newTree, chapterId, lessonId);
          }
        },
      }),
    [initialSelectedChapter, loadOutline, setSelectedState],
  );

  const loadTree = useCallback(
    async (chapterId = '', lessonId = '') => {
      const select = (newTree: LessonTree) => {
        if (!setSelectedState(newTree, chapterId, lessonId)) {
          initialSelectedChapter(newTree);
        }
      };
      if (!tree) return loadOutline({ select, targetLessonId: lessonId });
      select(tree);
      return tree;
    },
    [initialSelectedChapter, loadOutline, setSelectedState, tree],
  );

  const updateSelectedLesson = async (
    lessonId: string,
    forceExpand = false,
  ) => {
    selectLesson(lessonId);

    setTree(old => {
      if (!old) {
        return null;
      }
      const nextState = produce(old, draft => {
        draft.catalogs.forEach(c => {
          c.lessons.forEach(ls => {
            if (ls.id === lessonId) {
              if (forceExpand) {
                c.collapse = false;
              }
            }
          });
        });
      });
      return nextState;
    });
  };

  const setCurrCatalog = async (catalogId: string) => {
    if (!tree) {
      return;
    }

    const ca = tree.catalogs.find(c => c.id === catalogId);
    if (!ca) {
      return;
    }
    const l = ca.lessons[0];
    if (!l) {
      return;
    }

    updateSelectedLesson(l.id);
  };

  const toggleCollapse = ({ id }: ToggleCollapseParams) => {
    setTree(current =>
      produce(current, draft => {
        const catalog = draft?.catalogs.find(entry => entry.id === id);
        if (catalog) catalog.collapse = !catalog.collapse;
      }),
    );
  };

  const updateLesson = useCallback(
    (
      id: string,
      patch: LessonUpdatePatch,
      { refreshMissingLesson = false } = {},
    ) =>
      updateOutlineProgress({
        kind: 'lesson',
        id,
        patch,
        refreshMissingLesson,
      }),
    [updateOutlineProgress],
  );

  const updateChapterStatus = useCallback(
    (id: string, patch: ChapterStatusPatch) =>
      updateOutlineProgress({ kind: 'chapter', id, patch }),
    [updateOutlineProgress],
  );

  const getChapterByLesson = (lessonId: string): LessonTreeCatalog | null => {
    if (!tree) {
      return null;
    }
    const chapter = tree.catalogs.find(ch => {
      return ch.lessons.find(ls => ls.id === lessonId);
    });
    return chapter ?? null;
  };

  const getNextLessonId = useCallback(
    (currentLessonId?: string | null) => {
      if (!tree) {
        return null;
      }

      const targetLessonId = currentLessonId ?? selectedLessonId;
      if (!targetLessonId) {
        return null;
      }

      for (
        let catalogIndex = 0;
        catalogIndex < tree.catalogs.length;
        catalogIndex += 1
      ) {
        const catalog = tree.catalogs[catalogIndex];
        const lessonIndex = catalog.lessons.findIndex(
          ls => ls.id === targetLessonId,
        );
        if (lessonIndex === -1) {
          continue;
        }

        for (
          let nextLessonIndex = lessonIndex + 1;
          nextLessonIndex < catalog.lessons.length;
          nextLessonIndex += 1
        ) {
          const nextLesson = catalog.lessons[nextLessonIndex];
          if (nextLesson) {
            return nextLesson.id ?? null;
          }
        }

        for (
          let nextCatalogIndex = catalogIndex + 1;
          nextCatalogIndex < tree.catalogs.length;
          nextCatalogIndex += 1
        ) {
          const nextCatalog = tree.catalogs[nextCatalogIndex];
          if (!nextCatalog.lessons || nextCatalog.lessons.length === 0) {
            continue;
          }
          return nextCatalog.lessons[0]?.id ?? null;
        }

        return null;
      }

      return null;
    },
    [selectedLessonId, tree],
  );

  const onTryLessonSelect = ({ lessonId }: LessonSelectTrackingParams) => {
    if (
      !tree ||
      !shouldTrackLessonNavigation({
        previewMode,
        fromLessonId: selectedLessonId,
        toLessonId: lessonId,
      })
    ) {
      return;
    }

    trackEvent(
      LESSON_NAVIGATION_EVENT,
      buildLessonNavigationAnalytics({
        shifuBid: useEnvStore.getState().courseId,
        fromLessonId: selectedLessonId,
        toLessonId: lessonId,
      }),
    );
  };

  return {
    tree,
    selectedLessonId,
    loadTree,
    reloadTree,
    updateSelectedLesson,
    setCurrCatalog,
    toggleCollapse,
    updateLesson,
    updateChapterStatus,
    getCurrElement,
    getChapterByLesson,
    onTryLessonSelect,
    getNextLessonId,
  };
};
