-- MySQL dump 10.13  Distrib 5.7.24, for osx11.1 (x86_64)
--
-- Host: 127.0.0.1    Database: ai_asistant
-- ------------------------------------------------------
-- Server version	8.0.32

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `ai_course`
--

DROP TABLE IF EXISTS `ai_course`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ai_course` (
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
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ai_course_buy_record`
--

DROP TABLE IF EXISTS `ai_course_buy_record`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ai_course_buy_record` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ai_course_lesson_attend`
--

DROP TABLE IF EXISTS `ai_course_lesson_attend`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ai_course_lesson_attend` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `attend_id` char(36) NOT NULL DEFAULT '' COMMENT 'Attend UUID',
  `lesson_id` char(36) NOT NULL DEFAULT '' COMMENT 'Lesson UUID',
  `course_id` char(36) NOT NULL DEFAULT '' COMMENT 'Course UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the attend 0-未开始 1-进行中 2-已结束',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `script_index` int NOT NULL DEFAULT '0' COMMENT 'script index',
  PRIMARY KEY (`id`),
  KEY `idx_attend_id_ai_course_lesson_attend` (`attend_id`),
  KEY `idx_lesson_id_ai_course_lesson_attend` (`lesson_id`),
  KEY `idx_course_id_ai_course_lesson_attend` (`course_id`),
  KEY `idx_user_id_ai_course_lesson_attend` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ai_course_lesson_attendscript`
--

DROP TABLE IF EXISTS `ai_course_lesson_attendscript`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ai_course_lesson_attendscript` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ai_course_lesson_generation`
--

DROP TABLE IF EXISTS `ai_course_lesson_generation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ai_course_lesson_generation` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `generation_id` char(36) NOT NULL DEFAULT '' COMMENT 'Generation UUID',
  `lesson_id` char(36) NOT NULL DEFAULT '' COMMENT 'Lesson UUID',
  `course_id` char(36) NOT NULL DEFAULT '' COMMENT 'Course UUID',
  `script_id` char(36) NOT NULL DEFAULT '' COMMENT 'Script UUID',
  `attend_id` char(36) NOT NULL DEFAULT '' COMMENT 'Attend UUID',
  `model` varchar(50) NOT NULL DEFAULT '' COMMENT 'Model of the generation',
  `prompt` text NOT NULL COMMENT 'Prompt for the generation',
  `content` text NOT NULL COMMENT 'Content of the generation',
  `input_tokens` int NOT NULL DEFAULT '0' COMMENT 'Input tokens of the generation',
  `output_tokens` int NOT NULL DEFAULT '0' COMMENT 'Output tokens of the generation',
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ai_lesson`
--

DROP TABLE IF EXISTS `ai_lesson`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ai_lesson` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `lesson_id` char(36) NOT NULL DEFAULT '' COMMENT 'Lesson UUID',
  `course_id` char(36) NOT NULL DEFAULT '' COMMENT 'Course UUID',
  `lesson_name` varchar(255) NOT NULL DEFAULT '' COMMENT 'Lesson name',
  `lesson_desc` text NOT NULL COMMENT 'Lesson description',
  `lesson_no` varchar(32) DEFAULT '0' COMMENT 'Lesson number',
  `lesson_index` int NOT NULL DEFAULT '0' COMMENT 'Lesson index',
  `lesson_sale_type` int NOT NULL DEFAULT '0' COMMENT '0 默认 1 体验课 2 系统课 3 扩展课',
  `lesson_type` int NOT NULL DEFAULT '0' COMMENT '0 默认 1 体验课 2 系统课 3 扩展课',
  `lesson_feishu_id` varchar(255) NOT NULL DEFAULT '' COMMENT 'Lesson feishu ID',
  `lesson_status` int NOT NULL DEFAULT '0' COMMENT 'Lesson status',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the lesson',
  `pre_lesson_no` varchar(255) NOT NULL DEFAULT '' COMMENT 'pre lesson no',
  PRIMARY KEY (`id`),
  KEY `idx_lesson_id_ai_lesson` (`lesson_id`),
  KEY `idx_course_id_ai_lesson` (`course_id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ai_lesson_script`
--

DROP TABLE IF EXISTS `ai_lesson_script`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ai_lesson_script` (
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
  `script_check_flag` text,
  `script_ui_profile` text NOT NULL COMMENT 'Script check content',
  `script_end_action` text NOT NULL COMMENT 'Script end action',
  `script_other_conf` text NOT NULL COMMENT '脚本的其他配置',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the script',
  PRIMARY KEY (`id`),
  KEY `idx_script_id_ai_lesson_script` (`script_id`),
  KEY `idx_lesson_id_ai_lesson_script` (`lesson_id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `chat_img`
--

DROP TABLE IF EXISTS `chat_img`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `chat_img` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `img_id` char(36) NOT NULL DEFAULT '' COMMENT 'Image UUID',
  `chat_id` char(36) NOT NULL DEFAULT '' COMMENT 'Chat UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `bucket_id` char(36) NOT NULL DEFAULT '' COMMENT 'Bucket UUID',
  `prompt` text NOT NULL COMMENT 'Prompt for the image',
  `size` varchar(50) NOT NULL DEFAULT '' COMMENT 'Size of the image',
  `url` text NOT NULL COMMENT 'URL of the image',
  `bucket_base` text NOT NULL COMMENT 'Bucket Base URL',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_img_id_image_table` (`img_id`),
  KEY `idx_chat_id_image_table` (`chat_id`),
  KEY `idx_user_id_image_table` (`user_id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `chat_info`
--

DROP TABLE IF EXISTS `chat_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `chat_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `chat_id` char(36) NOT NULL DEFAULT '' COMMENT 'Chat UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `chat_title` varchar(255) NOT NULL DEFAULT '' COMMENT 'Title of the chat',
  `tokens` varchar(255) NOT NULL DEFAULT '' COMMENT 'Tokens',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the chat',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_chat_id_chat_info` (`chat_id`),
  KEY `idx_user_id_chat_info` (`user_id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `chat_msg`
--

DROP TABLE IF EXISTS `chat_msg`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `chat_msg` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `chat_id` char(36) NOT NULL DEFAULT '' COMMENT 'Chat UUID',
  `tokens` varchar(255) NOT NULL DEFAULT '' COMMENT 'Tokens',
  `role` varchar(255) NOT NULL DEFAULT '' COMMENT 'Role in the chat',
  `type` varchar(255) NOT NULL DEFAULT '' COMMENT 'Type of the message',
  `msg` text NOT NULL COMMENT 'Message content',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the message',
  `function_info` text NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_chat_id_chat_msg` (`chat_id`)
) ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `classroom_online_count`
--

DROP TABLE IF EXISTS `classroom_online_count`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `classroom_online_count` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `room_id` varchar(255) NOT NULL COMMENT 'Room ID',
  `live_count` int NOT NULL COMMENT 'Live Count',
  `create_time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation Time',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=46461 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `contact`
--

DROP TABLE IF EXISTS `contact`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `contact` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `contact_id` char(36) NOT NULL DEFAULT '' COMMENT 'Contact UUID',
  `name` varchar(255) NOT NULL DEFAULT '' COMMENT 'Name',
  `email` varchar(255) NOT NULL DEFAULT '' COMMENT 'Email',
  `mobile` varchar(20) NOT NULL DEFAULT '' COMMENT 'Mobile',
  `telephone` varchar(20) NOT NULL DEFAULT '' COMMENT 'Telephone',
  `position` varchar(255) NOT NULL DEFAULT '' COMMENT 'Position',
  `company` varchar(255) NOT NULL DEFAULT '' COMMENT 'Company',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'user_id',
  PRIMARY KEY (`id`),
  KEY `idx_contact_id_contact` (`contact_id`),
  KEY `id_user_id` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=80 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `document`
--

DROP TABLE IF EXISTS `document`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `document` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `document_id` char(36) NOT NULL DEFAULT '' COMMENT 'Document UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `title` varchar(255) NOT NULL DEFAULT '' COMMENT 'Document title',
  `content` text NOT NULL COMMENT 'Document content in Markdown',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_user_id_document` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=29 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `family_info`
--

DROP TABLE IF EXISTS `family_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `family_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `family_id` char(36) NOT NULL DEFAULT '' COMMENT 'Family UUID',
  `family_name` varchar(255) NOT NULL DEFAULT '' COMMENT 'Family name',
  `address` text NOT NULL COMMENT 'Address',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_family_id_family_info` (`family_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `lesson`
--

DROP TABLE IF EXISTS `lesson`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `lesson` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `title` varchar(255) NOT NULL COMMENT 'Title',
  `start` varchar(255) DEFAULT NULL,
  `room_id` varchar(255) NOT NULL COMMENT 'Room ID',
  `document_id` varchar(255) NOT NULL COMMENT 'Document ID',
  `max_live_count` int NOT NULL COMMENT 'Maximum Live Count',
  `number` int NOT NULL COMMENT 'Number',
  `season` int NOT NULL COMMENT 'Season',
  `outlines` text COMMENT 'Outlines',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=57 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `risk_control_result`
--

DROP TABLE IF EXISTS `risk_control_result`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=687 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `room_info`
--

DROP TABLE IF EXISTS `room_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `room_info` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `room_id` char(36) NOT NULL DEFAULT '' COMMENT 'Room UUID',
  `family_id` char(36) NOT NULL DEFAULT '' COMMENT 'Family UUID',
  `room_name` varchar(255) NOT NULL DEFAULT '' COMMENT 'Room name',
  `room_type` int NOT NULL DEFAULT '0' COMMENT 'Type of the room',
  `room_note` text NOT NULL COMMENT 'Note of the room',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_room_id_room_info` (`room_id`),
  KEY `idx_family_id_room_info` (`family_id`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `room_msg`
--

DROP TABLE IF EXISTS `room_msg`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `room_msg` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `room_id` varchar(255) NOT NULL COMMENT 'Room ID',
  `user_name` varchar(255) NOT NULL COMMENT 'User Name',
  `time` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Time of Message',
  `user_msg` text NOT NULL COMMENT 'User Message',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status',
  `msg_id` varchar(255) NOT NULL DEFAULT '' COMMENT 'Message ID',
  `doc_id` varchar(255) NOT NULL DEFAULT '' COMMENT 'Document ID',
  `embeddings` blob COMMENT 'Embeddings',
  PRIMARY KEY (`id`),
  KEY `idx_msg_id_room_msg` (`msg_id`)
) ENGINE=InnoDB AUTO_INCREMENT=8047 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `todo`
--

DROP TABLE IF EXISTS `todo`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `todo` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `todo_id` char(36) NOT NULL DEFAULT '' COMMENT 'Todo UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `title` varchar(255) NOT NULL DEFAULT '' COMMENT 'Todo title',
  `description` text NOT NULL COMMENT 'Todo description',
  `is_done` int NOT NULL DEFAULT '0' COMMENT 'Status of the todo, 0 for not done, 1 for done',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  `deadline` datetime DEFAULT NULL COMMENT 'Deadline for the todo',
  `completed_at` datetime DEFAULT NULL COMMENT 'Completion time of the todo',
  PRIMARY KEY (`id`),
  KEY `idx_user_id_todo` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=33 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `todo_list`
--

DROP TABLE IF EXISTS `todo_list`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `todo_list` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `todo_id` char(36) NOT NULL DEFAULT '' COMMENT 'Todo UUID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `datetime` datetime NOT NULL COMMENT 'Time of the todo event',
  `end_time` datetime NOT NULL DEFAULT ((now() + interval 1 hour)) COMMENT 'End time of the todo event',
  `details` text NOT NULL COMMENT 'Details of the todo event',
  `location` varchar(255) NOT NULL DEFAULT '' COMMENT 'Location of the todo event',
  `participants` varchar(255) NOT NULL DEFAULT '' COMMENT 'Participants in the todo event',
  `description` text NOT NULL COMMENT 'Description of the todo event',
  `completed` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Whether the todo event is completed',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_todo_id_todo_list` (`todo_id`),
  KEY `idx_user_id_todo_list` (`user_id`)
) ENGINE=InnoDB AUTO_INCREMENT=140 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_family_mapping`
--

DROP TABLE IF EXISTS `user_family_mapping`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `user_family_mapping` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Unique ID',
  `user_id` char(36) NOT NULL DEFAULT '' COMMENT 'User UUID',
  `family_id` char(36) NOT NULL DEFAULT '' COMMENT 'Family UUID',
  `status` int NOT NULL DEFAULT '0' COMMENT 'Status of the relationship',
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Creation time',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (`id`),
  KEY `idx_user_id_user_family_mapping` (`user_id`),
  KEY `idx_family_id_user_family_mapping` (`family_id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_info`
--

DROP TABLE IF EXISTS `user_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
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
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `user_profile`
--

DROP TABLE IF EXISTS `user_profile`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `user_profile` (
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
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2024-06-07 11:19:59

CREATE TABLE `user
