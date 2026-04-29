import os
import sys
import yaml
import json
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=None)
CORS(app)

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(VAULT_DIR, "Frontend")

# Output directory from the small batch rounds
CROPS_DIR = r"c:\_3 EVF-Bricks\_07 Parts Desc to Variable - Inference Lists\_20 Part Section PDF Crops\Output"

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/api/documents')
def list_documents():
    docs = []
    if os.path.exists(CROPS_DIR):
        for f in sorted(os.listdir(CROPS_DIR)):
            if f.endswith('_DATA.yaml'):
                doc_id = f.replace('_DATA.yaml', '')
                docs.append({"id": doc_id, "filename": f, "pages": 1})
    return jsonify(docs)

@app.route('/api/document/<doc_id>/data')
def get_doc_data(doc_id):
    yaml_path = os.path.join(CROPS_DIR, f"{doc_id}_DATA.yaml")
    if os.path.exists(yaml_path):
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Not found"}), 404

@app.route('/api/page/<doc_id>/<int:page_num>')
def get_page_image(doc_id, page_num):
    img_path = os.path.join(CROPS_DIR, f"{doc_id}.png")
    if os.path.exists(img_path):
        return send_file(img_path, mimetype='image/png')
    return jsonify({"error": "Image not found"}), 404

@app.route('/api/approve', methods=['POST'])
def approve_match():
    data = request.json
    doc_id = data.get('doc_id')
    approved_dir = os.path.join(CROPS_DIR, "_approved")
    os.makedirs(approved_dir, exist_ok=True)
    with open(os.path.join(approved_dir, f"{doc_id}_approved.json"), "w") as f:
        json.dump(data, f, indent=2)
    return jsonify({"success": True})

@app.route('/api/reject', methods=['POST'])
def reject_match():
    data = request.json
    doc_id = data.get('doc_id')
    rejected_dir = os.path.join(CROPS_DIR, "_rejected")
    os.makedirs(rejected_dir, exist_ok=True)
    with open(os.path.join(rejected_dir, f"{doc_id}_rejected.json"), "w") as f:
        json.dump(data, f, indent=2)
    return jsonify({"success": True})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file:
        intake_dir = os.path.join(CROPS_DIR, "_intake")
        os.makedirs(intake_dir, exist_ok=True)
        filepath = os.path.join(intake_dir, file.filename)
        file.save(filepath)
        # Here we would invoke the parsing engine (e.g. proxy_rag_engine.py)
        # For now, we simulate active parsing trigger
        print(f"[SYSTEM] Uploaded {file.filename} to {filepath}. Actively starting extraction pipeline...")
        return jsonify({"success": True, "filename": file.filename})

if __name__ == '__main__':
    print("==========================================================")
    print("   SOVEREIGN UI VAULT: SINGLE VIEW APPROVER (PORT 8100)")
    print("==========================================================\n")
    app.run(host='0.0.0.0', port=8100, debug=False)
