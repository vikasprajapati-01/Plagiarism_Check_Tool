import os
import re
from typing import Iterable, List

import pandas as pd


# A lightweight stop word list keeps dependencies minimal while covering common fillers.
STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'for', 'if', 'in', 'into',
    'is', 'it', 'no', 'not', 'of', 'on', 'or', 'such', 'that', 'the', 'their', 'then',
    'there', 'these', 'they', 'this', 'to', 'was', 'will', 'with'
}


def preprocess_text(text: str) -> str:
    """Normalise a single text snippet for downstream duplicate checks."""
    if text is None:
        return ''

    # Ensure we are always working with a string representation.
    text = str(text).lower()

    # Replace punctuation with spaces so words remain separable.
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Collapse extra whitespace and tokenize for stop-word removal.
    tokens = re.split(r"\s+", text.strip())
    filtered_tokens = [token for token in tokens if token and token not in STOP_WORDS]

    return " ".join(filtered_tokens)


def preprocess_texts(texts: Iterable[str]) -> List[str]:
    """Apply ``preprocess_text`` across an iterable, keeping positional order."""
    return [preprocess_text(text) for text in texts]


def preprocess_dataset(file_path: str) -> pd.DataFrame:
    """Load a CSV dataset, clean the primary text column, and return a dataframe."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_csv(file_path, header=None)

    # Basic column naming for clarity. Column 0 stores the raw text.
    num_cols = len(df.columns)
    new_columns = {0: 'text'}
    for i in range(1, num_cols):
        new_columns[i] = f'col_{i}'

    df = df.rename(columns=new_columns)
    df['cleaned_text'] = preprocess_texts(df['text'])

    return df


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_file_path = os.path.join(current_dir, 'balanced_ai_human_prompts.csv')

    print(f"Processing file: {csv_file_path}")
    processed_df = preprocess_dataset(csv_file_path)

    print("\nPreprocessing complete.")
    print("-" * 30)
    print("First 5 rows of processed data:")
    print("-" * 30)
    pd.set_option('display.max_colwidth', 100)
    print(processed_df[['text', 'cleaned_text']].head())