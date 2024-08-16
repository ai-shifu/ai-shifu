// 课程目录
import CourseCatalog from "./CourseCatalog.jsx";
import styles from "./CourseCatalogList.module.scss";

export const CourseCatalogList = ({
  catalogs = [],
  catalogCount = 0,
  lessonCount = 0,
  onChapterCollapse = ({ id }) => {},
  onLessonSelect = ({ id }) => {},
}) => {
  return (
    <div className={styles.courseCatalogList}>
      <div className={styles.titleRow}>
        <div className={styles.titleArea}>
          <img
            className={styles.icon}
            src={require("@Assets/newchat/light/icon16-course-list.png")}
            alt="课程列表"
          />
          <div className={styles.titleName}>课程列表</div>
        </div>
        <div className={styles.chapterCount}>
          {lessonCount}节/{catalogCount}章
        </div>
      </div>
      <div className={styles.listRow}>
        {catalogs.map((catalog) => {
          return (
            <CourseCatalog
              key={catalog.id}
              id={catalog.id}
              name={catalog.name}
              lessons={catalog.lessons}
              collapse={catalog.collapse}
              onCollapse={onChapterCollapse}
              onLessonSelect={onLessonSelect}
            />
          );
        })}
      </div>
    </div>
  );
};

export default CourseCatalogList;
