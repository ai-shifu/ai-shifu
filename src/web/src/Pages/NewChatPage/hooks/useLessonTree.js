import { useState } from "react";
import { getLessonTree } from 'Api/lesson.js';
import { produce } from 'immer';
import { LESSON_STATUS_VALUE} from "constants/courseConstants.js";
import { useTracking, EVENT_NAMES } from "common/hooks/useTracking.js";
import { useSystemStore } from 'stores/useSystemStore.js';
import { useUserStore } from 'stores/useUserStore.js';
import { useEnvStore } from 'stores/envStore.js';
export const checkChapterCanLearning = ({ status }) => {
  return status === LESSON_STATUS_VALUE.LEARNING || status === LESSON_STATUS_VALUE.COMPLETED || status === LESSON_STATUS_VALUE.PREPARE_LEARNING;
};

export const checkChapterAvaiableStatic = (tree, chapterId) => {
  const catalog = tree.catalogs.find(v => v.id === chapterId);



  if (!catalog) {
    return false;
  }

  return catalog.status_value === LESSON_STATUS_VALUE.LEARNING || catalog.status_value === LESSON_STATUS_VALUE.COMPLETED || catalog.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING;
};

const getCurrElementStatic = async(tree) => {
  for (const catalog of tree.catalogs) {
    const lesson = catalog.lessons.find(v => v.selected === true);
    if (lesson) {
      return { catalog, lesson };
    }
  }
  return {catalog:null,lesson:null};
};

export const initialSelectedChapter = (tree) => {
  let catalog = tree.catalogs.find(v => v.status_value === LESSON_STATUS_VALUE.LEARNING);
  if (catalog) {
    const lesson = catalog.lessons.find(v => v.status_value === LESSON_STATUS_VALUE.LEARNING || v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING);
    lesson && (lesson.selected = true);
  } else {
    catalog = tree.catalogs.find(v => v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING);
    if (catalog) {
      const lesson = catalog.lessons.find(v => v.status_value === LESSON_STATUS_VALUE.LEARNING || v.status_value === LESSON_STATUS_VALUE.PREPARE_LEARNING);
      lesson && (lesson.selected = true);
    }
  }
};

export const useLessonTree = () => {
  const { trackEvent } = useTracking();
  const [tree, setTree] = useState(null);
  const { checkLogin } = useUserStore();
  const { updateCourseId } = useEnvStore.getState();
  const loadTreeInner = async () => {
    let resp;
    try {
      resp = await getLessonTree(useEnvStore.getState().courseId);
    } catch (err) {
      await checkLogin();
      resp = await getLessonTree(useEnvStore.getState().courseId);
    }

    const treeData = resp.data;
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
          status_value:c.status_value,
          canLearning: checkChapterCanLearning(c),
        };
      });

      return {
        id: l.lesson_id,
        name: l.lesson_name,
        status: l.status,
        status_value:l.status_value,
        lessons,
        collapse: false,
      };
    });

    const newTree = {
      catalogCount: catalogs.length,
      catalogs,
      lessonCount,
    };
    return newTree;
  };

  const clearSelectedStateStatic = (tree) => {
    tree.catalogs.forEach(c => {
      c.lessons.forEach(l => {
        l.selected = false;
      });
    });
  };

  const setSelectedStateStatic = (tree, chapterId, lessonId) => {
    let selectedCorrect = false;
    const chapter = tree.catalogs.find(v => v.id === chapterId);
    if (!chapter) {
      return;
    }

    let lesson = null;
    if (lessonId) {
      lesson = chapter.lessons.find(v => v.id === lessonId);
    }

    if (!lesson) {
      lesson = chapter.lessons.find(v => v.status_value === LESSON_STATUS_VALUE.LEARNING || v.status === LESSON_STATUS_VALUE.PREPARE_LEARNING);
    }

    if (!lesson) {
      return;
    }

    clearSelectedStateStatic(tree);
    lesson.selected = true;
    selectedCorrect = true;

    return selectedCorrect;
  };

  // 用于重新加载课程树，但保持临时状态
  const reloadTree = async (chapterId = 0, lessonId = 0) => {
    const newTree = await loadTreeInner();
    const { lesson } = await getCurrElementStatic(tree);
    const selected = setSelectedStateStatic(newTree, chapterId, lessonId);
    if (!selected) {
      // 设置当前选中的元素
      newTree.catalogs.forEach(c => {
        c.lessons.forEach(ls => {
          if (ls.id === lesson.id) {
            ls.selected = true;
          }
        });
      });
    }
    // 设置 collapse 状态
    await newTree.catalogs.forEach(c => {
      const oldCatalog = tree.catalogs.find(oc => oc.id === c.id);

      if (oldCatalog) {
        c.collapse = oldCatalog.collapse;
      }
    });
    setTree(newTree);
    return newTree;
  };

  const loadTree = async (chapterId = 0, lessonId = 0) => {
    const newTree = await loadTreeInner();
    const selected = setSelectedStateStatic(newTree, chapterId, lessonId);
    if (!selected) {
      initialSelectedChapter(newTree);
    }
    setTree(newTree);

    return newTree;
  };

  const updateSelectedLesson = async (lessonId, forceExpand = false) => {
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
              ls.selected = true;
            } else {
              ls.selected = false;
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
      draft.catalogs.forEach(c => {
        if (c.id === id) {
          c.collapse = !c.collapse;
        }
      });
    });

    setTree(nextState);
  };

  const getCurrElement = () => {
    if (!tree) {
      return null;
    }

    return getCurrElementStatic(tree);
  };

  const updateLesson = (id, val) => {
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

  const updateChapterStatus = (id, { status,status_value }) => {
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

    for (const catalog of tree.catalogs) {
      const lesson = catalog.lessons.find(v => v.selected === true);

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
    loadTree,
    reloadTree,
    updateSelectedLesson,
    setCurrCatalog,
    toggleCollapse,
    checkChapterAvaiableStatic,
    getCurrElement,
    updateLesson,
    updateChapterStatus,
    getCurrElementStatic,
    getChapterByLesson,
    onTryLessonSelect,
  };
};
