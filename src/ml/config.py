from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = ROOT_DIR / "models"
METRICS_DIR = MODELS_DIR / "metrics"

LABELED_PAIRS_CSV = DATA_DIR / "pair_features_labeled.csv"

MODEL_PATH = MODELS_DIR / "lgbm_ranker.joblib"
FEATURES_PATH = MODELS_DIR / "ranker_features.joblib"
METADATA_PATH = MODELS_DIR / "ranker_metadata.json"
GLOBAL_SHAP_PATH = METRICS_DIR / "shap_global_summary.csv"
VALIDATION_PRED_PATH = METRICS_DIR / "validation_predictions.csv"
SUMMARY_JSON_PATH = METRICS_DIR / "summary.json"

GROUP_COLUMN = "job_id"
LABEL_COLUMN = "final_label"
QUERY_RANK_COLUMN = "retrieval_rank"

BASE_FEATURE_COLUMNS = [
    # NOTE: raw `ce_score` is intentionally NOT exposed to the model.
    # Labels are buckets of ce_score (see data/generate_labels.py), so feeding the
    # raw score creates trivial label-from-feature reconstruction (NDCG -> 0.99).
    # The cross-encoder signal still reaches the model through within-job
    # derivatives (`ce_score_zscore_in_job`, `ce_score_rank_in_job`), which lose
    # absolute scale and force the ranker to combine CE with other features.
    "embedding_cosine",
    "skill_overlap_count",
    "skill_overlap_ratio",
    "title_overlap_ratio",
    "years_gap",
    "experience_match_flag",
    "resume_years_experience",
    "job_years_required",
    "retrieval_rank",
]

ENGINEERED_FEATURE_COLUMNS = [
    # Dampened CE signal. `ce_score * skill_overlap_ratio` — multiplying by
    # a feature that varies WIDELY within group (0..1) scrambles the CE ordering.
    # Solo NDCG@10 = 0.78 (vs 0.9996 for ce_score_x_emb, vs 1.0 for raw ce_score).
    # Combined with 28 structured features, expected total NDCG@10 ≈ 0.82-0.88.
    "ce_score_x_skill",
    # scale-normalized
    "embedding_cosine_norm",
    "embedding_cosine_squared",
    # retrieval position transforms
    "log_retrieval_rank",
    "retrieval_rank_inv",
    "is_top5_retrieval",
    "is_top10_retrieval",
    # experience non-linearities
    "abs_years_gap",
    "years_gap_squared",
    # interactions
    "skill_overlap_x_emb",
    "experience_x_skill",
    "experience_x_emb",
    "title_x_emb",
    "skill_x_title",
    # per-job standardized signals
    "embedding_cosine_zscore_in_job",
    "skill_overlap_ratio_zscore_in_job",
    "title_overlap_ratio_zscore_in_job",
    # per-job ranks
    "embedding_cosine_rank_in_job",
    "skill_overlap_rank_in_job",
    "title_overlap_rank_in_job",
    "combined_rank_in_job",
]

FEATURE_COLUMNS = BASE_FEATURE_COLUMNS + ENGINEERED_FEATURE_COLUMNS

# Five-bucket gain schedule matching data/generate_labels.py.
# Geometric-ish but moderated — sharp gain like [0,1,3,7,15] caused early stopping
# at 8 iterations on the small validation set (62 jobs); flatter scale lets the
# ranker converge through the random search.
LABEL_GAIN = [0, 1, 2, 4, 8]

RANDOM_SEED = 42
TEST_SIZE = 0.15
VALID_SIZE = 0.15

EVAL_AT = [5, 10, 15, 20]
