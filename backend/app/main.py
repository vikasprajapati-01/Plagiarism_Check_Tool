from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import pandas as pd
import io

from app.services.preprocess import preprocess_texts

app = FastAPI(title="Plagiarism Check Tool API")

# -------------------- CORS CONFIG -------------------- #

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Later replace with frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- ROOT CHECK -------------------- #

@app.get("/")
async def root():
    return {"message": "Plagiarism Checker Backend Running"}

# -------------------- INPUT API -------------------- #

@app.post("/input/data")
async def input_data(
    file: Optional[UploadFile] = File(None),
    texts: Optional[str] = Form(None)
):
    rows = []

    # -------- Case 1: File Upload -------- #
    if file:
        contents = await file.read()
        filename = file.filename.lower()

        try:
            # CSV File
            if filename.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(contents))
                first_column = df.columns[0]
                rows = df[first_column].dropna().astype(str).tolist()

            # Excel File
            elif filename.endswith(".xlsx") or filename.endswith(".xls"):
                df = pd.read_excel(io.BytesIO(contents))
                first_column = df.columns[0]
                rows = df[first_column].dropna().astype(str).tolist()

            # Text File
            elif filename.endswith(".txt"):
                text_data = contents.decode("utf-8").splitlines()
                rows = [line.strip() for line in text_data if line.strip()]

            else:
                return {"status": "Unsupported file format"}

        except Exception as e:
            return {"status": "File processing error", "error": str(e)}

    # -------- Case 2: Direct JSON Text Input -------- #
    elif texts:
        rows = [t.strip() for t in texts.split(",") if t.strip()]

    # -------- No Input -------- #
    else:
        return {"status": "No input provided"}

    cleaned_rows = preprocess_texts(rows)

    # -------- Unified Response -------- #
    return {
        "total_rows": len(rows),
        "status": "Data processed successfully",
        "original_data": rows,
        "preprocessed_data": cleaned_rows
    }