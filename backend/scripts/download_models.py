"""
Download ML models and save as checkpoints for offline use.

Run once:  python scripts/download_models.py
SSL fix:   python scripts/download_models.py --no-ssl-verify

Saves to: backend/checkpoints/sbert and backend/checkpoints/gpt2
"""

import os, sys, ssl

CHECKPOINTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "checkpoints")
SBERT_DIR = os.path.join(CHECKPOINTS_DIR, "sbert")
GPT2_DIR = os.path.join(CHECKPOINTS_DIR, "gpt2")


def download_sbert(model_name="all-MiniLM-L6-v2"):
    print(f"\n[1/2] Downloading SBERT: {model_name} → {SBERT_DIR}")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        model.save(SBERT_DIR)
        print("  ✅ SBERT checkpoint saved")
        return True
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return False


def download_gpt2(model_name="gpt2"):
    print(f"\n[2/2] Downloading GPT-2: {model_name} → {GPT2_DIR}")
    try:
        from transformers import GPT2LMHeadModel, GPT2TokenizerFast
        GPT2TokenizerFast.from_pretrained(model_name).save_pretrained(GPT2_DIR)
        GPT2LMHeadModel.from_pretrained(model_name).save_pretrained(GPT2_DIR)
        print("  ✅ GPT-2 checkpoint saved")
        return True
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return False


if __name__ == "__main__":
    os.makedirs(CHECKPOINTS_DIR, exist_ok=True)

    if "--no-ssl-verify" in sys.argv:
        print("⚠️  SSL verification disabled")
        ssl._create_default_https_context = ssl._create_unverified_context
        os.environ["CURL_CA_BUNDLE"] = ""
        os.environ["REQUESTS_CA_BUNDLE"] = ""

    sbert_ok = download_sbert()
    gpt2_ok = download_gpt2()

    print(f"\n{'='*50}")
    print(f"  SBERT : {'✅' if sbert_ok else '❌'}")
    print(f"  GPT-2 : {'✅' if gpt2_ok else '❌'}")
    print(f"  Saved : {CHECKPOINTS_DIR}")
    print(f"{'='*50}")
