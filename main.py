from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
import hmac
import hashlib
import os
import logging
import github_api
import subprocess
from celery_tasks import task_create_pull_request_for_issue, task_handle_pr_review_comment, task_handle_issue_comment

def has_multiple_commits(repo_dir, branch_name):
    """Check if the branch has more than one commit."""
    command = ['git', 'rev-list', '--count', f'origin/main..{branch_name}']
    result = subprocess.run(command, cwd=repo_dir, capture_output=True, text=True, check=True)
    commit_count = int(result.stdout.strip())
    return commit_count > 1

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
        # import json
        # logger.info(f"Received webhook payload:\n{json.dumps(request.json, indent=2)}")

        signature = request.headers.get('X-Hub-Signature-256')
        payload = request.data

        if not verify_webhook_signature(payload, signature):
            logger.warning("Webhook signature verification failed")
            return jsonify({"error": "Request signatures didn't match!"}), 403

        logger.info("Webhook signature verified successfully")

        event = request.headers.get('X-GitHub-Event')
        data = request.json

        if not event or not data:
            return jsonify({"error": "Invalid payload"}), 400

        action = data['action']

        logger.info(f"Handling webhook:\nEvent: {event}\nAction: {action}")

        installation_id = data['installation']['id']
        token = github_api.get_github_token_for_installation(installation_id)
        if not token:
            logger.error("Failed to get GitHub token")
            return jsonify({"error": "Failed to get GitHub token"}), 500

        if event == 'issues' and action == 'opened':
            logger.info("Adding task to queue to create pull request for issue")
            task_create_pull_request_for_issue.delay(
                token=token,
                owner=data['repository']['owner']['login'],
                repo_name=data['repository']['name'],
                issue=data['issue']
            )
            return jsonify({"message": "Task added to queue"}), 202
        elif event == 'issue_comment' and action == 'created':
            logger.info("Adding task to queue to handle issue comment")
            task_handle_issue_comment.delay(
                token=token,
                owner=data['repository']['owner']['login'],
                repo_name=data['repository']['name'],
                issue=data['issue'],
                comment=data['comment']
            )
            return jsonify({"message": "Task added to queue"}), 202
        elif event == 'pull_request_review_comment' and action == 'created':
            logger.info("Adding task to queue to handle PR review comment")
            task = task_handle_pr_review_comment.delay(
                token=token,
                owner=data['repository']['owner']['login'],
                repo_name=data['repository']['name'],
                pull_request=data['pull_request'],
                comment=data['comment']
            )
            logger.info(f"Task added to queue with ID: {task.id}")
            return jsonify({"message": "Task added to queue", "task_id": task.id}), 202
        elif event == 'pull_request_review' and action == 'submitted':
            logger.info("Received pull_request_review event, but it's not handled yet")
            return jsonify({"message": "Received pull_request_review event"}), 200
        else:
            logger.info(f"Event {event} with action {action} is not handled, ignoring")
            return jsonify({"message": "Received"}), 200
    except Exception as e:
        logger.error(f"An error occurred in webhook handler: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({"error": f"An internal error occurred: {str(e)}"}), 500
