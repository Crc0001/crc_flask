-- HwishAI 菌种识别系统 · 客户全新空库结构（零业务数据）
-- 由 deploy_client 的 03_init_mysql.py 自动导入；sys_user / sys_audit_log 由应用首次启动自动创建。
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS sample (
    id                INT NOT NULL AUTO_INCREMENT,
    sample_code       VARCHAR(50)  DEFAULT NULL,
    collect_date      DATETIME     DEFAULT NULL,
    collector         VARCHAR(50)  DEFAULT NULL,
    collect_location  VARCHAR(100) DEFAULT NULL,
    final_strain_name VARCHAR(100) DEFAULT NULL,
    final_confidence  FLOAT        DEFAULT NULL,
    last_detect_time  DATETIME     DEFAULT NULL,
    last_detect_count INT          DEFAULT NULL,
    mass_spectrum     LONGBLOB     DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_sample_code (sample_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sample_lite (
    id             INT NOT NULL AUTO_INCREMENT,
    class_general  VARCHAR(100) NOT NULL,
    class_levelone VARCHAR(100) NOT NULL,
    class_leveltwo VARCHAR(100) NOT NULL,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_general (class_general),
    KEY idx_levelone (class_levelone),
    KEY idx_leveltwo (class_leveltwo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS detect_task (
    id                INT NOT NULL AUTO_INCREMENT,
    image_path        VARCHAR(255) DEFAULT NULL,
    result_image_path VARCHAR(255) DEFAULT NULL,
    created_at        DATETIME     DEFAULT NULL,
    sample_code       VARCHAR(50)  DEFAULT NULL,
    collect_date      DATETIME     DEFAULT NULL,
    location          VARCHAR(100) DEFAULT NULL,
    detect_count      INT          DEFAULT NULL,
    sample_id         INT NOT NULL,
    PRIMARY KEY (id),
    KEY ix_detect_task_sample_id (sample_id),
    CONSTRAINT fk_detect_task_sample FOREIGN KEY (sample_id) REFERENCES sample (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS detect_result (
    id          INT NOT NULL AUTO_INCREMENT,
    strain_name VARCHAR(100) DEFAULT NULL,
    confidence  FLOAT        DEFAULT NULL,
    x1          INT          DEFAULT NULL,
    y1          INT          DEFAULT NULL,
    x2          INT          DEFAULT NULL,
    y2          INT          DEFAULT NULL,
    is_final    TINYINT(1)   DEFAULT NULL,
    task_id     INT NOT NULL,
    PRIMARY KEY (id),
    KEY ix_detect_result_task_id (task_id),
    CONSTRAINT fk_detect_result_task FOREIGN KEY (task_id) REFERENCES detect_task (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
