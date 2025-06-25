import { useState, useCallback } from "react";
import { produce } from 'immer';
import { getLessonTree } from '@/c-api/lesson';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import { useTracking, EVENT_NAMES } from '@/c-common/hooks/useTracking';
import { useEnvStore } from '@/c-store/envStore';
import { useSystemStore } from '@/c-store/useSystemStore';

export const checkChapterCanLearning = ({ status_value }) => {
  const canLearn = status_value === LESSON_STATUS_VALUE.LEARNING ||
    status_value === LESSON_STATUS_VALUE.COMPLETED ||
    status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING;
    
  return canLearn
};

export const useLessonTree = () => {
  const [tree, setTree] = useState(null);
  const [selectedLessonId, setSelectedLessonId] = useState(null);
  const { trackEvent } = useTracking();
  const { updateCourseId } = useEnvStore.getState();

  const getCurrElement = useCallback(async () => {
    if (!tree || !selectedLessonId) {
      return { catalog: null, lesson: null }
    }
    // @ts-expect-error EXPECT
    for (const catalog of tree.catalogs) {
      const lesson = catalog.lessons.find(v => v.id === selectedLessonId);
      if (lesson) {
        return { catalog, lesson };
      }
    }
    return { catalog: null, lesson: null };
  }, [selectedLessonId, tree])

  const initialSelectedChapter = useCallback((tree) => {
    let catalog = tree.catalogs.find(v => v.status_value === LESSON_STATUS_VALUE.LEARNING);
    if (catalog) {
      const lesson = catalog.lessons.find(v => v.status_value === LESSON_STATUS_VALUE.LEARNING || v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING);
      // lesson && setSelectedLessonId(lesson.id);
      if (lesson) {
        setSelectedLessonId(lesson.id)
      }
    } else {
      catalog = tree.catalogs.find(v => v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING);
      if (catalog) {
        const lesson = catalog.lessons.find(v => v.status_value === LESSON_STATUS_VALUE.LEARNING || v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING);
        // lesson && setSelectedLessonId(lesson.id);
        if (lesson) {
           setSelectedLessonId(lesson.id)
        }
      }
    }
  }, []);

  const loadTreeInner = useCallback(async () => {
    setSelectedLessonId(null);
    const resp = await getLessonTree(useEnvStore.getState().courseId, useSystemStore.getState().previewMode);

    const treeData = resp.data;
    if (!treeData) {
      return null;
    }

    if (treeData.course_id !== useEnvStore.getState().courseId) {
      await updateCourseId(treeData.course_id);
    }

    let lessonCount = 0;
    const catalogs = treeData.lessons.map(l => {
      const lessons = l.children.map(c => {
        lessonCount += 1;
        return {
          id: c.lesson_id,
          name: c.lesson_name,
          status: c.status,
          status_value: c.status_value,
          canLearning: checkChapterCanLearning(c),
        };
      });

      return {
        id: l.lesson_id,
        name: l.lesson_name,
        status: l.status,
        status_value: l.status_value,
        lessons,
        collapse: false,
        bannerInfo: l.banner_info,
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
      lesson = chapter.lessons.find(v => v.status_value === LESSON_STATUS_VALUE.LEARNING || v.status === LESSON_STATUS_VALUE.PREPARE_LEARNING);
    }

    if (!lesson) {
      return false;
    }
    // @ts-expect-error EXPECT
    setSelectedLessonId(lesson.id);
    return true;
  }, []);

  // 用于重新加载课程树，但保持临时状态
  const reloadTree = useCallback(async (chapterId = undefined, lessonId = undefined) => {
    const newTree = await loadTreeInner();
    if (chapterId === undefined) {
      initialSelectedChapter(newTree);
    } else {
      setSelectedState(newTree, chapterId, lessonId);
    }
    // 设置 collapse 状态
    await newTree?.catalogs.forEach(c => {
      // @ts-expect-error EXPECT
      const oldCatalog = tree?.catalogs.find(oc => oc.id === c.id);

      if (oldCatalog) {
        c.collapse = oldCatalog.collapse;
      }
    });
    // @ts-expect-error EXPECT
    setTree(newTree);
    return newTree;
  }, [loadTreeInner, tree, initialSelectedChapter, setSelectedState]);

  const loadTree = useCallback(async (chapterId = '', lessonId = '') => {
    let newTree = null;
    if (!tree) {
      // @ts-expect-error EXPECT
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
  }, [initialSelectedChapter, loadTreeInner, setSelectedState, tree]);

  const updateSelectedLesson = async (lessonId, forceExpand = false) => {
    setSelectedLessonId(lessonId);
    // @ts-expect-error EXPECT
    setTree(old => {
      if (!old) {
        return;
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

  const setCurrCatalog = async (catalogId) => {
    if (!tree) {
      return;
    }
    // @ts-expect-error EXPECT
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
      // @ts-expect-error EXPECT
      draft.catalogs.forEach(c => {
        if (c.id === id) {
          c.collapse = !c.collapse;
        }
      });
    });

    setTree(nextState);
  };

  const updateLesson = (id, val) => {
    // @ts-expect-error EXPECT
    setTree(old => {
      if (!old) {
        return;
      }

      const nextState = produce(old, draft => {
        draft.catalogs.forEach(c => {
          const idx = c.lessons.findIndex(ch => ch.id === id);
          if (idx !== -1) {
            const newLesson = {
              ...c.lessons[idx],
              ...val
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
    // @ts-expect-error EXPECT
    setTree(old => {
      if (!old) {
        return;
      }

      const nextState = produce(old, draft => {
        const idx = draft.catalogs.findIndex(ch => ch.id === id);
        if (idx !== -1) {
          draft.catalogs[idx] = {
            ...draft.catalogs[idx],
            status,
            status_value
          };
        }
      });

      return nextState;
    });
  };

  const getChapterByLesson = (lessonId) => {
    // @ts-expect-error EXPECT
    const chapter = tree.catalogs.find(ch => {
      return ch.lessons.find(ls => ls.id === lessonId);
    });

    return chapter;
  };

  const onTryLessonSelect = ({ lessonId }) => {
    if (!tree) {
      return;
    }

    let from = '';
    let to = '';
    // @ts-expect-error EXPECT
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
  };
};
