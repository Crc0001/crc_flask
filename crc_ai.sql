/*
 Navicat Premium Dump SQL

 Source Server         : crc_flaskdb
 Source Server Type    : MySQL
 Source Server Version : 80044 (8.0.44)
 Source Host           : localhost:3306
 Source Schema         : crc_ai

 Target Server Type    : MySQL
 Target Server Version : 80044 (8.0.44)
 File Encoding         : 65001

 Date: 12/01/2026 05:52:29
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for crc_item
-- ----------------------------
DROP TABLE IF EXISTS `crc_item`;
CREATE TABLE `crc_item`  (
  `id` int NOT NULL,
  `name` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL,
  `create_time` datetime NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of crc_item
-- ----------------------------
INSERT INTO `crc_item` VALUES (1, '菌种数据库', NULL, '2025-12-23 17:24:38');
INSERT INTO `crc_item` VALUES (2, '分类统计', NULL, '2025-12-23 17:25:00');
INSERT INTO `crc_item` VALUES (3, '趋势分析', NULL, '2025-12-23 17:25:11');
INSERT INTO `crc_item` VALUES (4, 'AI建议', NULL, '2025-12-23 17:25:25');

-- ----------------------------
-- Table structure for detect_result
-- ----------------------------
DROP TABLE IF EXISTS `detect_result`;
CREATE TABLE `detect_result`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `task_id` int NULL DEFAULT NULL,
  `strain_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `confidence` float NULL DEFAULT NULL,
  `x1` int NULL DEFAULT NULL,
  `y1` int NULL DEFAULT NULL,
  `x2` int NULL DEFAULT NULL,
  `y2` int NULL DEFAULT NULL,
  `is_final` tinyint(1) NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `fk_result_task`(`task_id` ASC) USING BTREE,
  CONSTRAINT `detect_result_ibfk_1` FOREIGN KEY (`task_id`) REFERENCES `detect_task` (`id`) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT `fk_result_task` FOREIGN KEY (`task_id`) REFERENCES `detect_task` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 539 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of detect_result
-- ----------------------------
INSERT INTO `detect_result` VALUES (191, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.896899, 1611, 3613, 1701, 3707, 0);
INSERT INTO `detect_result` VALUES (192, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.888617, 1426, 2769, 1508, 2856, 0);
INSERT INTO `detect_result` VALUES (193, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.86765, 2028, 2603, 2115, 2691, 0);
INSERT INTO `detect_result` VALUES (194, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.84857, 1613, 2731, 1706, 2832, 0);
INSERT INTO `detect_result` VALUES (195, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.836725, 1757, 3374, 1837, 3457, 0);
INSERT INTO `detect_result` VALUES (196, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.825629, 332, 3624, 407, 3708, 0);
INSERT INTO `detect_result` VALUES (197, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.81601, 903, 2362, 992, 2460, 0);
INSERT INTO `detect_result` VALUES (198, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.805288, 2656, 3962, 2732, 4042, 0);
INSERT INTO `detect_result` VALUES (199, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.723639, 1331, 3842, 1447, 3971, 0);
INSERT INTO `detect_result` VALUES (200, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.68533, 714, 2351, 795, 2437, 0);
INSERT INTO `detect_result` VALUES (201, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.6694, 640, 3804, 709, 3874, 0);
INSERT INTO `detect_result` VALUES (202, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.524185, 456, 3601, 531, 3683, 0);
INSERT INTO `detect_result` VALUES (203, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.460258, 2957, 3353, 3025, 3425, 0);
INSERT INTO `detect_result` VALUES (204, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.438136, 0, 3271, 43, 3363, 0);
INSERT INTO `detect_result` VALUES (205, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.424369, 2505, 3449, 2578, 3529, 0);
INSERT INTO `detect_result` VALUES (206, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.42285, 816, 2345, 892, 2422, 0);
INSERT INTO `detect_result` VALUES (207, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.407571, 2460, 3895, 2542, 3980, 0);
INSERT INTO `detect_result` VALUES (208, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.391752, 1120, 2776, 1231, 2881, 0);
INSERT INTO `detect_result` VALUES (209, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.355813, 1208, 2760, 1283, 2854, 0);
INSERT INTO `detect_result` VALUES (210, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.324169, 628, 2773, 764, 2872, 0);
INSERT INTO `detect_result` VALUES (211, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.301119, 594, 3633, 678, 3742, 0);
INSERT INTO `detect_result` VALUES (212, 13, '瑞士乳杆菌 Lactobacillus helveticus', 0.251038, 262, 3175, 336, 3251, 0);
INSERT INTO `detect_result` VALUES (213, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.757356, 662, 1265, 727, 1336, 0);
INSERT INTO `detect_result` VALUES (214, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.713832, 589, 1400, 662, 1479, 0);
INSERT INTO `detect_result` VALUES (215, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.706037, 2481, 3861, 2547, 3930, 0);
INSERT INTO `detect_result` VALUES (216, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.681482, 1154, 1116, 1227, 1194, 0);
INSERT INTO `detect_result` VALUES (217, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.651176, 2341, 3990, 2429, 4086, 0);
INSERT INTO `detect_result` VALUES (218, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.645438, 35, 1001, 102, 1075, 0);
INSERT INTO `detect_result` VALUES (219, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.62985, 488, 1724, 553, 1796, 0);
INSERT INTO `detect_result` VALUES (220, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.560788, 1004, 757, 1086, 862, 0);
INSERT INTO `detect_result` VALUES (221, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.533619, 2548, 3745, 2626, 3819, 0);
INSERT INTO `detect_result` VALUES (222, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.499231, 127, 1206, 189, 1270, 0);
INSERT INTO `detect_result` VALUES (223, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.442528, 485, 346, 563, 422, 0);
INSERT INTO `detect_result` VALUES (224, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.405621, 0, 708, 75, 814, 0);
INSERT INTO `detect_result` VALUES (225, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.392644, 684, 101, 752, 194, 0);
INSERT INTO `detect_result` VALUES (226, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.298575, 658, 525, 762, 622, 0);
INSERT INTO `detect_result` VALUES (227, 14, '瑞士乳杆菌 Lactobacillus helveticus', 0.282205, 628, 193, 686, 256, 0);
INSERT INTO `detect_result` VALUES (228, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.757356, 662, 1265, 727, 1336, 0);
INSERT INTO `detect_result` VALUES (229, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.713832, 589, 1400, 662, 1479, 0);
INSERT INTO `detect_result` VALUES (230, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.706037, 2481, 3861, 2547, 3930, 0);
INSERT INTO `detect_result` VALUES (231, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.681482, 1154, 1116, 1227, 1194, 0);
INSERT INTO `detect_result` VALUES (232, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.651176, 2341, 3990, 2429, 4086, 0);
INSERT INTO `detect_result` VALUES (233, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.645438, 35, 1001, 102, 1075, 0);
INSERT INTO `detect_result` VALUES (234, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.62985, 488, 1724, 553, 1796, 0);
INSERT INTO `detect_result` VALUES (235, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.560788, 1004, 757, 1086, 862, 0);
INSERT INTO `detect_result` VALUES (236, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.533619, 2548, 3745, 2626, 3819, 0);
INSERT INTO `detect_result` VALUES (237, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.499231, 127, 1206, 189, 1270, 0);
INSERT INTO `detect_result` VALUES (238, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.442528, 485, 346, 563, 422, 0);
INSERT INTO `detect_result` VALUES (239, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.405621, 0, 708, 75, 814, 0);
INSERT INTO `detect_result` VALUES (240, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.392644, 684, 101, 752, 194, 0);
INSERT INTO `detect_result` VALUES (241, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.298575, 658, 525, 762, 622, 0);
INSERT INTO `detect_result` VALUES (242, 15, '瑞士乳杆菌 Lactobacillus helveticus', 0.282205, 628, 193, 686, 256, 0);
INSERT INTO `detect_result` VALUES (279, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.934551, 442, 368, 489, 419, 0);
INSERT INTO `detect_result` VALUES (280, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.933833, 517, 324, 555, 364, 0);
INSERT INTO `detect_result` VALUES (281, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.926952, 660, 730, 706, 779, 0);
INSERT INTO `detect_result` VALUES (282, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.913094, 589, 684, 638, 733, 0);
INSERT INTO `detect_result` VALUES (283, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.9031, 474, 887, 521, 937, 0);
INSERT INTO `detect_result` VALUES (284, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.860952, 107, 727, 146, 769, 0);
INSERT INTO `detect_result` VALUES (285, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.840147, 39, 826, 88, 875, 0);
INSERT INTO `detect_result` VALUES (286, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.807475, 774, 459, 816, 503, 0);
INSERT INTO `detect_result` VALUES (287, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.792279, 181, 220, 217, 259, 0);
INSERT INTO `detect_result` VALUES (288, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.728047, 192, 265, 227, 303, 0);
INSERT INTO `detect_result` VALUES (289, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.701714, 298, 380, 345, 428, 0);
INSERT INTO `detect_result` VALUES (290, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.615891, 161, 986, 193, 1021, 0);
INSERT INTO `detect_result` VALUES (291, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.603961, 441, 996, 479, 1024, 0);
INSERT INTO `detect_result` VALUES (292, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.584422, 491, 592, 535, 653, 0);
INSERT INTO `detect_result` VALUES (293, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.548951, 154, 717, 193, 757, 0);
INSERT INTO `detect_result` VALUES (294, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.495192, 866, 0, 922, 27, 0);
INSERT INTO `detect_result` VALUES (295, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.34209, 200, 991, 235, 1023, 0);
INSERT INTO `detect_result` VALUES (296, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.325699, 946, 0, 983, 28, 0);
INSERT INTO `detect_result` VALUES (297, 19, '瑞士乳杆菌 Lactobacillus helveticus', 0.275419, 276, 841, 304, 872, 0);
INSERT INTO `detect_result` VALUES (317, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.923135, 463, 3610, 579, 3721, 0);
INSERT INTO `detect_result` VALUES (318, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.891468, 2297, 2080, 2410, 2188, 0);
INSERT INTO `detect_result` VALUES (319, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.888614, 2001, 1786, 2103, 1885, 0);
INSERT INTO `detect_result` VALUES (320, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.887594, 1446, 2991, 1554, 3097, 0);
INSERT INTO `detect_result` VALUES (321, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.88017, 2367, 1926, 2473, 2024, 0);
INSERT INTO `detect_result` VALUES (322, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.879251, 2630, 3131, 2725, 3219, 0);
INSERT INTO `detect_result` VALUES (323, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.879081, 1635, 2955, 1735, 3054, 0);
INSERT INTO `detect_result` VALUES (324, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.868251, 82, 3543, 205, 3652, 0);
INSERT INTO `detect_result` VALUES (325, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.865311, 2364, 2299, 2475, 2403, 0);
INSERT INTO `detect_result` VALUES (326, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.864091, 1264, 2751, 1365, 2853, 0);
INSERT INTO `detect_result` VALUES (327, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.857915, 2865, 2248, 2976, 2353, 0);
INSERT INTO `detect_result` VALUES (328, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.847505, 2620, 1365, 2707, 1445, 0);
INSERT INTO `detect_result` VALUES (329, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.843095, 1996, 2855, 2096, 2955, 0);
INSERT INTO `detect_result` VALUES (330, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.825493, 234, 2407, 312, 2484, 0);
INSERT INTO `detect_result` VALUES (331, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.815488, 2370, 1757, 2472, 1854, 0);
INSERT INTO `detect_result` VALUES (332, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.777218, 2004, 1528, 2092, 1625, 0);
INSERT INTO `detect_result` VALUES (333, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.746429, 1805, 2717, 1903, 2814, 0);
INSERT INTO `detect_result` VALUES (334, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.671565, 1986, 1329, 2070, 1407, 0);
INSERT INTO `detect_result` VALUES (335, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.634118, 2063, 1187, 2146, 1273, 0);
INSERT INTO `detect_result` VALUES (336, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.616769, 2141, 2807, 2239, 2907, 0);
INSERT INTO `detect_result` VALUES (337, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.602647, 743, 1775, 818, 1871, 0);
INSERT INTO `detect_result` VALUES (338, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.582275, 133, 2368, 207, 2441, 0);
INSERT INTO `detect_result` VALUES (339, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.520592, 1465, 636, 1550, 709, 0);
INSERT INTO `detect_result` VALUES (340, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.492545, 2102, 2721, 2191, 2803, 0);
INSERT INTO `detect_result` VALUES (341, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.484787, 1537, 2077, 1615, 2157, 0);
INSERT INTO `detect_result` VALUES (342, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.356208, 352, 1821, 419, 1883, 0);
INSERT INTO `detect_result` VALUES (343, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.339343, 1011, 657, 1079, 735, 0);
INSERT INTO `detect_result` VALUES (344, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.332019, 2236, 2549, 2336, 2643, 0);
INSERT INTO `detect_result` VALUES (345, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.322163, 2525, 1187, 2615, 1263, 0);
INSERT INTO `detect_result` VALUES (346, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.296954, 2053, 636, 2129, 698, 0);
INSERT INTO `detect_result` VALUES (347, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.29624, 0, 2877, 45, 2985, 0);
INSERT INTO `detect_result` VALUES (348, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.285719, 1628, 2560, 1716, 2644, 0);
INSERT INTO `detect_result` VALUES (349, 21, '泡囊短波单胞菌Brevundimonas vesicularis', 0.282544, 2523, 1153, 2613, 1260, 0);
INSERT INTO `detect_result` VALUES (350, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.918214, 631, 3629, 742, 3736, 0);
INSERT INTO `detect_result` VALUES (351, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.894655, 1553, 3018, 1655, 3119, 0);
INSERT INTO `detect_result` VALUES (352, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.873865, 1731, 2980, 1823, 3074, 0);
INSERT INTO `detect_result` VALUES (353, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.871789, 2065, 2876, 2165, 2975, 0);
INSERT INTO `detect_result` VALUES (354, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.867681, 2044, 1863, 2141, 1957, 0);
INSERT INTO `detect_result` VALUES (355, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.842215, 265, 3578, 386, 3683, 0);
INSERT INTO `detect_result` VALUES (356, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.838035, 1372, 2796, 1468, 2890, 0);
INSERT INTO `detect_result` VALUES (357, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.823263, 2872, 2282, 2975, 2382, 0);
INSERT INTO `detect_result` VALUES (358, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.815894, 2337, 2137, 2437, 2236, 0);
INSERT INTO `detect_result` VALUES (359, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.813032, 2405, 2342, 2504, 2439, 0);
INSERT INTO `detect_result` VALUES (360, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.758105, 2673, 3122, 2763, 3206, 0);
INSERT INTO `detect_result` VALUES (361, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.730156, 2038, 1622, 2126, 1714, 0);
INSERT INTO `detect_result` VALUES (362, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.703301, 2618, 1453, 2702, 1529, 0);
INSERT INTO `detect_result` VALUES (363, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.677369, 2079, 857, 2153, 922, 0);
INSERT INTO `detect_result` VALUES (364, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.67225, 2021, 1437, 2098, 1512, 0);
INSERT INTO `detect_result` VALUES (365, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.627131, 1613, 2148, 1692, 2229, 0);
INSERT INTO `detect_result` VALUES (366, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.618979, 1511, 795, 1591, 864, 0);
INSERT INTO `detect_result` VALUES (367, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.524927, 2202, 2823, 2296, 2920, 0);
INSERT INTO `detect_result` VALUES (368, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.517843, 855, 1884, 930, 1972, 0);
INSERT INTO `detect_result` VALUES (369, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.509547, 2167, 2744, 2248, 2819, 0);
INSERT INTO `detect_result` VALUES (370, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.507814, 1929, 801, 1996, 866, 0);
INSERT INTO `detect_result` VALUES (371, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.490369, 2401, 1990, 2492, 2080, 0);
INSERT INTO `detect_result` VALUES (372, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.410222, 2064, 781, 2135, 841, 0);
INSERT INTO `detect_result` VALUES (373, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.379804, 390, 2493, 461, 2562, 0);
INSERT INTO `detect_result` VALUES (374, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.351481, 2525, 1278, 2609, 1359, 0);
INSERT INTO `detect_result` VALUES (375, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.3434, 1705, 2606, 1795, 2688, 0);
INSERT INTO `detect_result` VALUES (376, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.335975, 2396, 1828, 2486, 1918, 0);
INSERT INTO `detect_result` VALUES (377, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.323438, 1889, 2753, 1976, 2833, 0);
INSERT INTO `detect_result` VALUES (378, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.308895, 486, 1936, 554, 1991, 0);
INSERT INTO `detect_result` VALUES (379, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.286448, 1802, 768, 1877, 836, 0);
INSERT INTO `detect_result` VALUES (380, 22, '泡囊短波单胞菌Brevundimonas vesicularis', 0.269896, 1787, 1730, 1872, 1809, 0);
INSERT INTO `detect_result` VALUES (383, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.944904, 1993, 3167, 2122, 3302, 0);
INSERT INTO `detect_result` VALUES (384, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.940485, 857, 3676, 977, 3806, 0);
INSERT INTO `detect_result` VALUES (385, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.939399, 1850, 2940, 1961, 3060, 0);
INSERT INTO `detect_result` VALUES (386, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.934961, 2414, 3630, 2531, 3756, 0);
INSERT INTO `detect_result` VALUES (387, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.924783, 111, 2003, 217, 2118, 0);
INSERT INTO `detect_result` VALUES (388, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.918699, 1260, 3726, 1368, 3841, 0);
INSERT INTO `detect_result` VALUES (389, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.903285, 2065, 2015, 2191, 2148, 0);
INSERT INTO `detect_result` VALUES (390, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.896081, 2521, 2526, 2626, 2638, 0);
INSERT INTO `detect_result` VALUES (391, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.887483, 660, 1650, 758, 1758, 0);
INSERT INTO `detect_result` VALUES (392, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.885881, 1982, 1764, 2089, 1883, 0);
INSERT INTO `detect_result` VALUES (393, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.870025, 74, 2514, 159, 2606, 0);
INSERT INTO `detect_result` VALUES (394, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.857394, 466, 1185, 561, 1286, 0);
INSERT INTO `detect_result` VALUES (395, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.843571, 221, 2357, 362, 2491, 0);
INSERT INTO `detect_result` VALUES (396, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.808938, 214, 2155, 318, 2267, 0);
INSERT INTO `detect_result` VALUES (397, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.807689, 2372, 1878, 2458, 1972, 0);
INSERT INTO `detect_result` VALUES (398, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.793048, 1735, 2644, 1848, 2762, 0);
INSERT INTO `detect_result` VALUES (399, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.776807, 2063, 1891, 2167, 1997, 0);
INSERT INTO `detect_result` VALUES (400, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.674223, 1478, 3984, 1584, 4094, 0);
INSERT INTO `detect_result` VALUES (401, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.664906, 2706, 2795, 2791, 2892, 0);
INSERT INTO `detect_result` VALUES (402, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.598062, 2485, 1209, 2556, 1285, 0);
INSERT INTO `detect_result` VALUES (403, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.569287, 2842, 2729, 2926, 2818, 0);
INSERT INTO `detect_result` VALUES (404, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.560102, 1755, 1229, 1854, 1329, 0);
INSERT INTO `detect_result` VALUES (405, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.55524, 2369, 2837, 2482, 2958, 0);
INSERT INTO `detect_result` VALUES (406, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.532697, 159, 2267, 273, 2386, 0);
INSERT INTO `detect_result` VALUES (407, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.528412, 1639, 2539, 1779, 2691, 0);
INSERT INTO `detect_result` VALUES (408, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.47247, 2275, 2347, 2383, 2460, 0);
INSERT INTO `detect_result` VALUES (409, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.402663, 23, 1817, 179, 1971, 0);
INSERT INTO `detect_result` VALUES (410, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.38327, 2468, 1846, 2548, 1941, 0);
INSERT INTO `detect_result` VALUES (411, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.354003, 2658, 1082, 2724, 1148, 0);
INSERT INTO `detect_result` VALUES (412, 24, '瑞士乳杆菌 Lactobacillus helveticus', 0.27812, 2269, 57, 2349, 128, 0);
INSERT INTO `detect_result` VALUES (413, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.757356, 662, 1265, 727, 1336, 0);
INSERT INTO `detect_result` VALUES (414, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.713832, 589, 1400, 662, 1479, 0);
INSERT INTO `detect_result` VALUES (415, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.706037, 2481, 3861, 2547, 3930, 0);
INSERT INTO `detect_result` VALUES (416, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.681482, 1154, 1116, 1227, 1194, 0);
INSERT INTO `detect_result` VALUES (417, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.651176, 2341, 3990, 2429, 4086, 0);
INSERT INTO `detect_result` VALUES (418, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.645438, 35, 1001, 102, 1075, 0);
INSERT INTO `detect_result` VALUES (419, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.62985, 488, 1724, 553, 1796, 0);
INSERT INTO `detect_result` VALUES (420, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.560788, 1004, 757, 1086, 862, 0);
INSERT INTO `detect_result` VALUES (421, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.533619, 2548, 3745, 2626, 3819, 0);
INSERT INTO `detect_result` VALUES (422, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.499231, 127, 1206, 189, 1270, 0);
INSERT INTO `detect_result` VALUES (423, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.442528, 485, 346, 563, 422, 0);
INSERT INTO `detect_result` VALUES (424, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.405621, 0, 708, 75, 814, 0);
INSERT INTO `detect_result` VALUES (425, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.392644, 684, 101, 752, 194, 0);
INSERT INTO `detect_result` VALUES (426, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.298575, 658, 525, 762, 622, 0);
INSERT INTO `detect_result` VALUES (427, 25, '瑞士乳杆菌 Lactobacillus helveticus', 0.282205, 628, 193, 686, 256, 0);
INSERT INTO `detect_result` VALUES (428, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.896899, 1611, 3613, 1701, 3707, 0);
INSERT INTO `detect_result` VALUES (429, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.888617, 1426, 2769, 1508, 2856, 0);
INSERT INTO `detect_result` VALUES (430, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.86765, 2028, 2603, 2115, 2691, 0);
INSERT INTO `detect_result` VALUES (431, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.84857, 1613, 2731, 1706, 2832, 0);
INSERT INTO `detect_result` VALUES (432, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.836725, 1757, 3374, 1837, 3457, 0);
INSERT INTO `detect_result` VALUES (433, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.825629, 332, 3624, 407, 3708, 0);
INSERT INTO `detect_result` VALUES (434, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.81601, 903, 2362, 992, 2460, 0);
INSERT INTO `detect_result` VALUES (435, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.805288, 2656, 3962, 2732, 4042, 0);
INSERT INTO `detect_result` VALUES (436, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.723639, 1331, 3842, 1447, 3971, 0);
INSERT INTO `detect_result` VALUES (437, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.68533, 714, 2351, 795, 2437, 0);
INSERT INTO `detect_result` VALUES (438, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.6694, 640, 3804, 709, 3874, 0);
INSERT INTO `detect_result` VALUES (439, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.524185, 456, 3601, 531, 3683, 0);
INSERT INTO `detect_result` VALUES (440, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.460258, 2957, 3353, 3025, 3425, 0);
INSERT INTO `detect_result` VALUES (441, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.438136, 0, 3271, 43, 3363, 0);
INSERT INTO `detect_result` VALUES (442, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.424369, 2505, 3449, 2578, 3529, 0);
INSERT INTO `detect_result` VALUES (443, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.42285, 816, 2345, 892, 2422, 0);
INSERT INTO `detect_result` VALUES (444, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.407571, 2460, 3895, 2542, 3980, 0);
INSERT INTO `detect_result` VALUES (445, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.391752, 1120, 2776, 1231, 2881, 0);
INSERT INTO `detect_result` VALUES (446, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.355813, 1208, 2760, 1283, 2854, 0);
INSERT INTO `detect_result` VALUES (447, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.324169, 628, 2773, 764, 2872, 0);
INSERT INTO `detect_result` VALUES (448, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.301119, 594, 3633, 678, 3742, 0);
INSERT INTO `detect_result` VALUES (449, 26, '瑞士乳杆菌 Lactobacillus helveticus', 0.251038, 262, 3175, 336, 3251, 0);
INSERT INTO `detect_result` VALUES (450, 28, '瑞士乳杆菌 Lactobacillus helveticus', 0.625283, 2696, 2919, 2765, 3008, 0);
INSERT INTO `detect_result` VALUES (451, 28, '瑞士乳杆菌 Lactobacillus helveticus', 0.59484, 2876, 1359, 2942, 1429, 0);
INSERT INTO `detect_result` VALUES (452, 28, '瑞士乳杆菌 Lactobacillus helveticus', 0.460509, 2638, 3426, 2703, 3493, 0);
INSERT INTO `detect_result` VALUES (453, 28, '瑞士乳杆菌 Lactobacillus helveticus', 0.427731, 2696, 3790, 2759, 3856, 0);
INSERT INTO `detect_result` VALUES (454, 28, '瑞士乳杆菌 Lactobacillus helveticus', 0.369913, 2098, 2956, 2163, 3024, 0);
INSERT INTO `detect_result` VALUES (455, 28, '瑞士乳杆菌 Lactobacillus helveticus', 0.28076, 2830, 2979, 2888, 3041, 0);
INSERT INTO `detect_result` VALUES (456, 28, '瑞士乳杆菌 Lactobacillus helveticus', 0.250808, 2256, 3464, 2311, 3526, 0);
INSERT INTO `detect_result` VALUES (457, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.907766, 1858, 2469, 1954, 2574, 0);
INSERT INTO `detect_result` VALUES (458, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.885901, 2756, 2679, 2847, 2780, 0);
INSERT INTO `detect_result` VALUES (459, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.858487, 1850, 2681, 1934, 2771, 0);
INSERT INTO `detect_result` VALUES (460, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.842773, 2546, 2485, 2628, 2573, 0);
INSERT INTO `detect_result` VALUES (461, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.812651, 1822, 2022, 1911, 2117, 0);
INSERT INTO `detect_result` VALUES (462, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.805565, 1256, 3312, 1335, 3403, 0);
INSERT INTO `detect_result` VALUES (463, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.800438, 1306, 3113, 1402, 3218, 0);
INSERT INTO `detect_result` VALUES (464, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.781019, 1279, 2633, 1354, 2718, 0);
INSERT INTO `detect_result` VALUES (465, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.777127, 2458, 4006, 2540, 4093, 0);
INSERT INTO `detect_result` VALUES (466, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.71937, 1978, 3973, 2058, 4058, 0);
INSERT INTO `detect_result` VALUES (467, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.682455, 2957, 803, 3039, 916, 0);
INSERT INTO `detect_result` VALUES (468, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.558884, 2799, 1746, 2878, 1831, 0);
INSERT INTO `detect_result` VALUES (469, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.485288, 2465, 3873, 2546, 3958, 0);
INSERT INTO `detect_result` VALUES (470, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.363993, 246, 1036, 303, 1096, 0);
INSERT INTO `detect_result` VALUES (471, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.358843, 1265, 3210, 1336, 3297, 0);
INSERT INTO `detect_result` VALUES (472, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.339324, 1664, 3445, 1765, 3591, 0);
INSERT INTO `detect_result` VALUES (473, 29, '瑞士乳杆菌 Lactobacillus helveticus', 0.313414, 2715, 3740, 2783, 3812, 0);
INSERT INTO `detect_result` VALUES (474, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.907766, 1858, 2469, 1954, 2574, 0);
INSERT INTO `detect_result` VALUES (475, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.885901, 2756, 2679, 2847, 2780, 0);
INSERT INTO `detect_result` VALUES (476, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.858487, 1850, 2681, 1934, 2771, 0);
INSERT INTO `detect_result` VALUES (477, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.842773, 2546, 2485, 2628, 2573, 0);
INSERT INTO `detect_result` VALUES (478, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.812651, 1822, 2022, 1911, 2117, 0);
INSERT INTO `detect_result` VALUES (479, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.805565, 1256, 3312, 1335, 3403, 0);
INSERT INTO `detect_result` VALUES (480, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.800438, 1306, 3113, 1402, 3218, 0);
INSERT INTO `detect_result` VALUES (481, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.781019, 1279, 2633, 1354, 2718, 0);
INSERT INTO `detect_result` VALUES (482, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.777127, 2458, 4006, 2540, 4093, 0);
INSERT INTO `detect_result` VALUES (483, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.71937, 1978, 3973, 2058, 4058, 0);
INSERT INTO `detect_result` VALUES (484, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.682455, 2957, 803, 3039, 916, 0);
INSERT INTO `detect_result` VALUES (485, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.558884, 2799, 1746, 2878, 1831, 0);
INSERT INTO `detect_result` VALUES (486, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.485288, 2465, 3873, 2546, 3958, 0);
INSERT INTO `detect_result` VALUES (487, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.363993, 246, 1036, 303, 1096, 0);
INSERT INTO `detect_result` VALUES (488, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.358843, 1265, 3210, 1336, 3297, 0);
INSERT INTO `detect_result` VALUES (489, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.339324, 1664, 3445, 1765, 3591, 0);
INSERT INTO `detect_result` VALUES (490, 30, '瑞士乳杆菌 Lactobacillus helveticus', 0.313414, 2715, 3740, 2783, 3812, 0);
INSERT INTO `detect_result` VALUES (491, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.907766, 1858, 2469, 1954, 2574, 0);
INSERT INTO `detect_result` VALUES (492, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.885901, 2756, 2679, 2847, 2780, 0);
INSERT INTO `detect_result` VALUES (493, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.858487, 1850, 2681, 1934, 2771, 0);
INSERT INTO `detect_result` VALUES (494, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.842773, 2546, 2485, 2628, 2573, 0);
INSERT INTO `detect_result` VALUES (495, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.812651, 1822, 2022, 1911, 2117, 0);
INSERT INTO `detect_result` VALUES (496, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.805565, 1256, 3312, 1335, 3403, 0);
INSERT INTO `detect_result` VALUES (497, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.800438, 1306, 3113, 1402, 3218, 0);
INSERT INTO `detect_result` VALUES (498, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.781019, 1279, 2633, 1354, 2718, 0);
INSERT INTO `detect_result` VALUES (499, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.777127, 2458, 4006, 2540, 4093, 0);
INSERT INTO `detect_result` VALUES (500, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.71937, 1978, 3973, 2058, 4058, 0);
INSERT INTO `detect_result` VALUES (501, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.682455, 2957, 803, 3039, 916, 0);
INSERT INTO `detect_result` VALUES (502, 31, '瑞士乳杆菌 Lactobacillus helveticus', 0.558884, 2799, 1746, 2878, 1831, 0);
INSERT INTO `detect_result` VALUES (503, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.907766, 1858, 2469, 1954, 2574, 0);
INSERT INTO `detect_result` VALUES (504, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.885901, 2756, 2679, 2847, 2780, 0);
INSERT INTO `detect_result` VALUES (505, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.858487, 1850, 2681, 1934, 2771, 0);
INSERT INTO `detect_result` VALUES (506, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.842773, 2546, 2485, 2628, 2573, 0);
INSERT INTO `detect_result` VALUES (507, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.812651, 1822, 2022, 1911, 2117, 0);
INSERT INTO `detect_result` VALUES (508, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.805565, 1256, 3312, 1335, 3403, 0);
INSERT INTO `detect_result` VALUES (509, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.800438, 1306, 3113, 1402, 3218, 0);
INSERT INTO `detect_result` VALUES (510, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.781019, 1279, 2633, 1354, 2718, 0);
INSERT INTO `detect_result` VALUES (511, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.777127, 2458, 4006, 2540, 4093, 0);
INSERT INTO `detect_result` VALUES (512, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.71937, 1978, 3973, 2058, 4058, 0);
INSERT INTO `detect_result` VALUES (513, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.682455, 2957, 803, 3039, 916, 0);
INSERT INTO `detect_result` VALUES (514, 32, '瑞士乳杆菌 Lactobacillus helveticus', 0.558884, 2799, 1746, 2878, 1831, 0);
INSERT INTO `detect_result` VALUES (515, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.907766, 1858, 2469, 1954, 2574, 0);
INSERT INTO `detect_result` VALUES (516, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.885901, 2756, 2679, 2847, 2780, 0);
INSERT INTO `detect_result` VALUES (517, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.858487, 1850, 2681, 1934, 2771, 0);
INSERT INTO `detect_result` VALUES (518, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.842773, 2546, 2485, 2628, 2573, 0);
INSERT INTO `detect_result` VALUES (519, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.812651, 1822, 2022, 1911, 2117, 0);
INSERT INTO `detect_result` VALUES (520, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.805565, 1256, 3312, 1335, 3403, 0);
INSERT INTO `detect_result` VALUES (521, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.800438, 1306, 3113, 1402, 3218, 0);
INSERT INTO `detect_result` VALUES (522, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.781019, 1279, 2633, 1354, 2718, 0);
INSERT INTO `detect_result` VALUES (523, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.777127, 2458, 4006, 2540, 4093, 0);
INSERT INTO `detect_result` VALUES (524, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.71937, 1978, 3973, 2058, 4058, 0);
INSERT INTO `detect_result` VALUES (525, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.682455, 2957, 803, 3039, 916, 0);
INSERT INTO `detect_result` VALUES (526, 33, '瑞士乳杆菌 Lactobacillus helveticus', 0.558884, 2799, 1746, 2878, 1831, 0);
INSERT INTO `detect_result` VALUES (527, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.907766, 1858, 2469, 1954, 2574, 0);
INSERT INTO `detect_result` VALUES (528, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.885901, 2756, 2679, 2847, 2780, 0);
INSERT INTO `detect_result` VALUES (529, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.858487, 1850, 2681, 1934, 2771, 0);
INSERT INTO `detect_result` VALUES (530, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.842773, 2546, 2485, 2628, 2573, 0);
INSERT INTO `detect_result` VALUES (531, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.812651, 1822, 2022, 1911, 2117, 0);
INSERT INTO `detect_result` VALUES (532, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.805565, 1256, 3312, 1335, 3403, 0);
INSERT INTO `detect_result` VALUES (533, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.800438, 1306, 3113, 1402, 3218, 0);
INSERT INTO `detect_result` VALUES (534, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.781019, 1279, 2633, 1354, 2718, 0);
INSERT INTO `detect_result` VALUES (535, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.777127, 2458, 4006, 2540, 4093, 0);
INSERT INTO `detect_result` VALUES (536, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.71937, 1978, 3973, 2058, 4058, 0);
INSERT INTO `detect_result` VALUES (537, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.682455, 2957, 803, 3039, 916, 0);
INSERT INTO `detect_result` VALUES (538, 35, '瑞士乳杆菌 Lactobacillus helveticus', 0.558884, 2799, 1746, 2878, 1831, 0);

-- ----------------------------
-- Table structure for detect_task
-- ----------------------------
DROP TABLE IF EXISTS `detect_task`;
CREATE TABLE `detect_task`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `image_path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `result_image_path` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `created_at` datetime NULL DEFAULT CURRENT_TIMESTAMP,
  `sample_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `collect_date` date NULL DEFAULT NULL,
  `location` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `sample_id` int NULL DEFAULT NULL COMMENT '关联sample表的主键ID',
  `detect_count` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `fk_task_sample`(`sample_id` ASC) USING BTREE,
  CONSTRAINT `fk_task_sample` FOREIGN KEY (`sample_id`) REFERENCES `sample` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB AUTO_INCREMENT = 37 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of detect_task
-- ----------------------------
INSERT INTO `detect_task` VALUES (13, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\6.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\6.jpg', NULL, '10', '2025-12-25', '实验室A', NULL, NULL);
INSERT INTO `detect_task` VALUES (14, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\2.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\2.jpg', NULL, '11', '2025-12-25', '实验室B', NULL, NULL);
INSERT INTO `detect_task` VALUES (15, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\2.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\2.jpg', NULL, '11', '2025-12-25', '实验室B', NULL, NULL);
INSERT INTO `detect_task` VALUES (19, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\10_tile3_rot90.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\10_tile3_rot90.jpg', '2025-12-26 02:07:03', NULL, NULL, NULL, 4, NULL);
INSERT INTO `detect_task` VALUES (21, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\16.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\16.jpg', '2025-12-26 05:51:38', NULL, NULL, NULL, 6, NULL);
INSERT INTO `detect_task` VALUES (22, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\14.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\14.jpg', '2025-12-26 07:45:23', NULL, NULL, NULL, 9, '31');
INSERT INTO `detect_task` VALUES (24, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\4.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\4.jpg', '2025-12-26 09:21:02', NULL, NULL, NULL, 11, '30');
INSERT INTO `detect_task` VALUES (25, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\2.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\2.jpg', '2025-12-26 09:21:40', NULL, NULL, NULL, 12, '15');
INSERT INTO `detect_task` VALUES (26, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\6.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\6.jpg', '2025-12-26 09:31:51', NULL, NULL, NULL, 13, '22');
INSERT INTO `detect_task` VALUES (28, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\14.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\14.jpg', '2025-12-27 03:52:01', NULL, NULL, NULL, 15, '7');
INSERT INTO `detect_task` VALUES (29, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\1.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\1.jpg', '2025-12-29 00:54:15', NULL, NULL, NULL, 16, '17');
INSERT INTO `detect_task` VALUES (30, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\1.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\1.jpg', '2026-01-11 18:16:43', NULL, NULL, NULL, 17, '17');
INSERT INTO `detect_task` VALUES (31, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\1.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\result_1.jpg', '2026-01-11 21:42:34', NULL, NULL, NULL, 17, '12');
INSERT INTO `detect_task` VALUES (32, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\1.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\result_1.jpg', '2026-01-11 21:42:37', NULL, NULL, NULL, 17, '12');
INSERT INTO `detect_task` VALUES (33, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\1.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\result_1.jpg', '2026-01-11 21:43:03', NULL, NULL, NULL, 18, '12');
INSERT INTO `detect_task` VALUES (35, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\1.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\result_1.jpg', '2026-01-11 21:49:19', NULL, NULL, NULL, 18, '12');
INSERT INTO `detect_task` VALUES (36, 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/uploads\\17.jpg', 'C:\\Users\\admin\\Desktop\\crc_flask\\app\\static/results\\result_17.jpg', '2026-01-11 21:49:33', NULL, NULL, NULL, 20, '0');

-- ----------------------------
-- Table structure for sample
-- ----------------------------
DROP TABLE IF EXISTS `sample`;
CREATE TABLE `sample`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `sample_code` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '样品编号',
  `collect_date` date NULL DEFAULT NULL COMMENT '采集日期',
  `collector` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '采集人',
  `collect_location` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL COMMENT '采集地点',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `final_strain_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NULL DEFAULT NULL,
  `final_confidence` float NULL DEFAULT NULL,
  `last_detect_time` datetime NULL DEFAULT NULL,
  `last_detect_count` int NULL DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `sample_code`(`sample_code` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 21 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of sample
-- ----------------------------
INSERT INTO `sample` VALUES (4, '1212', '2025-12-26', '阿松大发', '生产车间', '2025-12-26 10:07:03', '瑞士乳杆菌 Lactobacillus helveticus', 0.934551, '2025-12-26 02:07:03', NULL);
INSERT INTO `sample` VALUES (6, '112', '2025-12-26', NULL, '实验室A', '2025-12-26 13:51:37', '泡囊短波单胞菌Brevundimonas vesicularis', 0.923135, '2025-12-26 05:51:38', NULL);
INSERT INTO `sample` VALUES (9, '12444', '2025-12-10', NULL, '实验室A', '2025-12-26 15:45:23', '泡囊短波单胞菌Brevundimonas vesicularis', 0.918214, '2025-12-26 07:45:23', 31);
INSERT INTO `sample` VALUES (11, '12546', '2025-12-26', '111', '生产车间', '2025-12-26 17:21:02', '瑞士乳杆菌 Lactobacillus helveticus', 0.944904, '2025-12-26 09:21:02', 30);
INSERT INTO `sample` VALUES (12, '333', '2025-12-19', NULL, '实验室A', '2025-12-26 17:21:40', '瑞士乳杆菌 Lactobacillus helveticus', 0.757356, '2025-12-26 09:21:40', 15);
INSERT INTO `sample` VALUES (13, '111', '2025-12-19', NULL, '生产车间', '2025-12-26 17:31:51', '瑞士乳杆菌 Lactobacillus helveticus', 0.896899, '2025-12-26 09:31:51', 22);
INSERT INTO `sample` VALUES (15, '123213', '2025-12-18', NULL, '实验室A', '2025-12-27 11:52:00', '瑞士乳杆菌 Lactobacillus helveticus', 0.625283, '2025-12-27 03:52:01', 7);
INSERT INTO `sample` VALUES (16, '1231231', '2026-01-01', NULL, '实验室A', '2025-12-29 08:54:15', '瑞士乳杆菌 Lactobacillus helveticus', 0.907766, '2025-12-29 00:54:15', 17);
INSERT INTO `sample` VALUES (17, '123123', '2026-01-12', NULL, '实验室A', '2026-01-12 02:16:42', '瑞士乳杆菌 Lactobacillus helveticus', 0.907766, '2026-01-11 21:42:37', 12);
INSERT INTO `sample` VALUES (18, '2459', '2026-01-12', NULL, '实验室B', '2026-01-12 05:43:03', '瑞士乳杆菌 Lactobacillus helveticus', 0.907766, '2026-01-11 21:49:19', 12);
INSERT INTO `sample` VALUES (20, '12424', '2026-01-12', NULL, '生产车间', '2026-01-12 05:49:32', NULL, NULL, NULL, 0);

SET FOREIGN_KEY_CHECKS = 1;
