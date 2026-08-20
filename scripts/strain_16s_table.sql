-- 16S 结果表
CREATE TABLE IF NOT EXISTS `strain_16s` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `strain_id` INT NOT NULL COMMENT '关联菌种ID',
  `strain_16s` TEXT NULL COMMENT '16S结果文本',
  PRIMARY KEY (`id`),
  INDEX `idx_strain_16s_strain_id` (`strain_id` ASC),
  CONSTRAINT `fk_strain_16s_strain`
    FOREIGN KEY (`strain_id`)
    REFERENCES `strain` (`id`)
    ON DELETE CASCADE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = '菌种16S结果表';
