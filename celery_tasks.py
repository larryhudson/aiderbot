from dotenv import load_dotenv
load_dotenv()

import os
import logging
import tempfile
import shutil
import subprocess
import re
import git
import requests
from bs4 import BeautifulSoup

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

# Explicitly set the Git executable path
git_executable = "/usr/bin/git"
git.refresh(git_executable)
logger.info(f"Git executable set to: {git_executable}")

from celery import Celery
import github_api
import git_commands
import aider_coder

# Celery configuration
# This will use the REDIS_URL from the environment variables
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

app = Celery('tasks', broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

# Log the REDIS_URL being used
logger.info(f"Using CELERY_BROKER_URL: {CELERY_BROKER_URL}")

# GitHub App configuration
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

    # Create a temporary directory within the current working directory
    temp_dir = tempfile.mkdtemp(dir=os.getcwd(), prefix='repo_')
    logger.info(f"Created temporary directory: {temp_dir}")

    try:
        eyes_reaction_id = github_api.create_issue_reaction(token, owner, repo_name, issue['number'], "eyes")

        repo_dir, initial_commit_hash = git_commands.clone_repository(token, temp_dir, owner, repo_name)

        files_list = extract_files_list_from_issue(issue['body'])

        # Check for URLs in the issue body
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', issue['body'])
        url_content = ""
        if urls:
            url_content = fetch_url_content(urls[0])

        # Prepare the prompt
        issue_pr_prompt = f"Please help me resolve this issue.\n\nIssue Title: {issue['title']}\n\nIssue Body: {issue['body']}"
        
        if url_content:
            issue_pr_prompt += f"\n\nContent from URL:\n{url_content}"
        
        if comments:
            issue_pr_prompt += "\n\nComments:\n"
            for comment in comments:
                issue_pr_prompt += f"\n- {comment['body']}"

        coding_result = aider_coder.do_coding_request(issue_pr_prompt, files_list, repo_dir)

        # Check if any changes were made
        current_commit_hash = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo_dir, capture_output=True, text=True, check=True).stdout.strip()

        if current_commit_hash == initial_commit_hash:
            logger.info("No changes were made by Aider")
            comment_body = f"I've analyzed the issue, but no changes were necessary. Here's a summary of my findings:\n\n{coding_result['summary']}"
            github_api.create_issue_comment(token, owner, repo_name, issue['number'], comment_body)
            github_api.delete_issue_reaction(token, owner, repo_name, issue['number'], eyes_reaction_id)
            return {"message": "No changes made, comment added to issue"}, 200

        # Changes were made, proceed with creating a PR
        branch_name = f"fix-issue-{issue['number']}"
        git_commands.checkout_new_branch(repo_dir, branch_name)

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
        error_traceback = traceback.format_exc()
        logger.error(f"Full traceback:\n{error_traceback}")
        
        # Post a comment about the error
        error_comment = f"An error occurred while processing this issue:\n\n```\n{str(e)}\n\n{error_traceback}\n```"
        github_api.create_issue_comment(token, owner, repo_name, issue['number'], error_comment)
        
        return {"error": "An internal error occurred"}, 500

    finally:
        # Clean up the temporary directory
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up temporary directory: {temp_dir}")

def handle_pr_review_comment(*, token, owner, repo_name, pull_request, comment):
    logger.info(f"Processing PR review comment for PR #{pull_request['number']} in {owner}/{repo_name}")

    if not is_aiderbot_mentioned(comment['body']):
        logger.info(f"Ignoring PR review comment as @aiderbot was not mentioned")
        return {"message": "PR review comment ignored as @aiderbot was not mentioned"}, 200

    # Check if the comment is from the app user
    if comment['user']['login'] == APP_USER_NAME:
        logger.info(f"Ignoring comment from {APP_USER_NAME}")
        return {"message": "Comment from app user ignored"}, 200

    # Check if the comment is from the allowed user (if set)
    if ALLOWED_USERNAME and comment['user']['login'] != ALLOWED_USERNAME:
        logger.info(f"Ignoring comment from non-allowed user: {comment['user']['login']}")
        return {"message": "Comment from non-allowed user ignored"}, 200

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
        repo_dir, initial_commit_hash = git_commands.clone_repository(token, temp_dir, owner, repo_name, pull_request['head']['ref'])

        # Get the list of files changed in the PR
        changed_pr_files = github_api.get_pr_changed_files(token, owner, repo_name, pull_request['number'])
        mentioned_files = extract_files_list_from_issue(comment['body'])

        files_list = list(set(changed_pr_files + mentioned_files))

        coding_result = aider_coder.do_coding_request(prompt, files_list, repo_dir)

        # Check if any changes were made
        current_commit_hash = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo_dir, capture_output=True, text=True, check=True).stdout.strip()

        if current_commit_hash == initial_commit_hash:
            logger.info("No changes were made by Aider")
            comment_body = f"I've analyzed the issue, but no changes were necessary. Here's a summary of my findings:\n\n{coding_result['summary']}"
            github_api.reply_to_pr_review_comment(token, owner, repo_name, pull_request['number'], pr_review_comment_id, comment_body)
            github_api.delete_pr_review_comment_reaction(token, owner, repo_name, pr_review_comment_id, eyes_reaction_id)
            return {"message": "No changes made, comment added to PR review comment"}, 200

        git_commands.push_changes_to_repository(temp_dir, pull_request['head']['ref'])

        pr_comment_body = f"I've updated the PR based on the review comment.\n\n{coding_result['summary']}"

        github_api.reply_to_pr_review_comment(token, owner, repo_name, pull_request['number'], pr_review_comment_id, pr_comment_body)

        github_api.delete_pr_review_comment_reaction(token, owner, repo_name, pr_review_comment_id, eyes_reaction_id)
        github_api.create_pr_review_comment_reaction(token, owner, repo_name, pr_review_comment_id, "rocket")

        return {"message": "PR updated based on review comment", "commit_message": coding_result['commit_message']}, 200

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Full traceback:\n{error_traceback}")
        
        # Reply to the PR review comment about the error
        error_comment = f"An error occurred while processing this PR review comment:\n\n```\n{str(e)}\n\n{error_traceback}\n```"
        github_api.reply_to_pr_review_comment(token, owner, repo_name, pull_request['number'], comment['id'], error_comment)
        
        return {"error": f"An internal error occurred: {str(e)}"}, 500

    finally:
        # Clean up the temporary directory
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up temporary directory: {temp_dir}")

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

def fetch_url_content(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract text content from the page
        text_content = soup.get_text(separator='\n', strip=True)
        
        # Limit the content to a reasonable length (e.g., first 1000 characters)
        return text_content[:1000]
    except Exception as e:
        logger.error(f"Error fetching URL content: {str(e)}")
        return f"Error fetching URL content: {str(e)}"

@app.task
def task_create_pull_request_for_issue(token, owner, repo_name, issue, comments=None):
    logger.info(f"Starting task_create_pull_request_for_issue for issue #{issue['number']} in {owner}/{repo_name}")
    try:
        result = create_pull_request_for_issue(token=token, owner=owner, repo_name=repo_name, issue=issue, comments=comments)
        logger.info(f"Completed task_create_pull_request_for_issue for issue #{issue['number']} with result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in task_create_pull_request_for_issue for issue #{issue['number']}: {str(e)}")
        raise

@app.task
def task_handle_pr_review_comment(token, owner, repo_name, pull_request, comment):
    logger.info(f"Starting task_handle_pr_review_comment for PR #{pull_request['number']} in {owner}/{repo_name}")
    try:
        result = handle_pr_review_comment(token=token, owner=owner, repo_name=repo_name, pull_request=pull_request, comment=comment)
        logger.info(f"Completed task_handle_pr_review_comment for PR #{pull_request['number']} with result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in task_handle_pr_review_comment for PR #{pull_request['number']}: {str(e)}")
        raise

@app.task
def task_handle_issue_comment(token, owner, repo_name, issue, comment):
    logger.info(f"Starting task_handle_issue_comment for issue #{issue['number']} in {owner}/{repo_name}")
    try:
        result = handle_issue_comment(token=token, owner=owner, repo_name=repo_name, issue=issue, comment=comment)
        logger.info(f"Completed task_handle_issue_comment for issue #{issue['number']} with result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in task_handle_issue_comment for issue #{issue['number']}: {str(e)}")
        raise
