from aider.repo import GitRepo
from flask import Flask, request, jsonify
import hmac
import hashlib
import re
from flask import Flask, request, jsonify
import hmac
import hashlib
import os
import logging
from dotenv import load_dotenv
import requests
import subprocess
import json
import base64
import jwt
import time
import zipfile
import io
import tempfile
import shutil
import filecmp
import uuid
from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

load_dotenv()

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
GITHUB_APP_ID = os.getenv('GITHUB_APP_ID')
GITHUB_PRIVATE_KEY_PATH = os.getenv('GITHUB_PRIVATE_KEY_PATH', 'path/to/your/private-key.pem')
GITHUB_INSTALLATION_ID = os.getenv('GITHUB_INSTALLATION_ID')
APP_USER_NAME = "larryhudson-aider-github[bot]"

# Read the private key from the PEM file
with open(GITHUB_PRIVATE_KEY_PATH, 'r') as key_file:
    GITHUB_PRIVATE_KEY = key_file.read()

def get_github_token():
    try:
        # Open PEM file and read the signing key
        with open(GITHUB_PRIVATE_KEY_PATH, 'rb') as pem_file:
            signing_key = pem_file.read()

        payload = {
            'iat': int(time.time()),
            'exp': int(time.time()) + 600,  # JWT expiration time (10 minutes maximum)
            'iss': GITHUB_APP_ID
        }

        # Create JWT
        jwt_token = jwt.encode(payload, signing_key, algorithm='RS256')

        # Get an installation access token
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        response = requests.post(
            f'https://api.github.com/app/installations/{GITHUB_INSTALLATION_ID}/access_tokens',
            headers=headers
        )

        response.raise_for_status()
        return response.json()['token']
    except FileNotFoundError:
        logger.error(f"Private key file not found: {GITHUB_PRIVATE_KEY_PATH}")
    except jwt.PyJWTError as e:
        logger.error(f"JWT encoding failed: {str(e)}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get GitHub token: {str(e)}")
    except KeyError:
        logger.error("Unexpected response format from GitHub API")
    except Exception as e:
        logger.error(f"Unexpected error in get_github_token: {str(e)}")
    
    return None

def clone_repository(temp_dir, owner, repo, branch='main', ):
    token = get_github_token()
    if not token:
        logger.error("Failed to get GitHub token")
        return None

    clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"

    # clone the repo into the temp_dir
    subprocess.run(['git', 'clone', clone_url, temp_dir], check=True)
    subprocess.run(['git', 'checkout', branch], cwd=temp_dir, check=True)

    return temp_dir

def checkout_new_branch(repo_dir, branch_name):
    try:
        subprocess.run(['git', 'checkout', '-b', branch_name], cwd=repo_dir, check=True)
        return True
    except:
        logger.error(f"Failed to checkout new branch: {branch_name}")
        return False


def push_changes_to_repository(temp_dir, branch):
    try:
        # First, fetch the latest changes from the remote
        subprocess.run(['git', 'fetch', 'origin'], cwd=temp_dir, check=True)
        
        # Check if the branch exists on the remote
        remote_branch_exists = subprocess.run(['git', 'ls-remote', '--exit-code', '--heads', 'origin', branch], 
                                              cwd=temp_dir, capture_output=True).returncode == 0

        push_command_args = ['git', 'push']
        if not remote_branch_exists:
            push_command_args += ['--set-upstream', 'origin', branch]
        else:
            push_command_args += ['origin', branch]

        subprocess.run(push_command_args, cwd=temp_dir, check=True)
        
        logger.info(f"Pushed changes to branch {branch}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to push changes to branch {branch}: {e}")
        logger.error(f"Command output: {e.output.decode() if e.output else 'No output'}")
        return False

def create_branch(owner, repo, branch_name, sha):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "ref": f"refs/heads/{branch_name}",
        "sha": sha
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create branch: {response.text}")
        return None

def create_pull_request(owner, repo, title, body, head, base):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": title,
        "body": body,
        "head": head,
        "base": base
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create pull request: {response.text}")
        return None

def create_issue_comment(owner, repo, issue_number, body):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "body": body
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create issue comment: {response.text}")
        return None

def create_issue_reaction(owner, repo, issue_number, reaction):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/reactions"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    data = {
        "content": reaction
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        reaction_id = response.json()['id']
        return reaction_id
    elif response.status_code == 200:
        reaction_id = response.json()['id']
        return reaction_id
    elif response.status_code == 422:
        logger.error(f"Failed to create issue reaction: {response.text}")
        return response.json()

def delete_issue_reaction(owner, repo, issue_number, reaction_id):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/reactions/{reaction_id}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        return True
    else:
        logger.error(f"Failed to delete issue reaction: {response.text}")
        return False

def create_pr_review_comment_reaction(owner, repo, comment_id, reaction):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "body": reaction
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create PR review comment reaction: {response.text}")
        return None

def delete_pr_review_comment_reaction(owner, repo, comment_id, reaction_id):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions/{reaction_id}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        return True
    else:
        logger.error(f"Failed to delete PR review comment reaction: {response.text}")
        return False


def create_pull_request_for_issue(owner, repo_name, issue):
    logger.info(f"Processing issue #{issue['number']} for {owner}/{repo_name}")

    # Create a temporary directory within the current working directory
    temp_dir = tempfile.mkdtemp(dir=os.getcwd(), prefix='repo_')
    logger.info(f"Created temporary directory: {temp_dir}")

    try:
        eyes_reaction_id = create_issue_reaction(owner, repo_name, issue['number'], "eyes")

        repo_dir = clone_repository(temp_dir, owner, repo_name)
        logger.info(f"Repository extracted to {repo_dir}")

        branch_name = f"fix-issue-{issue['number']}"
        checkout_new_branch(repo_dir, branch_name)

        files_list = extract_files_list_from_issue(issue['body'])
        logger.info(f"Extracted files list from issue: {files_list}")

        # Prepare the prompt
        prompt = f"Please help me resolve this issue.\n\nIssue Title: {issue['title']}\n\nIssue Body: {issue['body']}"
        logger.info("Prepared prompt for coding request")

        logger.info("Starting coding request")
        coding_result = do_coding_request(prompt, files_list, repo_dir)
        logger.info("Coding request completed")

        main_branch = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}").json()['default_branch']

        push_changes_to_repository(temp_dir, branch_name)

        logger.info("Creating pull request")
        pr = create_pull_request(
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
        comment = create_issue_comment(owner, repo_name, issue['number'], comment_body)
        delete_issue_reaction(owner, repo_name, issue['number'], eyes_reaction_id)
        create_issue_reaction(owner, repo_name, issue['number'], "rocket")

        if comment:
            logger.info("Comment added successfully")
            return {"message": f"Pull request created and issue commented: {pr['html_url']}"}, 200
        else:
            logger.warning("Failed to add comment to the issue")
            return {"message": f"Pull request created, but failed to comment on issue: {pr['html_url']}"}, 200

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return {"error": "An internal error occurred"}, 500

    finally:
        # Clean up the temporary directory
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up temporary directory: {temp_dir}")

def handle_pr_review_comment(owner, repo_name, pull_request, comment):
    logger.info(f"Processing PR review comment for PR #{pull_request['number']} in {owner}/{repo_name}")

    # Check if the comment is from the app user
    if comment['user']['login'] == APP_USER_NAME:
        logger.info(f"Ignoring comment from {APP_USER_NAME}")
        return {"message": "Comment from app user ignored"}, 200

    pr_review_comment_id = comment['id']
    eyes_reaction_id = create_pr_review_comment_reaction(owner, repo_name, pr_review_comment_id, "eyes")

    if 'LGTM' in comment['body']:
        logger.info("Comment contains 'LGTM', no action needed")
        return {"message": "Comment acknowledged, no action needed"}, 200

    try:
        # Get the original issue
        issue_number = extract_issue_number_from_pr_title(pull_request['title'])
        logger.info(f"Extracted issue number: {issue_number}")
        if not issue_number:
            logger.error("Failed to extract issue number from PR title")
            return {"error": "Failed to extract issue number from PR title"}, 500

        issue = get_issue(owner, repo_name, issue_number)
        logger.info(f"Retrieved issue: {issue['number'] if issue else None}")
        if not issue:
            logger.error(f"Failed to get issue #{issue_number}")
            return {"error": f"Failed to get issue #{issue_number}"}, 500

        # Get the PR diff
        pr_diff = get_pr_diff(owner, repo_name, pull_request['number'])
        logger.info(f"Retrieved PR diff: {'Success' if pr_diff else 'Failed'}")
        if not pr_diff:
            logger.error("Failed to get PR diff")
            return {"error": "Failed to get PR diff"}, 500

        # Build the prompt
        prompt = build_pr_review_prompt(issue, pr_diff, comment['body'])
        logger.info("Built prompt for coding request")

        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(dir=os.getcwd(), prefix='repo_')
        logger.info(f"Created temporary directory: {temp_dir}")

        repo_dir = clone_repository(temp_dir, owner, repo_name, pull_request['head']['ref'])
        if not repo_dir:
            logger.error("Failed to clone repository")
            return {"error": "Failed to clone repository"}, 500

        # Get the list of files changed in the PR
        changed_pr_files = get_pr_changed_files(owner, repo_name, pull_request['number'])
        logger.info(f"Files changed in PR: {changed_pr_files}")

        mentioned_files = extract_files_list_from_issue(comment['body'])
        logger.info(f"Files mentioned in comment: {mentioned_files}")

        files_list = list(set(changed_pr_files + mentioned_files))
        logger.info(f"Combined files list: {files_list}")

        # Do the coding request
        logger.info("Starting coding request")
        coding_result = do_coding_request(prompt, files_list, repo_dir)
        logger.info("Completed coding request")

        push_changes_to_repository(temp_dir, pull_request['head']['ref'])

        pr_comment_body = f"I've updated the PR based on the review comment.\n\n{coding_result['summary']}"

        pr_comment = reply_to_pr_review_comment(owner, repo_name, pull_request['number'], pr_review_comment_id, pr_comment_body)
        if not pr_comment:
            logger.warning("Failed to add comment to the PR")
        else:
            logger.info("Added comment to PR successfully")

        delete_pr_review_comment_reaction(owner, repo_name, pr_review_comment_id, eyes_reaction_id)
        create_pr_review_comment_reaction(owner, repo_name, pr_review_comment_id, "rocket")

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

def get_issue(owner, repo, issue_number):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"Failed to get issue: {response.text}")
        return None

def get_pr_diff(owner, repo, pr_number):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.text
    else:
        logger.error(f"Failed to get PR diff: {response.text}")
        return None

def build_pr_review_prompt(issue, pr_diff, review_comment):
    return f"""
Please help me address the following review comment on a pull request:

Original Issue:
Title: {issue['title']}
Body: {issue['body']}

Here is the original diff for the pull request:
{pr_diff}

Here is the review comment:
{review_comment}

Please make changes to address this review comment.
"""

def get_pr_changed_files(owner, repo, pr_number):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return [file['filename'] for file in response.json()]
    else:
        logger.error(f"Failed to get PR changed files: {response.text}")
        return []

def create_pr_comment(owner, repo, pr_number, body):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "body": body
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to create PR comment: {response.text}")
        return None

def reply_to_pr_review_comment(owner, repo, pr_number, pr_review_comment_id, body):
    token = get_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"

    headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
    }

    data = {
        "body": body,
        "in_reply_to": pr_review_comment_id
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    else:
        logger.error(f"Failed to reply to PR review comment: {response.text}")
        return None

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
    logger.info("Verifying webhook signature")
    if not signature_header:
        logger.warning("No signature header provided")
        return False
    hash_object = hmac.new(GITHUB_WEBHOOK_SECRET.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    result = hmac.compare_digest(expected_signature, signature_header)
    logger.info(f"Signature verification result: {result}")
    return result

def do_coding_request(prompt, files_list, root_folder_path):
    logger.info("Starting coding request")
    logger.info(f"Files List: {files_list}")
    
    model = Model("claude-3-5-sonnet-20240620")
    full_file_paths = [os.path.join(root_folder_path, file) for file in files_list]
    io = InputOutput(yes=True)
    git_repo = GitRepo(io, full_file_paths, root_folder_path, models=model.commit_message_models())
    coder = Coder.create(main_model=model, fnames=full_file_paths, io=io, repo=git_repo, stream=False)

    logger.info("Running coder with prompt")
    try:
        summary =coder.run(prompt)
        logger.info("Coding request completed")

        # summary_prompt = "/ask Thank you. Please provide a summary of the changes you just made."
        # summary = coder.run(summary_prompt)
        # logger.info("Summary generated successfully")
    except Exception as e:
        logger.error(f"Error during coding request: {str(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise  # Re-raise the exception to be caught by the outer try-except block

    # Get the list of changed files in the last commit
    changed_files = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD~1'], cwd=root_folder_path).decode('utf-8').splitlines()
    if not changed_files:
        # If no changes detected, get all files tracked by git
        changed_files = subprocess.check_output(['git', 'ls-files'], cwd=root_folder_path).decode('utf-8').splitlines()
    logger.info(f"Changed files: {changed_files}")

    # Get the last commit message
    commit_message = subprocess.check_output(['git', 'log', '-1',
 '--pretty=%B'], cwd=root_folder_path).decode('utf-8').strip()
    if not commit_message:
        commit_message = "Update files based on the latest request"
    logger.info(f"Commit message: {commit_message}")

    # Make a commit if there are changes
    # if changed_files:
    #     subprocess.run(['git', 'add', '-A'], cwd=root_folder_path, check=True)
    #     subprocess.run(['git', 'commit', '-m', commit_message], cwd=root_folder_path, check=True)
    #     logger.info("Changes committed")

    return {
        'changed_files': changed_files,
        'commit_message': commit_message,
        'summary': summary
    }


@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "Hello, World!"})

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        signature = request.headers.get('X-Hub-Signature-256')
        payload = request.data

        logger.info(f"Received webhook with signature: {signature}")
        logger.info(f"Payload: {payload.decode('utf-8')}")

        if not verify_webhook_signature(payload, signature):
            logger.warning("Webhook signature verification failed")
            return jsonify({"error": "Request signatures didn't match!"}), 403

        logger.info("Webhook signature verified successfully")

        event = request.headers.get('X-GitHub-Event')
        data = request.json

        logger.info(f"GitHub event: {event}")
        logger.info(f"Action: {data.get('action')}")

        if event == 'issues' and data['action'] == 'opened':
            issue = data['issue']
            repo = data['repository']
            owner = repo['owner']['login']
            repo_name = repo['name']

            result, status_code = create_pull_request_for_issue(owner, repo_name, issue)
            return jsonify(result), status_code
        elif event == 'pull_request_review_comment' and data['action'] == 'created':
            comment = data['comment']
            pull_request = data['pull_request']
            repo = data['repository']
            owner = repo['owner']['login']
            repo_name = repo['name']

            result, status_code = handle_pr_review_comment(owner, repo_name, pull_request, comment)
            return jsonify(result), status_code
        else:
            logger.info("Event is not handled, ignoring")
            return jsonify({"message": "Received"}), 200
    except Exception as e:
        logger.error(f"An error occurred in webhook handler: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({"error": f"An internal error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)

