from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
import hmac
import hashlib
import re
import os
import logging
import tempfile
import shutil
import subprocess

import github_api
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
APP_USER_NAME = os.getenv('GITHUB_APP_USER_NAME', 'larryhudson-aider-github[bot]')
ALLOWED_USERNAME = os.getenv('ALLOWED_USERNAME')

def is_aiderbot_mentioned(text):
    return "@aiderbot" in text.lower()

def create_pull_request_for_issue(*, token, owner, repo_name, issue, comments=None):
    logger.info(f"Processing issue #{issue['number']} for {owner}/{repo_name}")

    if not comments:
        if not is_aiderbot_mentioned(issue['title']) and not is_aiderbot_mentioned(issue['body']):
            logger.info(f"Ignoring issue #{issue['number']} as @aiderbot was not mentioned")
            return {"message": "Issue ignored as @aiderbot was not mentioned"}, 200

        if ALLOWED_USERNAME and issue['user']['login'] != ALLOWED_USERNAME:
            logger.info(f"Ignoring issue from non-allowed user: {issue['user']['login']}")
            return {"message": "Issue from non-allowed user ignored"}, 200

    # This function is now handled by the Celery task
    # The implementation details have been moved to the task function
    pass

def is_pr_created_by_bot(pull_request):
    return pull_request['user']['login'] == APP_USER_NAME

def handle_pr_review_comment(*, token, owner, repo_name, pull_request, comment):
    # This function is now handled by the Celery task
    # The implementation details have been moved to the task function
    pass

def extract_issue_number_from_pr_title(title):
    match = re.search(r'#(\d+)', title)
    return int(match.group(1)) if match else None

def extract_files_list_from_issue(issue_body):
    files_list = []
    files_section_started = False
    for line in issue_body.split('\n'):
        if line.strip() == 'Files:':
            files_section_started = True
            continue
        if files_section_started:
            if line.strip().startswith('- '):
                files_list.append(line.strip()[2:])
            elif line.strip() == '':
                break
            else:
                break
    return files_list

def handle_issue_comment(*, token, owner, repo_name, issue, comment):
    logger.info(f"Processing issue comment for issue #{issue['number']} in {owner}/{repo_name}")

    if not is_aiderbot_mentioned(comment['body']):
        logger.info(f"Ignoring issue comment as @aiderbot was not mentioned")
        return {"message": "Issue comment ignored as @aiderbot was not mentioned"}, 200

    # Check if the comment is from the app user
    if comment['user']['login'] == APP_USER_NAME:
        logger.info(f"Ignoring comment from {APP_USER_NAME}")
        return {"message": "Comment from app user ignored"}, 200

    # Check if the comment is from the allowed user (if set)
    if ALLOWED_USERNAME and comment['user']['login'] != ALLOWED_USERNAME:
        logger.info(f"Ignoring comment from non-allowed user: {comment['user']['login']}")
        return {"message": "Comment from non-allowed user ignored"}, 200

    # Check if there's already a pull request for this issue
    existing_prs = github_api.get_pull_requests_for_issue(token, owner, repo_name, issue['number'])
    if existing_prs:
        logger.info(f"Pull request already exists for issue #{issue['number']}")
        return {"message": "Pull request already exists for this issue"}, 200

    # If no existing PR, proceed with creating one
    return create_pull_request_for_issue(token=token, owner=owner, repo_name=repo_name, issue=issue, comments=[comment])

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
        import json
        logger.info(f"Received webhook payload:\n{json.dumps(request.json, indent=2)}")

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

        installation_id = data['installation']['id']
        token = github_api.get_github_token_for_installation(installation_id)
        if not token:
            logger.error("Failed to get GitHub token")
            return jsonify({"error": "Failed to get GitHub token"}), 500

        if event == 'issues' and data['action'] == 'opened':
            task_create_pull_request_for_issue.delay(
                token=token,
                owner=data['repository']['owner']['login'],
                repo_name=data['repository']['name'],
                issue=data['issue']
            )
            return jsonify({"message": "Task added to queue"}), 202
        elif event == 'issue_comment' and data['action'] == 'created':
            task_handle_issue_comment.delay(
                token=token,
                owner=data['repository']['owner']['login'],
                repo_name=data['repository']['name'],
                issue=data['issue'],
                comment=data['comment']
            )
            return jsonify({"message": "Task added to queue"}), 202
        elif event == 'pull_request_review_comment' and data['action'] == 'created':
            task_handle_pr_review_comment.delay(
                token=token,
                owner=data['repository']['owner']['login'],
                repo_name=data['repository']['name'],
                pull_request=data['pull_request'],
                comment=data['comment']
            )
            return jsonify({"message": "Task added to queue"}), 202
        else:
            logger.info("Event is not handled, ignoring")
            return jsonify({"message": "Received"}), 200
    except Exception as e:
        logger.error(f"An error occurred in webhook handler: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({"error": f"An internal error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)

