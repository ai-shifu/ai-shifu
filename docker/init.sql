CREATE DATABASE IF NOT EXISTS `ai-shifu-cook`;
USE `ai-shifu-cook`;

-- check table chapters_follow_up_ask_prompt
CREATE TABLE IF NOT EXISTS `chapters_follow_up_ask_prompt` (
  `lark_app_token` varchar(64) NOT NULL,
  `lark_table_id` varchar(32) NOT NULL,
  `prompt_template` text NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- check table courses
CREATE TABLE IF NOT EXISTS `courses` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_name` varchar(24) NOT NULL,
  `course_name` varchar(64) NOT NULL,
  `lark_app_token` varchar(64) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb4;
