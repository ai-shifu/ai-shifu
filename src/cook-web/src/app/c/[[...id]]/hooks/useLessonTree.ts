import { useState, useCallback, useRef, useEffect } from 'react';
import { produce } from 'immer';
import { getLessonTree } from '@/c-api/lesson';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import { useEnvStore } from '@/c-store/envStore';
import { useSystemStore } from '@/c-store/useSystemStore';
import { useUserStore } from '@/store';
import { useCourseStore } from '@/c-store/useCourseStore';
import { useShallow } from 'zustand/react/shallow';
import { debugError, debugInfo, debugWarn } from '@/c-utils/debugConsole';
import { resolveLearnerLessonAccess } from '../learnerAccessRules';

type LessonTreeApiLesson = {
  bid: string;
  title: string;
  status: string;
  type: string;
  is_paid: boolean;
  has_content_update_for_current_user?: boolean;
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
};

export type LessonTreeLesson = {
  id: string;
  name: string;
  status: string;
  type: string;
  is_paid: boolean;
  has_content_update_for_current_user?: boolean;
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

export const useLessonTree = () => {
  const [tree, setTree] = useState<LessonTree>(null);
  const treeRef = useRef<LessonTree>(tree);

  useEffect(() => {
    treeRef.current = tree;
  }, [tree]);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);
  const { trackEvent } = useTracking();
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const previewMode = useSystemStore(state => state.previewMode);
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
      const access = resolveLearnerLessonAccess({
        type: lesson.type,
        isPaid: lesson.is_paid,
        isLoggedIn,
        previewMode,
        chapterId,
        lessonId: lesson.id,
        currentPathAndSearch: location.pathname + location.search,
      });

      if (access.type === 'login') {
        window.location.href = access.redirectUrl;
        return false;
      }

      if (access.type === 'pay') {
        openPayModal({
          type: access.modalType,
          payload: access.payload,
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
        setSelectedLessonId(lesson.id);
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
          setSelectedLessonId(
            lastChapter.lessons[lastChapter.lessons.length - 1].id,
          );
        }
      }
    },
    [ensureLessonAccessible],
  );

  const loadTreeInner = useCallback(async () => {
    setSelectedLessonId(null);
    const courseId = useEnvStore.getState().courseId;
    debugInfo('[lesson-tree] request start', {
      courseId,
      previewMode,
      path:
        typeof window !== 'undefined'
          ? `${window.location.pathname}${window.location.search}`
          : '',
    });

    try {
      const treeData = (await getLessonTree(
        courseId,
        previewMode,
      )) as LessonTreeApiResponse;
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

      const catalogs: LessonTreeCatalog[] = (treeData.outline_items || []).map(
        l => {
          const lessons: LessonTreeLesson[] = l.children.map(c => {
            return {
              id: c.bid,
              name: c.title,
              status: c.status,
              type: c.type,
              is_paid: c.is_paid,
              has_content_update_for_current_user:
                c.has_content_update_for_current_user,
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
        },
      );

      const newTree: LessonTreeData = {
        catalogs,
        bannerInfo: treeData.banner_info,
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
  }, [previewMode]);

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
        setSelectedLessonId(lesson.id);
        return true;
      }
      return true;
    },
    [ensureLessonAccessible],
  );

  // Reload the course tree while preserving transient state
  const reloadTree = useCallback(
    async (chapterId: string | undefined = undefined, lessonId = undefined) => {
      const newTree = await loadTreeInner();
      if (chapterId === undefined) {
        initialSelectedChapter(newTree);
      } else {
        setSelectedState(newTree, chapterId, lessonId);
      }
      // Restore each catalog's collapse state using the previous snapshot
      const previousTree = treeRef.current;
      newTree?.catalogs.forEach(c => {
        const oldCatalog = previousTree?.catalogs.find(oc => oc.id === c.id);

        if (oldCatalog) {
          c.collapse = oldCatalog.collapse;
        }
      });

      setTree(newTree);
      return newTree;
    },
    [loadTreeInner, initialSelectedChapter, setSelectedState],
  );

  const loadTree = useCallback(
    async (chapterId = '', lessonId = '') => {
      let newTree: LessonTree = null;
      if (!tree) {
        newTree = await loadTreeInner();
      } else {
        newTree = tree;
      }

      const selected = setSelectedState(newTree, chapterId, lessonId);
      if (!selected) {
        initialSelectedChapter(newTree);
      }
      setTree(newTree);
      return newTree;
    },
    [initialSelectedChapter, loadTreeInner, setSelectedState, tree],
  );

  const updateSelectedLesson = async (
    lessonId: string,
    forceExpand = false,
  ) => {
    setSelectedLessonId(lessonId);

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
    const nextState = produce(tree, draft => {
      if (!draft) {
        return draft;
      }
      draft.catalogs.forEach(c => {
        if (c.id === id) {
          c.collapse = !c.collapse;
        }
      });
    });

    setTree(nextState);
  };

  const updateLesson = (id: string, val: LessonUpdatePatch) => {
    setTree(old => {
      if (!old) {
        return null;
      }

      const nextState = produce(old, draft => {
        draft.catalogs.forEach(c => {
          const idx = c.lessons.findIndex(ch => ch.id === id);
          if (idx !== -1) {
            const newLesson = {
              ...c.lessons[idx],
              ...val,
            };
            newLesson.canLearning = checkChapterCanLearning(newLesson);
            c.lessons[idx] = newLesson;
          }
        });
      });

      return nextState;
    });
  };

  const updateChapterStatus = (
    id: string,
    { status, status_value }: ChapterStatusPatch,
  ) => {
    setTree(old => {
      if (!old) {
        return null;
      }

      const nextState = produce(old, draft => {
        const idx = draft.catalogs.findIndex(ch => ch.id === id);
        if (idx !== -1) {
          draft.catalogs[idx] = {
            ...draft.catalogs[idx],
            status,
            status_value,
          };
        }
      });

      return nextState;
    });
  };

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
    if (!tree) {
      return;
    }

    let from = '';
    let to = '';

    for (const catalog of tree.catalogs) {
      const lesson = catalog.lessons.find(v => v.id === selectedLessonId);

      if (lesson) {
        from = `${catalog.name}|${lesson.name}`;
      }

      const toLesson = catalog.lessons.find(v => v.id === lessonId);
      if (toLesson) {
        to = `${catalog.name}|${toLesson.name}`;
      }
    }

    const eventData = {
      from,
      to,
    };
    trackEvent(EVENT_NAMES.NAV_SECTION_SWITCH, eventData);
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
