from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
import hmac
import hashlib
import os
import logging
from .celery_tasks import task_create_pull_request_for_issue, task_handle_pr_review_comment, task_handle_issue_comment

app = Flask(__name__)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# GitHub App configuration
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', 'your_webhook_secret_here')

def verify_webhook_signature(payload_body, signature_header):
    """Verify that the payload was sent from GitHub by validating SHA256."""
    if not signature_header:
        logger.warning("No signature header provided")
        return False
    hash_object = hmac.new(GITHUB_WEBHOOK_SECRET.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    result = hmac.compare_digest(expected_signature, signature_header)
    return result

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "Hello, World!"})

@app.route('/webhook', methods=['POST'])
def webhook():
    try:

        signature = request.headers.get('X-Hub-Signature-256')
        payload = request.data

        if not verify_webhook_signature(payload, signature):
            logger.warning("Webhook signature verification failed")
            return jsonify({"error": "Request signatures didn't match!"}), 403

        logger.info("Webhook signature verified successfully")

        event = request.headers.get('X-GitHub-Event')
        payload = request.json

        if not event or not payload:
            return jsonify({"error": "Invalid payload"}), 400

        action = payload['action']

        logger.info(f"Handling webhook:\nEvent: {event}\nAction: {action}")

        EVENT_ACTION_TASK_MAP = {
            ('issues', 'opened'): task_create_pull_request_for_issue,
            ('issue_comment', 'created'): task_handle_issue_comment,
            ('pull_request_review_comment', 'created'): task_handle_pr_review_comment
        }

        matching_task = EVENT_ACTION_TASK_MAP.get((event, action))
        if matching_task:
            matching_task.delay(payload)
            return jsonify({"message": f"Task scheduled for event {event} with action {action}"}), 200
        else:
            logger.info(f"Event {event} with action {action} is not handled, ignoring")
            return jsonify({"message": "Received"}), 200
    except Exception as e:
        logger.error(f"An error occurred in webhook handler: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({"error": f"An internal error occurred: {str(e)}"}), 500
