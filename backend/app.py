# from flask import Flask, jsonify
# from transformers import pipeline
# import json

# app = Flask(__name__)

# # Load BERT QA model
# qa_pipeline = pipeline(
#     "question-answering",
#     model="bert-large-uncased-whole-word-masking-finetuned-squad"
# )


# # Load CUAD-style dataset (your JSON file)
# with open("../cuad/test.json") as f:
#     data = json.load(f)

# # Legal questions to extract key clauses
# legal_questions = [
#     "What is the governing law?",
#     "Who are the parties involved?",
#     "What is the agreement date?",
#     "What is the termination clause?",
#     "What is the confidentiality clause?",
#     "What are the payment terms?",
#     "What are the indemnification terms?",
#     "What is the jurisdiction clause?"
# ]

# # 🆕 STEP 1: Add a helper function for rule-based risk detection
# def detect_risks(clause_answers):
#     risks = []

#     # Define risky keywords per clause type
#     risky_patterns = {
#         "termination": ["without notice", "immediate termination", "for any reason"],
#         "indemnification": ["unlimited liability", "hold harmless", "all claims"],
#         "confidentiality": ["perpetual", "without consent", "no termination"],
#         "jurisdiction": ["exclusive jurisdiction", "foreign laws", "non-us court"]
#     }

#     # Loop through extracted clause answers and check for risks
#     for question, answer in clause_answers.items():
#         for clause_type, patterns in risky_patterns.items():
#             if clause_type in question.lower() and isinstance(answer, str):
#                 for pattern in patterns:
#                     if pattern in answer.lower():
#                         risks.append(f"⚠️ Risk in {clause_type.capitalize()} clause: contains '{pattern}'")

#     return risks


# @app.route("/qa", methods=["GET"])
# def extract_legal_clauses():
#     results = {}

#     for contract in data["data"]:
#         contract_title = contract.get("title", "Untitled Contract")
#         results[contract_title] = []

#         for para in contract.get("paragraphs", []):
#             context = para.get("context", "")

#             clause_answers = {}
#             for question in legal_questions:
#                 try:
#                     answer = qa_pipeline({
#                         "context": context,
#                         "question": question
#                     })["answer"]
#                     clause_answers[question] = answer
#                 except Exception as e:
#                     clause_answers[question] = f"Error: {str(e)}"

#             # 🆕 STEP 2: Detect risk flags for this paragraph
#             risk_flags = detect_risks(clause_answers)

#             # 🆕 STEP 3: Add risk flags into results
#             results[contract_title].append({
#                 "context_snippet": context[:200] + "...",
#                 "highlighted_clauses": clause_answers,
#                 "risk_flags": risk_flags
#             })

#     return jsonify(results)


# if __name__ == "__main__":
#     app.run(debug=True)


from flask import Flask, request, jsonify
import boto3
# (which comes with Flask) that "cleans" a filename before you save it to your computer or S3.
from werkzeug.utils import secure_filename
from transformers import pipeline
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
import pdfplumber
import re
import hashlib
from pymongo import MongoClient
from datetime import datetime
import os
import tempfile
from pathlib import Path
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# MongoDB setup
MONGODB_URI = os.getenv("MONGODB_URI", 'mongodb://localhost:27017/')
DB_NAME = os.getenv("DB_NAME", "legal_analyzer")

# connection bridge between your Python code and your MongoDB database.
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
summaries_collection = db['summaries']

#S3 configuration
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# connection object that allows Python script to talk to Amazon S3 
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# Local storage configuration
LOCAL_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
Path(LOCAL_UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
USE_LOCAL_STORAGE = os.getenv("USE_LOCAL_STORAGE", "false").lower() == "true"

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Backend is running"})

# Upload to S3 OR Local Storage + save metadata
@app.route("/upload-s3", methods=["POST"])
def upload_file_s3():
    try:
        if "file" not in request.files:
            return jsonify({"status": "error", "message": "No file part in request"}), 400

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"status": "error", "message": "No file selected"}), 400

        filename = secure_filename(file.filename)

        if USE_LOCAL_STORAGE:
            # Save to local storage
            filepath = os.path.join(LOCAL_UPLOAD_FOLDER, filename)
            file.save(filepath)
            file_url = f"/uploads/{filename}"
        else:
            # Upload to S3
            s3.upload_fileobj(
                file,
                S3_BUCKET_NAME,
                filename,
                ExtraArgs={"ContentType": file.content_type or "application/octet-stream"}
            )
            file_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{filename}"

        db.documents.insert_one({
            "filename": filename,
            "file_url": file_url
        })

        return jsonify({
            "status": "success",
            "file_url": file_url
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Serve local uploaded files
@app.route("/uploads/<filename>", methods=["GET"])
def serve_file(filename):
    try:
        from flask import send_file
        filepath = os.path.join(LOCAL_UPLOAD_FOLDER, secure_filename(filename))
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=False)
        else:
            return jsonify({"status": "error", "message": "File not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
# ------------------ Config ------------------
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ------------------ Load Models ------------------

# 1. Load BERT QA model (fine-tuned on SQuAD) - moved to /ask route
# qa_pipeline = pipeline(
#     "question-answering",
#     model="bert-large-uncased-whole-word-masking-finetuned-squad"
# )

# 2. Rule-based risky clause patterns
risky_patterns = [
    r"(?i)not liable",              # Negation of liability
    r"(?i)no refund",               # Refund denial
    r"(?i)without prior notice",    # Risky unilateral change
    r"(?i)termination.*immediate",  # Harsh termination clauses
]

# ------------------ Helpers ------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
    """Extract text using pdfplumber for better table handling."""
    text = ""
    try:
        # pdfplumber first because it's great at reading tables (like tax forms). 
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        # Fallback to PyPDF2 if pdfplumber fails
        reader = PdfReader(file_path)
        text = "\n".join([
            page.extract_text() for page in reader.pages if page.extract_text()
        ])
    return text.strip()

def is_tax_form(text):
    """Check if the document is a tax form."""
    return "Form 1040" in text or "Tax Return" in text.upper()

def extract_tax_form_data(text):
    """Extract key data from tax form text."""
    data = {}
    # Common patterns for tax forms
    patterns = {
        "total_income": r"Total income[^\d]*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        "tax_owed": r"Tax you owe[^\d]*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        "refund": r"Refund[^\d]*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        "adjusted_gross_income": r"Adjusted gross income[^\d]*(\d+(?:,\d{3})*(?:\.\d{2})?)",
        "taxable_income": r"Taxable income[^\d]*(\d+(?:,\d{3})*(?:\.\d{2})?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data[key] = match.group(1)
    return data

def get_file_hash(file_path):
    """Get SHA256 hash of file content."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

# ------------------ Routes ------------------

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        try:
            full_text = extract_text_from_pdf(file_path)
            return jsonify({"text": full_text})
        except Exception as e:
            return jsonify({"error": f"Failed to read PDF: {str(e)}"}), 500

    return jsonify({"error": "Invalid file type. Only PDFs allowed."}), 400


@app.route("/qa", methods=["POST"])
def question_answering():
    try:
        if 'file' not in request.files or 'question' not in request.form:
            return jsonify({"error": "File or question missing"}), 400

        file = request.files['file']
        question = request.form['question']

        # Save to a temporary file so we can use extract_text_from_pdf()
        # (pdfplumber-first; much better for forms/tables than PyPDF2 on streams).
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
            file.save(tmp_path)
            full_text = extract_text_from_pdf(tmp_path)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        if not full_text.strip():
            return jsonify({"error": "No text extracted from PDF"}), 400

        # Normalize text but preserve structural boundaries for better QA.
        # - Convert literal "\\n" sequences to real newlines
        # - Normalize whitespace without collapsing everything into one line
        full_text = full_text.replace('\\n', '\n')
        full_text = full_text.replace('\r', '\n')
        full_text = re.sub(r"[\t\u00A0]+", " ", full_text)
        full_text = re.sub(r"[ ]+", " ", full_text)
        full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()

        # Tokenize question into content words.
        stop_words = {
            'what', 'is', 'the', 'a', 'an', 'are', 'do', 'does', 'did', 'how', 'why', 'when', 'where',
            'which', 'who', 'whom', 'whose', 'can', 'could', 'should', 'would', 'will', 'be', 'have',
            'has', 'had', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from', 'or', 'and', 'but',
            'if', 'my', 'your', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'this', 'that', 'these',
            'those', 'please'
        }
        raw_q_words = [w.lower() for w in re.findall(r'\b\w+\b', question)]
        question_words = {w for w in raw_q_words if len(w) > 2 and w not in stop_words}
        if not question_words:
            question_words = {w for w in raw_q_words if len(w) > 2}

        clause_like_question = any(t in raw_q_words for t in ('clause', 'section', 'article', 'provision', 'terms'))
        wants_datetime = any(t in raw_q_words for t in ('date', 'time', 'when'))
        wants_amount = any(t in raw_q_words for t in ('amount', 'cost', 'price', 'fee', 'refund', 'payment', 'total', 'dollars', 'usd', 'how', 'much'))

        # Split into sentences, respecting newlines as boundaries too.
        sentences = re.split(r'(?<=[.!?])\s+|\n+', full_text)
        sentences = [s.strip() for s in sentences if len(s.strip().split()) >= 3]
        if not sentences:
            return jsonify({"answer": "No text found in document."})

        # Build overlapping passages (sliding windows of sentences).
        window_size = 4
        stride = 2
        passages: list[tuple[int, str]] = []
        for i in range(0, len(sentences), stride):
            passage = " ".join(sentences[i:i + window_size]).strip()
            if passage:
                passages.append((i, passage))
            if i + window_size >= len(sentences):
                break

        # Score a passage by keyword overlap and heading-like cues.
        def score_text_block(block: str) -> int:
            block_lower = block.lower()
            unique_hits = sum(1 for w in question_words if w in block_lower)
            freq_hits = sum(block_lower.count(w) for w in question_words)

            heading_boost = 0
            # Boost if it looks like a section heading for a key term (e.g., "10. Termination" or "Termination:")
            for w in question_words:
                if re.search(rf"(^|\b)\d+(?:\.\d+)*\s*{re.escape(w)}\b", block_lower):
                    heading_boost += 8
                if re.search(rf"(^|\b){re.escape(w)}\s*[:\-]", block_lower):
                    heading_boost += 6
                if re.search(rf"\b{re.escape(w)}\b", block_lower) and block_lower.startswith(w):
                    heading_boost += 4

            length_penalty = 0
            if len(block) > 900:
                length_penalty = -4

            url_penalty = -10 if ('http://' in block_lower or 'https://' in block_lower or 'www.' in block_lower) else 0

            pattern_boost = 0
            if wants_datetime:
                if re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", block):
                    pattern_boost += 10
                if re.search(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)?\b|\b\d{1,2}\s*(?:AM|PM)\b", block, flags=re.IGNORECASE):
                    pattern_boost += 8
            if wants_amount:
                if re.search(r"\$\s*\d[\d,]*(?:\.\d{2})?\b", block):
                    pattern_boost += 8

            return unique_hits * 10 + freq_hits * 2 + heading_boost + length_penalty + url_penalty + pattern_boost

        best_passage = ""
        best_start = 0
        best_score = -10**9
        for start_idx, p in passages:
            s = score_text_block(p)
            if s > best_score:
                best_score = s
                best_passage = p
                best_start = start_idx

        if best_score <= 0:
            return jsonify({"answer": "No relevant information found in the document."})

        # Expand a little context around the best window so we don't miss the key value
        # just outside the initial passage.
        context_start = max(0, best_start - 2)
        context_end = min(len(sentences), best_start + window_size + 4)
        context_block = " ".join(sentences[context_start:context_end]).strip()

        # For clause/section questions, return the best context block (more context).
        # For general questions, return the best 1-2 sentences inside that context.
        if clause_like_question:
            # Trim to the sentences that actually mention the clause topic
            # by returning a short span around the best match.
            clause_noise = {'clause', 'section', 'article', 'provision', 'terms'}
            focus_terms = {w for w in question_words if w not in clause_noise}

            # Very lightweight stemming: use a short root so "terminate/terminated/termination" all match.
            focus_roots = {t[:6] for t in focus_terms if len(t) >= 6}
            if not focus_roots:
                focus_roots = set(focus_terms)

            ctx_sents = re.split(r'(?<=[.!?])\s+', context_block)
            ctx_sents = [s.strip() for s in ctx_sents if s.strip()]

            best_idx = None
            best_local = -1
            for idx, s in enumerate(ctx_sents):
                s_lower = s.lower()
                root_hits = sum(s_lower.count(r) for r in focus_roots)
                term_hits = sum(1 for t in focus_terms if t in s_lower)
                score = root_hits * 2 + term_hits * 3
                if score > best_local:
                    best_local = score
                    best_idx = idx

            if best_idx is not None and best_local > 0:
                span_start = best_idx
                span_end = min(len(ctx_sents), best_idx + 3)  # up to 3 sentences
                answer = " ".join(ctx_sents[span_start:span_end])
            else:
                answer = context_block
        else:
            # For general questions, prefer concise value extraction when possible.
            if wants_datetime:
                d = re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", context_block)
                t = re.search(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)?\b|\b\d{1,2}\s*(?:AM|PM)\b", context_block, flags=re.IGNORECASE)
                if d and t:
                    answer = f"{d.group(0)} {t.group(0)}"
                elif d:
                    answer = d.group(0)
                else:
                    answer = context_block
            elif wants_amount:
                m = re.search(r"\$\s*\d[\d,]*(?:\.\d{2})?\b", context_block)
                if m:
                    answer = m.group(0).replace(' ', '')
                else:
                    answer = context_block
            else:
                passage_sents = re.split(r'(?<=[.!?])\s+', context_block)
                passage_sents = [s.strip() for s in passage_sents if s.strip()]
                ranked = []
                for s in passage_sents:
                    s_lower = s.lower()
                    hits = sum(1 for w in question_words if w in s_lower)
                    ranked.append((hits, -len(s), s))
                ranked.sort(reverse=True, key=lambda x: (x[0], x[1]))
                top = [t[2] for t in ranked if t[0] > 0][:2]
                answer = " ".join(top) if top else best_passage

        # Hard cap so we never dump huge chunks back.
        answer = answer.strip()
        if len(answer) > 1200:
            answer = answer[:1200].rstrip() + "…"

        return jsonify({"answer": answer})
        
    except Exception as e:
        print(f"QA Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# @app.route("/qa", methods=["POST"])
# def extract_legal_clauses():
#     data = request.get_json()
#     context = data.get("text", "")

#     if not context:
#         return jsonify({"error": "No input text provided"}), 400

#     questions = [
#         "What is the governing law?",
#         "Who are the parties involved?",
#         "What is the agreement date?",
#         "What is the termination clause?",
#         "What is the confidentiality clause?",
#         "What are the payment terms?",
#         "What are the indemnification terms?",
#         "What is the jurisdiction clause?"
#     ]

#     answers = {}
#     for question in questions:
#         try:
#             result = qa_pipeline({"context": context, "question": question})
#             answers[question] = result["answer"]
#         except Exception as e:
#             answers[question] = f"Error: {str(e)}"

#     return jsonify({"clauses": answers})

# @app.route("/risk", methods=["POST"])
# def detect_risky_clauses():
#     data = request.get_json()
#     text = data.get("text", "")

#     if not text:
#         return jsonify({"error": "No text provided"}), 400

#     risks = []
#     for pattern in risky_patterns:
#         matches = re.findall(pattern, text)
#         if matches:
#             risks.append({
#                 "pattern": pattern,
#                 "matches": matches
#             })

#     return jsonify({"risky_clauses": risks})

@app.route('/risk', methods=['POST'])
def detect_risk():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in request'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    try:
        reader = PdfReader(filepath)
        text = ''
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + '\n'

        # Clean text
        text = text.replace('\\n', ' ').replace('\n', ' ')
        text = ' '.join(text.split())
        
        # Risk keyword mapping
        risk_keywords = {'terminate': ['terminate', 'termination', 'terminated'],
                        'indemnify': ['indemnif', 'indemnit'],
                        'liability': ['liability', 'liable'],
                        'breach': ['breach', 'breached'],
                        'penalty': ['penalty', 'penalties']}
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        risky_clauses = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            for risk_type, keywords in risk_keywords.items():
                if any(kw in sentence_lower for kw in keywords):
                    risky_clauses.append(f"[{risk_type.upper()}] {sentence}")
                    break  # Don't flag same sentence twice
        
        if not risky_clauses:
            risky_clauses = ["No obvious risk clauses detected."]

        return jsonify({'risky_clauses': risky_clauses})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

## Summarization - lazy loading
# Model is loaded only when summarize() is called to reduce startup memory

def summarize_text(text: str) -> str:
    """Summarize text using extractive summarization. Simple and reliable."""
    print(f"DEBUG: summarize_text called with {len(text)} chars")
    # Clean up text
    text = ' '.join(text.split()).strip()
    
    if len(text) < 200:
        print(f"DEBUG: Text too short ({len(text)} chars), returning as-is")
        return text  # Too short to summarize
    
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    print(f"DEBUG: Split into {len(sentences)} sentences")
    
    # Extract key sentences (first sentence + key topic sentences)
    key_sentences = []
    if sentences:
        key_sentences.append(sentences[0])  # Always include first sentence
    
    # Add sentences with important keywords
    keywords = ['agreement', 'contract', 'clause', 'term', 'condition', 'liability', 'obligation', 'party', 'payment', 'termination']
    for sentence in sentences[1:]:
        if len(key_sentences) < 5 and any(kw in sentence.lower() for kw in keywords):
            key_sentences.append(sentence)
    
    # If we don't have enough key sentences, add more from the beginning
    if len(key_sentences) < 3:
        key_sentences.extend(sentences[1:4])
    
    summary = ' '.join(key_sentences[:5]).strip()
    return summary if summary else text[:300]

@app.route("/summarize", methods=["POST"])
def summarize():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        # Save uploaded file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        file.save(file_path)

        # Compute file hash for caching
        file_hash = get_file_hash(file_path)
        print(f"File hash: {file_hash}")

        # Check DB connection
        try:
            client.admin.command('ping')
            print("DB connected")
        except Exception as e:
            print(f"DB connection failed: {e}")

        # Check if summary already exists by filename
        existing_summary = summaries_collection.find_one({'filename': file.filename})
        print(f"Existing summary found by filename: {existing_summary is not None}")
        if existing_summary:
            # Handle both old and new format
            summary_text = existing_summary.get('summary') or existing_summary.get('fast_summary') or ''
            return jsonify({'summary': summary_text, 'cached': True})

        # Extract text
        text = extract_text_from_pdf(file_path)
        if not text.strip():
            return jsonify({'error': 'No readable text found in PDF'}), 400

        # Check if it's a tax form
        if is_tax_form(text):
            tax_data = extract_tax_form_data(text)
            if tax_data:
                summary_str = "Tax Form Summary:\n" + "\n".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in tax_data.items()])
                # Save to database
                try:
                    client.admin.command('ping')  # Test connection
                    summaries_collection.update_one(
                        {'filename': file.filename},
                        {'$set': {
                            'file_hash': file_hash,
                            'summary': summary_str,
                            'timestamp': datetime.utcnow()
                        }},
                        upsert=True
                    )
                except Exception as e:
                    print(f"DB save failed: {e}")
                return jsonify({'summary': summary_str, 'cached': False})

        # Summarize text
        summary = summarize_text(text)
        
        # Save to database
        try:
            client.admin.command('ping')  # Test connection
            result = summaries_collection.update_one(
                {'filename': file.filename},
                {'$set': {
                    'file_hash': file_hash,
                    'summary': summary,
                    'timestamp': datetime.utcnow()
                }},
                upsert=True
            )
            print(f"✅ Saved to DB - Matched: {result.matched_count}, Upserted ID: {result.upserted_id}")
        except Exception as e:
            print(f"❌ DB save failed: {e}")
        
        return jsonify({'summary': summary, 'cached': False})

    except Exception as e:
        print("Error:", e)
        return jsonify({'error': str(e)}), 500



@app.route("/summaries", methods=["GET"])
def get_summaries():
    summaries = list(summaries_collection.find({}, {'_id': 0}).sort('timestamp', -1))
    return jsonify(summaries)

# ------------------ Main ------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)

