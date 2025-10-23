import { useState, useCallback, useRef, useEffect } from 'react';
import { produce } from 'immer';
import { getLessonTree } from '@/c-api/lesson';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import { useEnvStore } from '@/c-store/envStore';
import { useSystemStore } from '@/c-store/useSystemStore';
import { LEARNING_PERMISSION } from '@/c-api/studyV2';
import { useUserStore } from '@/store';
import { useCourseStore } from '@/c-store/useCourseStore';
import { useShallow } from 'zustand/react/shallow';

export const checkChapterCanLearning = ({ status_value }) => {
  const canLearn =
    status_value === LESSON_STATUS_VALUE.LEARNING ||
    status_value === LESSON_STATUS_VALUE.COMPLETED ||
    status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING;
  return canLearn;
};

type LessonTree = {
  bannerInfo?: any;
  catalogs: any[];
} | null;

export const useLessonTree = () => {
  const [tree, setTree] = useState<LessonTree>(null);
  const treeRef = useRef<LessonTree>(tree);

  useEffect(() => {
    treeRef.current = tree;
  }, [tree]);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);
  const { trackEvent } = useTracking();
  const { updateCourseId } = useEnvStore.getState();
  const isLoggedIn = useUserStore(state => state.isLoggedIn);
  const { openPayModal } = useCourseStore(
    useShallow(state => ({
      openPayModal: state.openPayModal,
    })),
  );

  const getCurrElement = useCallback(async () => {
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

  const initialSelectedChapter = useCallback(
    tree => {
      let catalog = tree.catalogs.find(
        v => v.status_value === LESSON_STATUS_VALUE.LEARNING,
      );
      let lesson;
      if (catalog) {
        lesson = catalog.lessons.find(
          v =>
            v.status_value === LESSON_STATUS_VALUE.LEARNING ||
            v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING,
        );
      } else {
        catalog = tree.catalogs.find(
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
        if (
          (lesson.type === LEARNING_PERMISSION.TRIAL ||
            lesson.type === LEARNING_PERMISSION.NORMAL) &&
          !isLoggedIn
        ) {
          window.location.href = `/login?redirect=${encodeURIComponent(location.pathname)}`;
          return;
        }

        if (lesson.type === LEARNING_PERMISSION.NORMAL && !lesson.is_paid) {
          openPayModal({
            type: lesson.type,
            payload: {
              chapterId: lesson.chapterId,
              lessonId: lesson.id,
            },
          });
          return;
        }
        setSelectedLessonId(lesson.id);
      }
    },
    [isLoggedIn, openPayModal],
  );

  const loadTreeInner = useCallback(async () => {
    setSelectedLessonId(null);
    const resp = await getLessonTree(
      useEnvStore.getState().courseId,
      useSystemStore.getState().previewMode,
    );

    const treeData = resp;
    if (!treeData) {
      return null;
    }

    // new api without course_id
    // if (treeData.course_id !== useEnvStore.getState().courseId) {
    //   await updateCourseId(treeData.course_id);
    // }

    let lessonCount = 0;
    const catalogs = (treeData.outline_items || []).map(l => {
      const lessons = l.children.map(c => {
        lessonCount += 1;
        return {
          id: c.bid,
          name: c.title,
          status: c.status,
          type: c.type,
          is_paid: c.is_paid,
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

    const newTree = {
      catalogCount: catalogs.length,
      catalogs,
      lessonCount,
      bannerInfo: treeData.banner_info,
    };

    return newTree;
  }, [updateCourseId]);

  const setSelectedState = useCallback((tree, chapterId, lessonId) => {
    const chapter = tree.catalogs.find(v => v.id === chapterId);

    if (!chapter) {
      return false;
    }

    let lesson = null;
    if (lessonId) {
      lesson = chapter.lessons.find(v => v.id === lessonId);
    }

    if (!lesson) {
      lesson = chapter.lessons.find(
        v =>
          v.status_value === LESSON_STATUS_VALUE.LEARNING ||
          v.status === LESSON_STATUS_VALUE.PREPARE_LEARNING,
      );
    }

    if (lesson) {
      const typedLesson = lesson as { id: string };
      setSelectedLessonId(typedLesson.id);
      return true;
    }
    return true;
  }, []);

  // Reload the course tree while preserving transient state
  const reloadTree = useCallback(
    async (chapterId = undefined, lessonId = undefined) => {
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
      let newTree: { bannerInfo?: any; catalogs: any[] } | null = null;
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

  const updateSelectedLesson = async (lessonId, forceExpand = false) => {
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

  const setCurrCatalog = async catalogId => {
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

  const toggleCollapse = ({ id }) => {
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

  const updateLesson = (id, val) => {
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

  const updateChapterStatus = (id, { status, status_value }) => {
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

  const getChapterByLesson = lessonId => {
    if (!tree) {
      return null;
    }
    const chapter = tree.catalogs.find(ch => {
      return ch.lessons.find(ls => ls.id === lessonId);
    });

    return chapter;
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

  const onTryLessonSelect = ({ lessonId }) => {
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
