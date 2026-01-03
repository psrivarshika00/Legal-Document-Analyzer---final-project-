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
from transformers import pipeline, BartTokenizer, BartForConditionalGeneration
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
import torch
import re
import os
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

# ------------------ Config ------------------
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ------------------ Load Models ------------------

# 1. Load BERT QA model (fine-tuned on SQuAD)
qa_pipeline = pipeline(
    "question-answering",
    model="bert-large-uncased-whole-word-masking-finetuned-squad"
)

# 2. Load BART summarization model
bart_tokenizer = BartTokenizer.from_pretrained("facebook/bart-large-cnn")
bart_model = BartForConditionalGeneration.from_pretrained("facebook/bart-large-cnn")

# 3. Rule-based risky clause patterns
risky_patterns = [
    r"(?i)not liable",              # Negation of liability
    r"(?i)no refund",               # Refund denial
    r"(?i)without prior notice",    # Risky unilateral change
    r"(?i)termination.*immediate",  # Harsh termination clauses
]

# ------------------ Helpers ------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

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
            reader = PdfReader(file_path)
            full_text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            return jsonify({"text": full_text})
        except Exception as e:
            return jsonify({"error": f"Failed to read PDF: {str(e)}"}), 500

    return jsonify({"error": "Invalid file type. Only PDFs allowed."}), 400


# Load QA model once globally
qa_pipeline = pipeline("question-answering", model="deepset/bert-base-cased-squad2")

@app.route("/qa", methods=["POST"])
def question_answering():
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
        risky_clauses = [s.strip() for s in sentences if any(kw in s.lower() for kw in risk_keywords)]

        return jsonify({'risky_clauses': risky_clauses})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Load BART model
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

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

        # Extract text from PDF
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text

        if not text.strip():
            return jsonify({'error': 'No readable text found in PDF'}), 400

        # Summarize text
        summary = summarizer(text[:3000], max_length=200, min_length=60, do_sample=False)
        return jsonify({'summary': summary[0]['summary_text']})

    except Exception as e:
        print("Error:", e)
        return jsonify({'error': str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Legal Document Analyzer is running."})

# ------------------ Main ------------------
if __name__ == "__main__":
    app.run(debug=True)

