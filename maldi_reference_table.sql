-- MALDI-TOF 质谱参考谱库表
-- 创建时间: 2026-04-01

-- 创建 maldi_reference 表
CREATE TABLE IF NOT EXISTS `maldi_reference` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `strain_id` INT NOT NULL COMMENT '关联菌种ID',
  `sample_id` VARCHAR(100) NULL DEFAULT NULL COMMENT '样本ID（从COM=解析）',
  `peaks` JSON NOT NULL COMMENT '峰数据 [[mz1, intensity1], [mz2, intensity2], ...]',
  `peak_count` INT NULL DEFAULT NULL COMMENT '峰数量',
  `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  INDEX `idx_strain_id` (`strain_id` ASC),
  INDEX `idx_sample_id` (`sample_id` ASC),
  CONSTRAINT `fk_maldi_reference_strain` FOREIGN KEY (`strain_id`) REFERENCES `strain` (`id`) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = 'MALDI-TOF质谱参考谱库';
