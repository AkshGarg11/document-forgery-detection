"""
ai_models/text/nlp_analysis.py
NLP Anomaly Detection — REAL implementation using TF-IDF + Logistic Regression.

Training pipeline:
  python -m ai_models.text.nlp_analysis --train
  python -m ai_models.text.nlp_analysis --predict "some text here"

How it works:
  1. Extract linguistic features from OCR text:
       - TF-IDF character n-gram vectors (catches typos, substitutions)
       - Readability stats (sentence length, lexical diversity)
       - Regex flags (suspicious date formats, amount mismatches)
  2. A trained Logistic Regression classifies text as Authentic / Forged
"""

from __future__ import annotations
import re
import logging
import pickle
import argparse
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
MODEL_PATH = _HERE / "nlp_model.pkl"
VECTORIZER_PATH = _HERE / "nlp_vectorizer.pkl"

# ── Feature extraction ────────────────────────────────────────────────────

_DATE_PATTERN    = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
_AMOUNT_PATTERN  = re.compile(r"\$[\d,]+\.?\d{0,2}|\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|INR|EUR|GBP)\b")
_CAPS_RATIO      = re.compile(r"[A-Z]")
_WORD_SPLIT      = re.compile(r"\b\w+\b")


def _handcrafted_features(text: str) -> np.ndarray:
    """
    7 handcrafted numeric features:
    [n_chars, n_words, n_sentences, lexical_diversity, n_dates,
     n_amounts, caps_ratio]
    """
    words    = _WORD_SPLIT.findall(text)
    sents    = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    unique   = set(w.lower() for w in words)
    diversity = len(unique) / (len(words) + 1e-6)
    caps_r   = len(_CAPS_RATIO.findall(text)) / (len(text) + 1e-6)

    return np.array([
        len(text),
        len(words),
        len(sents),
        diversity,
        len(_DATE_PATTERN.findall(text)),
        len(_AMOUNT_PATTERN.findall(text)),
        caps_r,
    ], dtype=np.float32)


def extract_nlp_features(text: str) -> tuple[str, np.ndarray]:
    """Return (text_for_tfidf, handcrafted_feature_vector)."""
    return text, _handcrafted_features(text)


# ── Synthetic training data ───────────────────────────────────────────────

_AUTHENTIC_TEMPLATES = [
    "Invoice #{n}\nDate: {date}\nAmount Due: ${amount}\nIssued by: {company}\nPay within 30 days.",
    "Contract Agreement\nParties: {company} and Client\nEffective: {date}\nValue: ${amount}",
    "Receipt\nTransaction ID: {n}\nDate: {date}\nTotal: ${amount}\nThank you for your business.",
    "Employment Letter\nTo Whom It May Concern,\nThis is to certify that {name} is employed at {company} since {date}.",
    "Bank Statement\nAccount #{n}\nStatement Date: {date}\nClosing Balance: ${amount}",
]

_FORGED_TEMPLATES = [
    "Inv0ice #{n}\nDate: {date}\nAmount Due: ${amount}  Amount: ${amount2}\nIssued by: {company_typo}",
    "CONTRAC AGREEMENT\nParties: {company} und Client\nEffective: {date}\nValue: ${amount}",
    "R3ceipt\nTransaction ID: {n}\nDate: {date}\nDate: {date2}\nTotal: ${amount}",
    "Employment Lettter\n{name} is employed at {company} sinse {date}.",
    "Bank Statment\nAccount #{n}\nStatement Date: {date}\nBalance: ${amount}  Balance: ${amount2}",
]


def _random_data(rng, n: int, template_list: list) -> list[str]:
    from datetime import date, timedelta
    samples = []
    for i in range(n):
        tpl  = template_list[i % len(template_list)]
        base = date(2020, 1, 1) + timedelta(days=int(rng.integers(0, 1500)))
        d2   = base + timedelta(days=int(rng.integers(1, 60)))
        text = tpl.format(
            n=rng.integers(1000, 9999),
            date=base.strftime("%Y-%m-%d"),
            date2=d2.strftime("%Y-%m-%d"),
            amount=f"{rng.integers(100, 99999):,}",
            amount2=f"{rng.integers(100, 99999):,}",
            company=rng.choice(["Acme Corp", "GlobalTech", "FinServe Ltd", "BuildRight Inc"]),
            company_typo=rng.choice(["Acme Coorp", "Globa1Tech", "FinServ3 Ltd"]),
            name=rng.choice(["John Smith", "Priya Patel", "Wei Zhang", "Carlos Rivera"]),
        )
        samples.append(text)
    return samples


def _generate_synthetic_dataset(n_per_class: int = 400, seed: int = 99):
    rng = np.random.default_rng(seed)
    authentic = _random_data(rng, n_per_class, _AUTHENTIC_TEMPLATES)
    forged    = _random_data(rng, n_per_class, _FORGED_TEMPLATES)
    texts = authentic + forged
    labels = [0] * n_per_class + [1] * n_per_class
    return texts, labels


# ── Training ──────────────────────────────────────────────────────────────

def train(n_per_class: int = 400) -> None:
    """Train TF-IDF + handcrafted hybrid classifier and save to disk."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score
    from scipy.sparse import hstack, csr_matrix

    logger.info("[NLP] Generating synthetic training data …")
    texts, y = _generate_synthetic_dataset(n_per_class)
    y = np.array(y)

    # TF-IDF on character n-grams (catches typos)
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                  max_features=5000, sublinear_tf=True)
    X_tfidf = vectorizer.fit_transform(texts)

    # Handcrafted features
    hand = np.vstack([_handcrafted_features(t) for t in texts])
    scaler = StandardScaler()
    X_hand = scaler.fit_transform(hand)

    # Combine
    X = hstack([X_tfidf, csr_matrix(X_hand)])

    clf = LogisticRegression(C=5, max_iter=500, random_state=42)
    scores = cross_val_score(clf, X, y, cv=5, scoring="accuracy")
    logger.info("[NLP] CV accuracy: %.3f ± %.3f", scores.mean(), scores.std())

    clf.fit(X, y)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"clf": clf, "scaler": scaler}, f)
    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(vectorizer, f)

    logger.info("[NLP] Model saved → %s", MODEL_PATH)
    print(f"[NLP] Trained. CV accuracy: {scores.mean():.3f} ± {scores.std():.3f}")


# ── Inference ─────────────────────────────────────────────────────────────

def _load_model():
    if not MODEL_PATH.exists() or not VECTORIZER_PATH.exists():
        logger.warning("[NLP] Model not found. Running train() …")
        train()
    with open(MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)
    with open(VECTORIZER_PATH, "rb") as f:
        vectorizer = pickle.load(f)
    return bundle["clf"], bundle["scaler"], vectorizer


def run_nlp_anomaly_detection(text: str) -> float:
    """
    Detect textual anomalies.

    Returns:
        Forgery probability 0.0 – 1.0.
    """
    if not text or not text.strip():
        logger.warning("[NLP] Empty text received — returning 0.5")
        return 0.5
    try:
        from scipy.sparse import hstack, csr_matrix
        clf, scaler, vectorizer = _load_model()
        X_tfidf = vectorizer.transform([text])
        hand    = _handcrafted_features(text).reshape(1, -1)
        X_hand  = scaler.transform(hand)
        X       = hstack([X_tfidf, csr_matrix(X_hand)])
        prob    = clf.predict_proba(X)[0][1]
        logger.info("[NLP] Forgery probability: %.4f", prob)
        return float(prob)
    except Exception as exc:
        logger.error("[NLP] Error: %s", exc)
        return 0.5


# ── CLI ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="NLP anomaly detector")
    parser.add_argument("--train",   action="store_true")
    parser.add_argument("--predict", metavar="TEXT", help="Text to classify")
    args = parser.parse_args()

    if args.train:
        train()
    elif args.predict:
        score = run_nlp_anomaly_detection(args.predict)
        label = "Forged" if score > 0.6 else ("Suspicious" if score > 0.35 else "Authentic")
        print(f"NLP score: {score:.4f}  →  {label}")
    else:
        parser.print_help()
