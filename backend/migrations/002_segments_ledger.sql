-- MySQL 8 DDL for the segment-based study-hours scheme and monthly settlement ledger.
-- New tables are additive; cohorts gains a scheme discriminator so the old click scheme is retained.

ALTER TABLE `cohorts` ADD COLUMN `scheme` varchar(20) DEFAULT 'click';

CREATE TABLE `study_segments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(60) NOT NULL,
  `learner` varchar(60) NOT NULL,
  `started_at` varchar(40) NOT NULL,
  `ended_at` varchar(40) NOT NULL,
  `course` varchar(40) DEFAULT NULL,
  `note` text,
  `revision_of` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `ix_study_segments_learner` (`learner`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `ledger_months` (
  `id` int NOT NULL AUTO_INCREMENT,
  `learner` varchar(60) NOT NULL,
  `period` varchar(7) NOT NULL,
  `state` varchar(20) NOT NULL DEFAULT 'pending',
  `computed_minutes` decimal(10,1) NOT NULL DEFAULT 0,
  `recognized_minutes` decimal(10,1) DEFAULT NULL,
  `capped` tinyint(1) NOT NULL DEFAULT 0,
  `last_known_minutes` decimal(10,1) NOT NULL DEFAULT 0,
  `note` text,
  `updated_at` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_learner_period` (`learner`,`period`),
  KEY `ix_ledger_months_state` (`state`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `ledger_corrections` (
  `id` int NOT NULL AUTO_INCREMENT,
  `learner` varchar(60) NOT NULL,
  `source_month` varchar(7) NOT NULL,
  `target_month` varchar(7) NOT NULL,
  `delta_minutes` decimal(10,1) NOT NULL,
  `reason` text,
  `state` varchar(20) NOT NULL DEFAULT 'pending',
  `settlement_job_id` int DEFAULT NULL,
  `created_at` varchar(40) DEFAULT NULL,
  `applied_at` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_correction_src` (`learner`,`source_month`,`target_month`),
  KEY `ix_corrections_state` (`state`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `ledger_entries` (
  `id` int NOT NULL AUTO_INCREMENT,
  `learner` varchar(60) NOT NULL,
  `period` varchar(7) NOT NULL,
  `entry_type` varchar(20) NOT NULL,
  `amount_minutes` decimal(10,1) NOT NULL,
  `basis` text,
  `ref_kind` varchar(20) DEFAULT NULL,
  `ref_id` int DEFAULT NULL,
  `settlement_job_id` int DEFAULT NULL,
  `created_at` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ledger_entry` (`learner`,`period`,`entry_type`,`ref_kind`,`ref_id`),
  KEY `ix_ledger_entries_learner_period` (`learner`,`period`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `settlement_jobs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `period` varchar(7) DEFAULT NULL,
  `state` varchar(20) NOT NULL DEFAULT 'queued',
  `error` text,
  `posted_rows` int NOT NULL DEFAULT 0,
  `applied_corrections` int NOT NULL DEFAULT 0,
  `created_at` varchar(40) DEFAULT NULL,
  `finished_at` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
