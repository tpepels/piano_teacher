"""Pinned upstream RubricNet source artifacts for offline verification/export.

The paths and Git blob SHA-1s come from the official master tree at the
recorded commit. No trained artifacts are shipped inside Piano Teacher.
"""
UPSTREAM_REPOSITORY = "https://github.com/PRamoneda/rubricnet"
UPSTREAM_COMMIT = "3ff4a9342948b9588541a2a8524eab68045f6001"
UPSTREAM_LICENSE = "MIT"
OFFICIAL_ARTIFACTS = {
    "checkpoints/rubricnet_cameraready/scaler_0.pkl": "fa98ce49a78406ac293b7fa6301b59530fc330f5",
    "checkpoints/rubricnet_cameraready/scaler_1.pkl": "48e96e12aff7c1a60221481ff971f53a9898f7ef",
    "checkpoints/rubricnet_cameraready/scaler_2.pkl": "de5b457958e63fcd62edc37cecede34184d4fcf7",
    "checkpoints/rubricnet_cameraready/scaler_3.pkl": "778c81aa64ac073f7309053f2229ff358f2d3bff",
    "checkpoints/rubricnet_cameraready/scaler_4.pkl": "54504008a699c4f4dbcbf41cf446e04d30bca087",
    "checkpoints/rubricnet_cameraready/split_0.ckpt": "d8d6d2c7c5068835c82e08d6b75ed9a71c0a898a",
    "checkpoints/rubricnet_cameraready/split_1.ckpt": "5b70fd930b99d5706bbf2cd4e2bc9d229382e42b",
    "checkpoints/rubricnet_cameraready/split_2.ckpt": "b829346b513648e57f6295eca62ff6d8c3dcae36",
    "checkpoints/rubricnet_cameraready/split_3.ckpt": "882220a17f5e2305664142dd93adbcee8f364af1",
    "checkpoints/rubricnet_cameraready/split_4.ckpt": "ca3aa58e88bb2d0cfa640e80fbe90a22d6c489ea",
}
# There are two public orders. Prefer the StandardScaler's own recorded
# feature_names_in_. If missing, export MUST refuse to guess.
BASIC_FEATURES = (
    "rh_pitch_set_lz", "lh_pitch_set_lz", "rh_pitch_range", "lh_pitch_range",
    "lh_average_pitch", "rh_average_pitch", "lh_average_ioi_seconds",
    "rh_average_ioi_seconds", "rh_displacement_rate",
    "lh_displacement_rate", "lh_pitch_entropy", "rh_pitch_entropy",
)
CHIU_FEATURES = BASIC_FEATURES[2:]

# Pinned evaluation corpus and held-out identifiers. Never evaluate training
# examples as held-out samples. These are official upstream Git blob SHA-1s.
OFFICIAL_EVALUATION = {
    "features/cipi-features-ISMIR24.json":
        "c6e19f674c122032a85eb3597f685d5",
    "rubricnet/cipi_splits.json":
        "015239412e5a497806e2dfaf559f78c41fbf0a1a",
}
