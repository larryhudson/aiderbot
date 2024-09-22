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

import github_api
import git_commands
import aider_coder

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

def create_pull_request_for_issue(token, owner, repo_name, issue):
    logger.info(f"Processing issue #{issue['number']} for {owner}/{repo_name}")

    # Create a temporary directory within the current working directory
    temp_dir = tempfile.mkdtemp(dir=os.getcwd(), prefix='repo_')
    logger.info(f"Created temporary directory: {temp_dir}")

    try:
        eyes_reaction_id = github_api.create_issue_reaction(token, owner, repo_name, issue['number'], "eyes")

        repo_dir = git_commands.clone_repository(token, temp_dir, owner, repo_name)

        branch_name = f"fix-issue-{issue['number']}"
        git_commands.checkout_new_branch(repo_dir, branch_name)

        files_list = extract_files_list_from_issue(issue['body'])

        # Prepare the prompt
        issue_pr_prompt = f"Please help me resolve this issue.\n\nIssue Title: {issue['title']}\n\nIssue Body: {issue['body']}"

        coding_result = aider_coder.do_coding_request(issue_pr_prompt, files_list, repo_dir)

        main_branch = github_api.get_default_branch(token, owner, repo_name)

        git_commands.push_changes_to_repository(temp_dir, branch_name)

        pr = github_api.create_pull_request(
            token,
            owner,
            repo_name,
            f"Fix issue #{issue['number']}: {coding_result['commit_message']}",
            f"This PR addresses the changes requested in issue #{issue['number']}\n\n{coding_result['summary']}",
            branch_name,
            main_branch
        )
        if not pr:
            logger.error("Failed to create pull request")
            return {"error": "Failed to create pull request"}, 500

        logger.info(f"Pull request created: {pr['html_url']}")

        comment_body = f"I've created a pull request to address this issue: {pr['html_url']}"
        logger.info("Adding comment to the issue")
        github_api.create_issue_comment(token, owner, repo_name, issue['number'], comment_body)
        github_api.delete_issue_reaction(token, owner, repo_name, issue['number'], eyes_reaction_id)
        github_api.create_issue_reaction(token, owner, repo_name, issue['number'], "rocket")

        return {"message": f"Pull request created and issue commented: {pr['html_url']}"}, 200

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return {"error": "An internal error occurred"}, 500

    finally:
        # Clean up the temporary directory
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up temporary directory: {temp_dir}")

def handle_pr_review_comment(token, owner, repo_name, pull_request, comment):
    logger.info(f"Processing PR review comment for PR #{pull_request['number']} in {owner}/{repo_name}")

    # Check if the comment is from the app user
    if comment['user']['login'] == APP_USER_NAME:
        logger.info(f"Ignoring comment from {APP_USER_NAME}")
        return {"message": "Comment from app user ignored"}, 200

    pr_review_comment_id = comment['id']
    eyes_reaction_id = github_api.create_pr_review_comment_reaction(token, owner, repo_name, pr_review_comment_id, "eyes")

    if 'LGTM' in comment['body']:
        logger.info("Comment contains 'LGTM', no action needed")
        return {"message": "Comment acknowledged, no action needed"}, 200

    try:
        # Get the original issue
        issue_number = extract_issue_number_from_pr_title(pull_request['title'])
        logger.info(f"Extracted issue number: {issue_number}")

        issue = github_api.get_issue(token, owner, repo_name, issue_number)
        logger.info(f"Retrieved issue: {issue['number'] if issue else None}")

        # Get the PR diff
        pr_diff = github_api.get_pr_diff(token, owner, repo_name, pull_request['number'])
        logger.info(f"Retrieved PR diff: {'Success' if pr_diff else 'Failed'}")

        # Build the prompt
        prompt = aider_coder.build_pr_review_prompt(issue, pr_diff, comment['body'])

        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(dir=os.getcwd(), prefix='repo_')
        repo_dir = git_commands.clone_repository(token, temp_dir, owner, repo_name, pull_request['head']['ref'])

        # Get the list of files changed in the PR
        changed_pr_files = github_api.get_pr_changed_files(token, owner, repo_name, pull_request['number'])
        mentioned_files = extract_files_list_from_issue(comment['body'])

        files_list = list(set(changed_pr_files + mentioned_files))

        coding_result = aider_coder.do_coding_request(prompt, files_list, repo_dir)

        git_commands.push_changes_to_repository(temp_dir, pull_request['head']['ref'])

        pr_comment_body = f"I've updated the PR based on the review comment.\n\n{coding_result['summary']}"

        github_api.reply_to_pr_review_comment(token, owner, repo_name, pull_request['number'], pr_review_comment_id, pr_comment_body)

        github_api.delete_pr_review_comment_reaction(token, owner, repo_name, pr_review_comment_id, eyes_reaction_id)
        github_api.create_pr_review_comment_reaction(token, owner, repo_name, pr_review_comment_id, "rocket")

        return {"message": "PR updated based on review comment", "commit_message": coding_result['commit_message']}, 200

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return {"error": f"An internal error occurred: {str(e)}"}, 500

    finally:
        # Clean up the temporary directory
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up temporary directory: {temp_dir}")

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
            issue = data['issue']
            repo = data['repository']
            owner = repo['owner']['login']
            repo_name = repo['name']

            result, status_code = create_pull_request_for_issue(token, owner, repo_name, issue)
            return jsonify(result), status_code
        elif event == 'pull_request_review_comment' and data['action'] == 'created':
            comment = data['comment']
            pull_request = data['pull_request']
            repo = data['repository']
            owner = repo['owner']['login']
            repo_name = repo['name']

            result, status_code = handle_pr_review_comment(token, owner, repo_name, pull_request, comment)
            return jsonify(result), status_code
        else:
            logger.info("Event is not handled, ignoring")
            return jsonify({"message": "Received"}), 200
    except Exception as e:
        logger.error(f"An error occurred in webhook handler: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({"error": f"An internal error occurred: {str(e)}"}), 500

from werkzeug.serving import run_simple

class CustomReloader(object):
    def __init__(self, create_app):
        self.create_app = create_app
        self._app = create_app()

    def __call__(self):
        return self._app

    def should_reload(self):
        return False

def create_app():
    return app

if __name__ == '__main__':
    url = 'http://localhost:5000'
    run_simple('localhost', 5000, CustomReloader(create_app), use_reloader=True, use_debugger=True)

