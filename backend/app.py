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
from transformers import pipeline
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
import pdfplumber
import torch
import re
import hashlib
from pymongo import MongoClient
from datetime import datetime
import os
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

# MongoDB setup
mongo_uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(mongo_uri)
db = client['legal_analyzer']
summaries_collection = db['summaries']

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
    # Lazy load QA model on first request
    qa_pipeline = pipeline("question-answering", model="deepset/bert-base-cased-squad2")

    if 'file' not in request.files or 'question' not in request.form:
        return jsonify({"error": "File or question missing"}), 400

    file = request.files['file']
    question = request.form['question']

    pdf_reader = PdfReader(file)
    full_text = ""
    for page in pdf_reader.pages:
        full_text += page.extract_text()

    result = qa_pipeline(question=question, context=full_text)

    # if result['score'] < 0.15:
    #     return jsonify({"answer": "No relevant information found about pets in the document."})

    return jsonify({"answer": result["answer"]})

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


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

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

        # Simple risk keyword matching (placeholder logic)
        risk_keywords = ['terminate', 'indemnify', 'liability', 'penalty', 'breach']
        sentences = text.split('. ')
        risky_clauses = [s.strip() 
                         for s in sentences 
                         if any(kw in s.lower() 
                                for kw in risk_keywords)]

        return jsonify({'risky_clauses': risky_clauses})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

## Summarization models - lazy loading
# Models are loaded only when summarize() is called to reduce startup memory

def get_summarizer(quality: str):
    """Lazy load summarization model on first use."""
    model_name = "sshleifer/distilbart-cnn-12-6"
    return pipeline("summarization", model=model_name)

def preprocess_text(text: str) -> str:
    """Simple preprocessing: remove extra whitespace and normalize."""
    return ' '.join(text.split())

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
            return jsonify({'fast_summary': existing_summary['fast_summary'], 'accurate_summary': existing_summary['accurate_summary'], 'cached': True})

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
                            'fast_summary': summary_str,
                            'accurate_summary': summary_str,
                            'timestamp': datetime.utcnow()
                        }},
                        upsert=True
                    )
                except Exception as e:
                    print(f"DB save failed: {e}")
                return jsonify({'fast_summary': summary_str, 'accurate_summary': summary_str, 'cached': False})
            else:
                # Fallback to summarization
                pass

        # Preprocess text
        text = preprocess_text(text)

        # Summarize text with both fast and accurate modes
        fast_summary = summarize_text(text, quality="fast")
        accurate_summary = summarize_text(text, quality="accurate")
        
        # Save to database
        try:
            client.admin.command('ping')  # Test connection
            summaries_collection.update_one(
                {'filename': file.filename},
                {'$set': {
                    'file_hash': file_hash,
                    'fast_summary': fast_summary,
                    'accurate_summary': accurate_summary,
                    'timestamp': datetime.utcnow()
                }},
                upsert=True
            )
        except Exception as e:
            print(f"DB save failed: {e}")
        
        return jsonify({'fast_summary': fast_summary, 'accurate_summary': accurate_summary, 'cached': False})

    except Exception as e:
        print("Error:", e)
        return jsonify({'error': str(e)}), 500


def split_text_into_chunks(text: str, max_chars: int = 1500) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text.replace('\n', ' ').strip())
    chunks: list[str] = []
    current_chunk = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk = f"{current_chunk} {sentence}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def summarize_text(text: str, quality: str = "fast") -> str:
    """Summarize text using lazy-loaded model."""
    text = re.sub(r'\s+', ' ', text).strip()
    max_input_chars = 3000 if quality == "fast" else 6000
    if len(text) > max_input_chars:
        text = text[:max_input_chars]
    if len(text) < 1200:
        return get_summarizer(quality)(text, max_length=150, min_length=50, do_sample=False)[0]['summary_text']

    chunk_size = 2000 if quality == "fast" else 2500
    chunks = split_text_into_chunks(text, max_chars=chunk_size)
    chunk_summaries: list[str] = []
    for chunk in chunks[:3]:  # Limit to 3 chunks
        chunk_summary = get_summarizer(quality)(
            chunk,
            max_length=100 if quality == "fast" else 120,
            min_length=30 if quality == "fast" else 50,
            do_sample=False
        )[0]['summary_text']
        chunk_summaries.append(chunk_summary)

    combined_summary = ' '.join(chunk_summaries)
    if len(combined_summary) > 1000:
        combined_summary = get_summarizer(quality)(
            combined_summary,
            max_length=120 if quality == "fast" else 150,
            min_length=40 if quality == "fast" else 60,
            do_sample=False
        )[0]['summary_text']

    return combined_summary


@app.route("/summaries", methods=["GET"])
def get_summaries():
    summaries = list(summaries_collection.find({}, {'_id': 0}).sort('timestamp', -1))
    return jsonify(summaries)

# ------------------ Main ------------------
if __name__ == "__main__":
    app.run(debug=True)

