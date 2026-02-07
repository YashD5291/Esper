"""Inspect CoreML model files to determine input/output tensor names, shapes, and dtypes."""

import coremltools as ct
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "coreml"

# Use .mlpackage for inspection (readable specs), .mlmodelc for runtime
MLPACKAGE_DIR = MODEL_DIR / "mlpackages"

MODELS = {
    "Preprocessor": MLPACKAGE_DIR / "Preprocessor.mlpackage",
    "Encoder": MLPACKAGE_DIR / "Encoder.mlpackage",
    "MelEncoder": MLPACKAGE_DIR / "MelEncoder.mlpackage",
    "Decoder": MLPACKAGE_DIR / "Decoder.mlpackage",
    "JointDecision": MLPACKAGE_DIR / "JointDecision.mlpackage",
}

# Also check these compiled-only models
COMPILED_ONLY = [
    "Melspectrogram_15s.mlmodelc",
    "ParakeetEncoder_15s.mlmodelc",
    "ParakeetDecoder.mlmodelc",
    "JointDecisionv2.mlmodelc",
    "RNNTJoint.mlmodelc",
]


def describe_feature(feat):
    name = feat.name
    if feat.type.HasField("multiArrayType"):
        ma = feat.type.multiArrayType
        shape = list(ma.shape)
        dtype = ct.proto.FeatureTypes_pb2.ArrayFeatureType.ArrayDataType.Name(ma.dataType)
        if ma.shapeRange.sizeRanges:
            ranges = [f"[{r.lowerBound}..{r.upperBound}]" for r in ma.shapeRange.sizeRanges]
            return f"{name}: shape={shape} dtype={dtype} range={ranges}"
        return f"{name}: shape={shape} dtype={dtype}"
    return f"{name}: (unknown type)"


def inspect_model(label, path):
    print(f"\n{'='*70}")
    print(f"MODEL: {label}  ({path.name})")
    print(f"{'='*70}")

    try:
        model = ct.models.MLModel(str(path))
    except Exception as e:
        print(f"  FAILED to load: {e}")
        return

    spec = model.get_spec()

    print("\n  INPUTS:")
    for inp in spec.description.input:
        print(f"    {describe_feature(inp)}")

    print("\n  OUTPUTS:")
    for out in spec.description.output:
        print(f"    {describe_feature(out)}")

    if spec.description.state:
        print("\n  STATES:")
        for st in spec.description.state:
            if st.type.HasField("multiArrayType"):
                ma = st.type.multiArrayType
                shape = list(ma.shape)
                dtype = ct.proto.FeatureTypes_pb2.ArrayFeatureType.ArrayDataType.Name(ma.dataType)
                print(f"    {st.name}: shape={shape} dtype={dtype}")


if __name__ == "__main__":
    print("=== MLPACKAGE MODELS (readable specs) ===")
    for label, path in MODELS.items():
        if path.exists():
            inspect_model(label, path)
        else:
            print(f"\n  SKIPPED: {label} ({path})")

    print("\n\n=== COMPILED-ONLY MODELS (.mlmodelc) ===")
    print("Note: .mlmodelc cannot be introspected via coremltools.")
    print("Check model.mil files for tensor info.")
    for name in COMPILED_ONLY:
        path = MODEL_DIR / name
        mil_path = path / "model.mil"
        if mil_path.exists():
            print(f"\n  {name}: model.mil exists (see file for details)")
        elif path.exists():
            print(f"\n  {name}: exists but no model.mil")
        else:
            print(f"\n  {name}: NOT FOUND")
