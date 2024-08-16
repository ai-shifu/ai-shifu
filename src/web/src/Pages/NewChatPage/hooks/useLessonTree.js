import { useState } from "react";
import { getLessonTree } from '@Api/lesson.js';
import { produce } from 'immer';
import { LESSON_STATUS } from "@constants/courseConstants.js";

export const checkChapterCanLearning = ({ status }) => {
  return status === LESSON_STATUS.LEARNING || status === LESSON_STATUS.COMPLETED || status === LESSON_STATUS.PREPARE_LEARNING;
}

export const checkChapterAvaiableStatic = (tree, chapterId) => {
  const catalog = tree.catalogs.find(v => v.id === chapterId);

  if (!catalog) {
    return false;
  }

  return catalog.status === LESSON_STATUS.LEARNING || catalog.status === LESSON_STATUS.COMPLETED || catalog.status === LESSON_STATUS.PREPARE_LEARNING;
}

const getCurrElementStatic = (tree) => {
  for (let catalog of tree.catalogs) {
    const lesson = catalog.lessons.find(v => v.selected === true);

    if (lesson) {
      return { catalog, lesson };
    }
  }

  return null;
}

export const initialSelectedChapter = (tree) => {
  let catalog = tree.catalogs.find(v => v.status === LESSON_STATUS.LEARNING);
  if (catalog) {
    const lesson = catalog.lessons.find(v => v.status === LESSON_STATUS.LEARNING || v.status === LESSON_STATUS.PREPARE_LEARNING);
    lesson && (lesson.selected = true);
  } else {
    catalog = tree.catalogs.find(v => v.status === LESSON_STATUS.PREPARE_LEARNING);
    if (catalog) {
      const lesson = catalog.lessons.find(v => v.status === LESSON_STATUS.LEARNING || v.status === LESSON_STATUS.PREPARE_LEARNING);
      lesson && (lesson.selected = true);
    }
  }
}

export const useLessonTree = () => {
  const [tree, setTree] = useState(null);

  const loadTreeInner = async () => {
    const resp = await getLessonTree();
    const treeData = resp.data;

    let lessonCount = 0;
    const catalogs = treeData.lessons.map(l => {
      const lessons = l.children.map(c => {
        lessonCount += 1;
        return {
          id: c.lesson_id,
          name: c.lesson_name,
          status: c.status,
          canLearning: checkChapterCanLearning(c),
        }
      });

      return {
        id: l.lesson_id,
        name: l.lesson_name,
        status: l.status,
        lessons,
        collapse: false,
      };
    });

    const newTree = {
      catalogCount: catalogs.length,
      catalogs,
      lessonCount,
    }

    return newTree;
  }

  const clearSelectedStateStatic = (tree) => {
    tree.catalogs.forEach(c => {
      c.lessons.forEach(l => {
        l.selected = false;
      })
    })
  }

  const setSelectedStateStatic = (tree, chapterId, lessonId) => {
    let selectedCorrect = false;
    const chapter = tree.catalogs.find(v => v.id === chapterId);
    if (!chapter) {
      return
    }

    let lesson = null;
    if (lessonId) {
      lesson = chapter.lessons.find(v => v.id === lessonId);
    }

    if (!lesson) {
      lesson = chapter.lessons.find(v => v.status === LESSON_STATUS.LEARNING || v.status === LESSON_STATUS.PREPARE_LEARNING);
    }

    if (!lesson) {
      return
    }

    clearSelectedStateStatic(tree);
    lesson.selected = true;
    selectedCorrect = true;

    return selectedCorrect
  }

  // 用于重新加载课程树，但保持临时状态
  const reloadTree = async (chapterId = 0, lessonId = 0) => {
    const newTree = await loadTreeInner();
    const { lesson } = getCurrElementStatic(tree);

    const selected = setSelectedStateStatic(newTree, chapterId, lessonId);

    if (!selected) {
      // 设置当前选中的元素
      newTree.catalogs.forEach(c => {
        c.lessons.forEach(ls => {
          if (ls.id === lesson.id) {
            ls.selected = true;
          }
        })
      });
    }

    // 设置 collapse 状态
    newTree.catalogs.forEach(c => {
      const oldCatalog = tree.catalogs.find(oc => oc.id === c.id);

      if (oldCatalog) {
        c.collapse = oldCatalog.collapse;
      }
    });

    setTree(newTree);

    return newTree;
  }

  const loadTree = async (chapterId = 0, lessonId = 0) => {
    const newTree = await loadTreeInner();
    const selected = setSelectedStateStatic(newTree, chapterId, lessonId);

    if (!selected) {
      initialSelectedChapter(newTree);
    }
    setTree(newTree);

    return newTree;
  }

  const updateSelectedLesson = async (lessonId, forceExpand = false) => {
    setTree(old => {
      if (!old) {
        return
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
  }

  const setCurrCatalog = async (catalogId) => {
    if (!tree) {
      return
    }

    const ca = tree.catalogs.find(c => c.id === catalogId);
    if (!ca) {
      return
    }

    const l = ca.lessons[0];
    if (!l) {
      return
    }

    updateSelectedLesson(l.id);
  }

  const toggleCollapse = ({ id }) => {
    const nextState = produce(tree, draft => {
      draft.catalogs.forEach(c => {
        if (c.id === id) {
          c.collapse = !c.collapse;
        }
      })
    });

    setTree(nextState);
  }

  const getCurrElement = () => {
    if (!tree) {
      return null;
    }

    return getCurrElementStatic(tree);
  }

  const updateChapter = (id, val) => {
    setTree(old => {
      if (!old) {
        return
      }
      const nextState = produce(old, draft => {
        draft.catalogs.forEach(c => {
          const idx = c.lessons.findIndex(ch => ch.id === id)
          if (idx !== -1) {
            const newLesson = {
              ...c.lessons[idx],
              ...val
            };
            newLesson.canLearning = checkChapterCanLearning(newLesson);
            c.lessons[idx] = newLesson;
          }
        })
      });

      return nextState;
    });
  }

  const getChapterByLesson = (lessonId) => {
    const chapter = tree.catalogs.find(ch => {
      return ch.lessons.find(ls => ls.id === lessonId)
    })

    return chapter;
  }


  return {
    tree,
    loadTree,
    reloadTree,
    updateSelectedLesson,
    setCurrCatalog,
    toggleCollapse,
    checkChapterAvaiableStatic,
    getCurrElement,
    updateChapter,
    getCurrElementStatic,
    getChapterByLesson,
  }
}
