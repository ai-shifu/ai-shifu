import React from 'react';
import s from './TimeBar.module.scss';

interface TimeBarProps {
  timestamp: number;
}

const TimeBar: React.FC<TimeBarProps> = ({ timestamp }) => {
  return <div className={s.timeBar}>{new Date(timestamp).toLocaleString()}</div>;
};

export default TimeBar;