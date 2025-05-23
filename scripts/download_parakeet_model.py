import nemo.collections.asr as nemo_asr
import pathlib

MODEL_NAME = "parakeet-tdt-0.6b"  # base model name used by NeMo
TARGET_DIR = pathlib.Path("parakeet-tdt-0.6b-v2")
TARGET_DIR.mkdir(exist_ok=True)
TARGET_FILE = TARGET_DIR / f"{MODEL_NAME}-v2.nemo"

print(f"Downloading {MODEL_NAME} model to {TARGET_FILE} ...")
model = nemo_asr.models.EncDecRNNTBPEModel.from_pretrained(model_name=MODEL_NAME)
model.save_to(str(TARGET_FILE))
print("Download complete.")
