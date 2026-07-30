# BioCLIP + XGBoost 8-Species Colony Classifier - Test Report

Date: 2026-07-09
Architecture: BioCLIP-2 (ViT-B-16) + XGBoost
Device: CPU (Intel i5-13420H)

============================================================================
1. MODEL SUMMARY
============================================================================

  Species:          8
  Feature dims:     768 (BioCLIP image embedding)
  Classifier:       XGBoost (n_estimators=100, max_depth=3)
  Training samples: 244 images
  Training accuracy: 100.0%

  Training set:
    [0] Acinetobacter lwoffii .......... 27 images
    [1] Aspergillus niger .............. 27 images
    [2] Aspergillus unguis ............. 22 images
    [3] Aureobasidium melanogenum ...... 29 images
    [4] Bacillus albus ................. 54 images
    [5] Kocuria palustris .............. 28 images
    [6] Kocuria rhizophila ............. 27 images
    [7] Staphylococcus hominis ......... 30 images

  Top-10 feature importance:
    rank 1: dim 736  (0.1110)
    rank 2: dim 17   (0.0693)
    rank 3: dim 690  (0.0489)
    rank 4: dim 762  (0.0299)
    rank 5: dim 106  (0.0285)
    rank 6: dim 9    (0.0228)
    rank 7: dim 54   (0.0219)
    rank 8: dim 316  (0.0187)
    rank 9: dim 59   (0.0186)
    rank 10: dim 301 (0.0176)

============================================================================
2. TEST RESULTS (6 images)
============================================================================

  Image                          Prediction                 Conf    2nd Choice               Conf    Verdict
  ------------------------------ ------------------------- -------  ----------------------- -------  ---------------
  IMG_20251219_160927.jpg        Acinetobacter lwoffii      87.3%    Staphylococcus hominis   6.5%    [HIGH] direct report
  IMG_20251219_160938.jpg        Acinetobacter lwoffii      68.2%    Staphylococcus hominis  23.8%    [MED] manual review
  IMG_20251219_160943.jpg        Staphylococcus hominis     89.3%    Bacillus albus           4.7%    [HIGH] direct report
  IMG_20251219_161005.jpg        Acinetobacter lwoffii      97.8%    Bacillus albus           0.6%    [HIGH] direct report
  IMG_20251219_161009.jpg        Acinetobacter lwoffii      98.2%    Staphylococcus hominis   0.8%    [HIGH] direct report
  IMG_20251219_161033.jpg        Acinetobacter lwoffii      95.7%    Bacillus albus           1.5%    [HIGH] direct report

  Summary:
    High-confidence (>=85%):  5 / 6  (83.3%)
    Medium (50-85%):          1 / 6  (16.7%)
    Low (<50%):               0 / 6  (0.0%)

  Accuracy: 6/6 matched actual species (100%)
  False positives: 0

============================================================================
3. THREE-TIER DECISION GATEWAY VALIDATION
============================================================================

  Tier 1 [>=85%]:   Auto-generate report      5 images hit
  Tier 2 [50-85%]:  Manual review              1 image hit
  Tier 3 [<50%]:    MALDI-TOF confirmation     0 images hit

  Previous validation (5-species model, out-of-model bacteria):
    - Unknown bacteria scored 55.6% and 46.2%, correctly triggering Tier 2/3.
    - After expanding to 8 species, previously unknown bacteria now correctly identified.

============================================================================
4. FILE STRUCTURE
============================================================================

  bioclip_xgboost/
    train_classifier.py      Training + single-image prediction
    test_classifier.py       Batch testing program
    RESULTS.md               This report
    train/                   8 species x 244 training images
    test/                    6 test images
    model/                   Trained model files
      xgb.json               XGBoost classifier
      label_encoder.pkl      Species name encoder
      embeddings.npy         BioCLIP features (244 x 768)
      labels.npy             Labels

============================================================================
Report generated: 2026-07-09 17:44 GMT+8
