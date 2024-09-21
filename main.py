from flask import Flask, request, jsonify
import hmac
import hashlib
from flask import Flask, request, jsonify
import hmac
import hashlib
import os
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)

# Replace with your actual GitHub App's secret
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', 'your_webhook_secret_here')


def verify_webhook_signature(payload_body, signature_header):
    """Verify that the payload was sent from GitHub by validating SHA256.

    Args:
        payload_body: original request body to verify
        signature_header: header received from GitHub (x-hub-signature-256)
    
    Returns:
        bool: True if the signature is valid, False otherwise
    """
    if not signature_header:
        return False
    hash_object = hmac.new(GITHUB_WEBHOOK_SECRET.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "Hello, World!"})

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Hub-Signature-256')
    payload = request.data

    if not verify_webhook_signature(payload, signature):
        return jsonify({"error": "Request signatures didn't match!"}), 403

    event = request.headers.get('X-GitHub-Event')
    if event == 'issues':
        # Handle issue event
        data = request.json
        if data['action'] == 'opened':
            # Process new issue
            issue = data['issue']
            # Call your function to handle the new issue
            # handle_new_issue(issue)
            return jsonify({"message": f"Received new issue: {issue['title']}"}), 200

    return jsonify({"message": "Received"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)

