-- MySQL dump 10.13  Distrib 8.0.23, for osx10.16 (x86_64)
--
-- Host: 127.0.0.1    Database: ai_asistant
-- ------------------------------------------------------
-- Server version	8.0.32

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `chat_info`
--

--
-- Table structure for table `risk_control_result`
--

DROP TABLE IF EXISTS `risk_control_result`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `risk_control_result` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `chat_id` char(36) NOT NULL DEFAULT '' COMMENT 'Chat UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `text` text NOT NULL COMMENT 'Text',
  `check_vendor` varchar(255) NOT NULL DEFAULT '' COMMENT 'Check vendor',
  `check_result` int NOT NULL DEFAULT '0' COMMENT 'Check result',
  `check_resp` text NOT NULL COMMENT 'Check response',
  `is_pass` int NOT NULL DEFAULT '0' COMMENT 'Is pass',
  `check_strategy` varchar(30) NOT NULL DEFAULT '' COMMENT 'Check strategy',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_chat_id_risk_control_result` (`chat_id`),
  KEY `idx_user_id_risk_control_result` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=316 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_info`
--

DROP TABLE IF EXISTS `user_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `username` varchar(255) NOT NULL DEFAULT '' COMMENT 'Login username',
  `name` varchar(255) NOT NULL DEFAULT '' COMMENT 'User real name',
  `password_hash` varchar(255) NOT NULL DEFAULT '' COMMENT 'Hashed password',
  `email` varchar(255) NOT NULL DEFAULT '' COMMENT 'Email',
  `mobile` varchar(20) NOT NULL DEFAULT '' COMMENT 'Mobile',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `default_model` varchar(50) NOT NULL DEFAULT 'gpt-4-0613' COMMENT 'gpt model ',
  PRIMARY KEY (`id`),
  KEY `idx_username_user_info` (`username`),
  KEY `idx_email_user_info` (`email`),
  KEY `idx_mobile_user_info` (`mobile`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2023-08-14 18:45:48


CREATE TABLE chat_img (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
    img_id CHAR(36) NOT NULL DEFAULT '' COMMENT 'Image UUID',
    chat_id CHAR(36) NOT NULL DEFAULT '' COMMENT 'Chat UUID',
    user_id CHAR(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
    bucket_id CHAR(36) NOT NULL DEFAULT '' COMMENT 'Bucket UUID',
    prompt TEXT NOT NULL COMMENT 'Prompt for the image',
    size VARCHAR(50) NOT NULL DEFAULT '' COMMENT 'Size of the image',
    url TEXT NOT NULL COMMENT 'URL of the image',
    bucket_base TEXT NOT NULL COMMENT 'Bucket Base URL',
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
    updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
    PRIMARY KEY (id),
    INDEX idx_img_id_image_table (img_id),
    INDEX idx_chat_id_image_table (chat_id),
    INDEX idx_user_id_image_table (user_id)
);




create table user_profile(
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `profile_key` varchar(255) NOT NULL DEFAULT '' COMMENT 'Profile key',
  `profile_value` text NOT NULL COMMENT 'Profile value',
  `profile_type` int NOT NULL DEFAULT '0' COMMENT '0 默认,1 系统配置,2 用户配置，3 课程配置',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `status` int NOT NULL DEFAULT '0' COMMENT '0 for deleted, 1 for active',
  PRIMARY KEY (`id`),
  KEY `idx_user_id_user_profile` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4; 

create table ai_course(
`id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
`course_id` char(36) NOT NULL DEFAULT '' COMMENT 'Course UUID',
`course_name` varchar(255) NOT NULL DEFAULT '' COMMENT 'Course name',
`course_desc` text NOT NULL COMMENT 'Course description',
`course_price` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT 'Course price',
`course_status` int NOT NULL DEFAULT '0' COMMENT 'Course status',
`course_feishu_id` varchar(255) NOT NULL DEFAULT '' COMMENT 'Course feishu ID',
`created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
`updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
`status` int NOT NULL DEFAULT '0' COMMENT 'Status of the course',
PRIMARY KEY (`id`),
KEY `idx_course_id_ai_course` (`course_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


create table ai_lesson(
`id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
`lesson_id` char(36) NOT NULL DEFAULT '' COMMENT 'Lesson UUID',
`course_id` char(36) NOT NULL DEFAULT '' COMMENT 'Course UUID',
`lesson_name` varchar(255) NOT NULL DEFAULT '' COMMENT 'Lesson name',
`lesson_desc` text NOT NULL COMMENT 'Lesson description',
`lesson_no` varchar(32) NULL DEFAULT '0' COMMENT 'Lesson number',
`lesson_index` int NOT NULL DEFAULT '0' COMMENT 'Lesson index',
`lesson_sale_type` int NOT NULL DEFAULT '0' COMMENT '0 默认 1 体验课 2 系统课 3 扩展课',
`lesson_type` int NOT NULL DEFAULT '0' COMMENT '0 默认 1 体验课 2 系统课 3 扩展课',
`lesson_feishu_id` varchar(255) NOT NULL DEFAULT '' COMMENT 'Lesson feishu ID',
`lesson_status` int NOT NULL DEFAULT '0' COMMENT 'Lesson status',
`created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
`updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
`status` int NOT NULL DEFAULT '0' COMMENT 'Status of the lesson',
PRIMARY KEY (`id`),
KEY `idx_lesson_id_ai_lesson` (`lesson_id`),
KEY `idx_course_id_ai_lesson` (`course_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;



create table ai_lesson_script(
`id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
`script_id` char(36) NOT NULL DEFAULT '' COMMENT 'Script UUID',
`lesson_id` char(36) NOT NULL DEFAULT '' COMMENT 'Lesson UUID',
`script_name` varchar(255) NOT NULL DEFAULT '' COMMENT 'Script name',
`script_desc` text NOT NULL COMMENT 'Script description',
`script_index` int NOT NULL DEFAULT '0' COMMENT 'Script index',
`script_feishu_id` varchar(255) NOT NULL DEFAULT '' COMMENT 'Script feishu ID',
`script_version` int NOT NULL DEFAULT '0' COMMENT 'Script version',
`script_no` int NOT NULL DEFAULT '0' COMMENT 'Script number',
`script_type` int NOT NULL DEFAULT '0' COMMENT 'Script type',
`script_content_type` int NOT NULL DEFAULT '0' COMMENT 'Script content type',
`script_prompt` text NOT NULL COMMENT 'Script content',
`script_model` char(36) NOT NULL DEFAULT '' COMMENT 'Script model',
`script_profile` text NOT NULL COMMENT 'Script profile',
`script_media_url` text NOT NULL COMMENT 'Script media URL',
`script_ui_type` int NOT NULL DEFAULT '0' COMMENT 'Script UI type',
`script_ui_content` text NOT NULL COMMENT 'Script UI content',
`script_check_prompt` text NOT NULL COMMENT 'Script check prompt',
`script_check_flag` int NOT NULL DEFAULT '0' COMMENT 'Script check type',
`script_ui_profile` text NOT NULL COMMENT 'Script check content',
`script_end_action` text NOT NULL COMMENT 'Script end action',
`script_other_conf` text NOT NULL COMMENT '脚本的其他配置',
`created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
`updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
`status` int NOT NULL DEFAULT '0' COMMENT 'Status of the script',
PRIMARY KEY (`id`),
KEY `idx_script_id_ai_lesson_script` (`script_id`),
KEY `idx_lesson_id_ai_lesson_script` (`lesson_id`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;



create table ai_course_buy_record(
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `record_id` char(36) NOT NULL DEFAULT '' COMMENT 'Record UUID',
  `course_id` char(36) NOT NULL DEFAULT '' COMMENT 'Course UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `price` decimal(10,2) NOT NULL DEFAULT '0.00' COMMENT 'Price of the course',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the record',
  PRIMARY KEY (`id`),
  KEY `idx_record_id_ai_course_buy_record` (`record_id`),
  KEY `idx_course_id_ai_course_buy_record` (`course_id`),
  KEY `idx_user_id_ai_course_buy_record` (`user_id`)
)

create table ai_course_lesson_attend(
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `attend_id` char(36) NOT NULL DEFAULT '' COMMENT 'Attend UUID',
  `lesson_id` char(36) NOT NULL DEFAULT '' COMMENT 'Lesson UUID',
  `course_id` char(36) NOT NULL DEFAULT '' COMMENT 'Course UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the attend 0-未开始 1-进行中 2-已结束',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_attend_id_ai_course_lesson_attend` (`attend_id`),
  KEY `idx_lesson_id_ai_course_lesson_attend` (`lesson_id`),
  KEY `idx_course_id_ai_course_lesson_attend` (`course_id`),
  KEY `idx_user_id_ai_course_lesson_attend` (`user_id`)
);

create table ai_course_lesson_attendscript(
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `attend_id` char(36) NOT NULL DEFAULT '' COMMENT 'Attend UUID',
  `script_id` char(36) NOT NULL DEFAULT '' COMMENT 'Script UUID',
  `lesson_id` char(36) NOT NULL DEFAULT '' COMMENT 'Lesson UUID',
  `course_id` char(36) NOT NULL DEFAULT '' COMMENT 'Course UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `script_index` int NOT NULL DEFAULT '0' COMMENT 'Script index',
  `script_role` int NOT NULL DEFAULT '0' COMMENT 'Script role',
  `script_content` text NOT NULL COMMENT 'Script content',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the attend',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_attend_id_ai_course_lesson_attendscript` (`attend_id`),
  KEY `idx_script_id_ai_course_lesson_attendscript` (`script_id`),
  KEY `idx_lesson_id_ai_course_lesson_attendscript` (`lesson_id`),
  KEY `idx_course_id_ai_course_lesson_attendscript` (`course_id`),
  KEY `idx_user_id_ai_course_lesson_attendscript` (`user_id`)
  
)

create table ai_course_lesson_generation(
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `generation_id` char(36) NOT NULL DEFAULT '' COMMENT 'Generation UUID',
  `lesson_id` char(36) NOT NULL DEFAULT '' COMMENT 'Lesson UUID',
  `course_id` char(36) NOT NULL DEFAULT '' COMMENT 'Course UUID',
  `script_id` char(36) NOT NULL DEFAULT '' COMMENT 'Script UUID',
  `attend_id` char(36) NOT NULL DEFAULT '' COMMENT 'Attend UUID',
  `model` varchar(50) NOT NULL DEFAULT '' COMMENT 'Model of the generation',
  `prompt` text NOT NULL COMMENT 'Prompt for the generation',
  `content` text NOT NULL COMMENT 'Content of the generation',
  `input_tokens` int not NULL DEFAULT 0 COMMENT 'Input tokens of the generation',
  `output_tokens` int not NULL DEFAULT 0 COMMENT 'Output tokens of the generation',
  `index` int NOT NULL DEFAULT '0' COMMENT 'Index of the generation',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the generation',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_generation_id_ai_course_lesson_generation` (`generation_id`),
  KEY `idx_lesson_id_ai_course_lesson_generation` (`lesson_id`),
  KEY `idx_course_id_ai_course_lesson_generation` (`course_id`),
  KEY `idx_script_id_ai_course_lesson_generation` (`script_id`),
  KEY `idx_attend_id_ai_course_lesson_generation` (`attend_id`),
  KEY `idx_user_id_ai_course_lesson_generation` (`user_id`)
)