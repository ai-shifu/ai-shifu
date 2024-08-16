import classNames from "classnames";
import CourseSection from "./CourseSection.jsx";
import styles from "./CourseCatalog.module.scss";

import { useState } from "react";

export const CourseCatalog = ({
  id = 0,
  name = "",
  lessons = [],
  collapse = false,
  onCollapse = ({ id }) => {},
  onLessonSelect = ({ id }) => {},
}) => {
  return (
    <div
      className={classNames(styles.courseCatalog, collapse && styles.collapse)}
    >
      <div className={styles.titleRow} onClick={() => onCollapse?.({id})}>
        <div>{name}</div>
        <img
          className={styles.collapseBtn}
          src={require("@Assets/newchat/light/icon16-arrow-down.png")}
          alt=""
        />
      </div>
      <div className={styles.sectionList}>
        {lessons.map((e) => {
          return (
            <CourseSection
              key={e.id}
              id={e.id}
              name={e.name}
              status={e.status}
              selected={e.selected}
              canLearning={e.canLearning}
              onSelect={onLessonSelect}
            />
          );
        })}
      </div>
    </div>
  );
};

export default CourseCatalog;
