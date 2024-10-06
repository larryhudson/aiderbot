from dotenv import load_dotenv
load_dotenv()

import os
import logging
import tempfile
import shutil
import subprocess
import re
import git
import time
from pathlib import Path

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
from . import github_api, git_commands, aider_coder

REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)

APP_USER_NAME = os.getenv('GITHUB_APP_USER_NAME', 'larryhudson-aider-github[bot]')

def _is_aiderbot_mentioned(text):
    return "@aiderbot" in text.lower()

def _create_pull_request_for_issue(token, owner, repo_name, issue, comments=None, start_time=None):
    logger.info(f"Processing issue #{issue['number']} for {owner}/{repo_name}")

    if not comments:
        if not _is_aiderbot_mentioned(issue['title']) and not _is_aiderbot_mentioned(issue['body']):
            logger.info(f"Ignoring issue #{issue['number']} as @aiderbot was not mentioned")
            return {"message": "Issue ignored as @aiderbot was not mentioned"}, 200

        author_association = issue['author_association']
        if author_association not in ['OWNER', 'MEMBER', 'COLLABORATOR']:
            logger.info(f"Ignoring issue from user without sufficient permissions: {issue['user']['login']} (association: {author_association})")
            return {"message": "Issue from user without sufficient permissions ignored"}, 200

    # Create a temporary directory within the current working directory
    temp_dir = tempfile.mkdtemp(dir=os.getcwd(), prefix='repo_')
    logger.info(f"Created temporary directory: {temp_dir}")

    try:
        eyes_reaction_id = github_api.create_issue_reaction(
            token=token,
            owner=owner,
            repo=repo_name,
            issue_number=issue['number'],
            reaction="eyes"
        )

        repo_dir, initial_commit_hash = git_commands.clone_repository(
            token=token,
            temp_dir=temp_dir,
            owner=owner,
            repo=repo_name
        )

        files_list = _extract_files_list_from_issue(issue['body'])

        # Check for conventions file
        conventions_file_path = os.getenv('CONVENTIONS_FILE_PATH')
        conventions_file = None
        if conventions_file_path:
            full_conventions_path = Path(repo_dir) / conventions_file_path
            if full_conventions_path.exists():
                conventions_file = str(full_conventions_path)
                logger.info(f"Found conventions file: {conventions_file}")

        # Prepare the prompt
        issue_pr_prompt = f"Please help me resolve this issue.\n\nIssue Title: {issue['title']}\n\nIssue Body: {issue['body']}"
        
        if comments:
            issue_pr_prompt += "\n\nComments:\n"
            for comment in comments:
                issue_pr_prompt += f"\n- {comment['body']}"

        coding_result = aider_coder.do_coding_request(
            prompt=issue_pr_prompt,
            files_list=files_list,
            root_folder_path=repo_dir,
            conventions_file=conventions_file
        )

        # Check if any changes were made
        current_commit_hash = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo_dir, capture_output=True, text=True, check=True).stdout.strip()

        if current_commit_hash == initial_commit_hash:
            logger.info("No changes were made by Aider")
            comment_body = f"I've analyzed the issue, but no changes were necessary. Here's a summary of my findings:\n\n{coding_result['summary']}"
            github_api.create_issue_comment(
                token=token,
                owner=owner,
                repo=repo_name,
                issue_number=issue['number'],
                body=comment_body
            )
            github_api.delete_issue_reaction(
                token=token,
                owner=owner,
                repo=repo_name,
                issue_number=issue['number'],
                reaction_id=eyes_reaction_id
            )
            return {"message": "No changes made, comment added to issue"}, 200

        # Changes were made, proceed with creating a PR
        branch_name = f"fix-issue-{issue['number']}"
        git_commands.checkout_new_branch(
            repo_dir=repo_dir,
            branch_name=branch_name
        )

        main_branch = github_api.get_default_branch(
            token=token,
            owner=owner,
            repo=repo_name
        )

        git_commands.push_changes_to_repository(
            temp_dir=temp_dir,
            branch=branch_name
        )

        created_pull_request = github_api.create_pull_request(
            token=token,
            owner=owner,
            repo=repo_name,
            title=f"Fix issue #{issue['number']}: {coding_result['commit_message']}",
            body=f"This PR addresses the changes requested in issue #{issue['number']}\n\n{coding_result['summary']}",
            head=branch_name,
            base=main_branch
        )

        if not created_pull_request:
            logger.error("Failed to create pull request")
            return {"error": "Failed to create pull request"}, 500

        logger.info(f"Pull request created: {created_pull_request['html_url']}")

        end_time = time.time()
        elapsed_time = end_time - start_time if start_time else None
        time_info = f"\n\nTime taken to create this PR: {elapsed_time:.2f} seconds" if elapsed_time else ""
        
        comment_body = f"I've created a pull request to address this issue: {created_pull_request['html_url']}{time_info}"
        logger.info("Adding comment to the issue")
        github_api.create_issue_comment(
            token=token,
            owner=owner,
            repo=repo_name,
            issue_number=issue['number'],
            body=comment_body
        )
        github_api.delete_issue_reaction(
            token=token,
            owner=owner,
            repo=repo_name,
            issue_number=issue['number'],
            reaction_id=eyes_reaction_id
        )
        github_api.create_issue_reaction(
            token=token,
            owner=owner,
            repo=repo_name,
            issue_number=issue['number'],
            reaction="rocket"
        )

        return {"message": f"Pull request created and issue commented: {created_pull_request['html_url']}", "elapsed_time": elapsed_time}, 200

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Full traceback:\n{error_traceback}")
        
        # Post a comment about the error
        error_comment = f"An error occurred while processing this issue:\n\n```\n{str(e)}\n\n{error_traceback}\n```"
        github_api.create_issue_comment(
            token=token,
            owner=owner,
            repo=repo_name,
            issue_number=issue['number'],
            body=error_comment
        )
        
        return {"error": "An internal error occurred"}, 500

    finally:
        # Clean up the temporary directory
        shutil.rmtree(temp_dir)
        logger.info(f"Cleaned up temporary directory: {temp_dir}")

def _handle_pr_review_comment(token, owner, repo_name, pull_request, pr_review_comment):
    logger.info(f"Processing PR review comment for PR #{pull_request['number']} in {owner}/{repo_name}")
    start_time = time.time()

    if not _is_aiderbot_mentioned(pr_review_comment['body']):
        not_mentioned_message = "PR review comment ignored as @aiderbot was not mentioned"
        logger.info(not_mentioned_message)
        return {"message": not_mentioned_message}, 200

    # Check if the comment is from the app user
    if pr_review_comment['user']['login'] == APP_USER_NAME:
        app_user_message = f"Comment from {APP_USER_NAME} ignored"
        logger.info(app_user_message)
        return {"message": app_user_message}, 200

    # Check if the user has sufficient permissions
    author_association = pr_review_comment['author_association']
    if author_association not in ['OWNER', 'MEMBER', 'COLLABORATOR']:
        not_associated_message = f"Comment from user without sufficient permissions ignored: {pr_review_comment['user']['login']} (association: {author_association})"
        logger.info(not_associated_message)
        return {"message": not_associated_message}, 200

    eyes_reaction_id = github_api.create_pr_review_comment_reaction(
        token=token,
        owner=owner,
        repo=repo_name,
        pr_review_comment_id=pr_review_comment['id'],
        reaction="eyes"
    )

    if 'LGTM' in pr_review_comment['body']:
        logger.info("Comment contains 'LGTM', no action needed")
        return {"message": "Comment acknowledged, no action needed"}, 200

    try:
        # Get the original issue
        issue_number = _extract_issue_number_from_pr_title(pull_request['title'])
        logger.info(f"Extracted issue number: {issue_number}")

        issue = github_api.get_issue(
            token=token,
            owner=owner,
            repo=repo_name,
            issue_number=issue_number
        )

        # Get the PR diff
        pr_diff = github_api.get_pr_diff(
            token=token,
            owner=owner,
            repo=repo_name,
            pr_number=pull_request['number']
        )

        # Build the prompt
        prompt = aider_coder.build_pr_review_prompt(
            issue=issue,
            pr_diff=pr_diff,
            review_comment=pr_review_comment['body']
        )

        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(dir=os.getcwd(), prefix='repo_')
        repo_dir, initial_commit_hash = git_commands.clone_repository(
            token=token,
            temp_dir=temp_dir,
            owner=owner,
            repo=repo_name,
            branch=pull_request['head']['ref']
        )

        # Get the list of files changed in the PR
        changed_pr_files = github_api.get_pr_changed_files(
            token=token,
            owner=owner,
            repo=repo_name,
            pr_number=pull_request['number']
        )

        files_mentioned_in_pr_review_comment = _extract_files_list_from_issue(pr_review_comment['body'])

        files_list = list(set(changed_pr_files + files_mentioned_in_pr_review_comment))

        coding_result = aider_coder.do_coding_request(
            prompt=prompt,
            files_list=files_list,
            root_folder_path=repo_dir
        )

        # Check if any changes were made
        current_commit_hash = git_commands.get_current_commit_hash(
            repo_dir_path=repo_dir
        )

        if current_commit_hash == initial_commit_hash:
            logger.info("No changes were made by Aider")
            comment_body = f"I've analyzed the issue, but no changes were necessary. Here's a summary of my findings:\n\n{coding_result['summary']}"
            github_api.reply_to_pr_review_comment(
                token=token,
                owner=owner,
                repo=repo_name,
                pr_number=pull_request['number'],
                pr_review_comment_id=pr_review_comment['id'],
                body=comment_body
            )
            github_api.delete_pr_review_comment_reaction(
                token=token,
                owner=owner,
                repo=repo_name,
                pr_review_comment_id=pr_review_comment['id'],
                reaction_id=eyes_reaction_id
            )
            return {"message": "No changes made, comment added to PR review comment"}, 200

        git_commands.push_changes_to_repository(
            temp_dir=temp_dir,
            branch=pull_request['head']['ref']
        )


        end_time = time.time()
        elapsed_time = end_time - start_time
        time_info = f"Time taken to process this PR review comment: {elapsed_time:.2f} seconds"

        pr_comment_body = f"I've updated the PR based on the review comment.\n\n{coding_result['summary']}\n\n{time_info}"

        github_api.reply_to_pr_review_comment(
            token=token,
            owner=owner,
            repo=repo_name,
            pr_number=pull_request['number'],
            pr_review_comment_id=pr_review_comment['id'],
            body=pr_comment_body
        )

        github_api.delete_pr_review_comment_reaction(
            token=token,
            owner=owner,
            repo=repo_name,
            pr_review_comment_id=pr_review_comment['id'],
            reaction_id=eyes_reaction_id
        )

        github_api.create_pr_review_comment_reaction(
            token=token,
            owner=owner,
            repo=repo_name,
            pr_review_comment_id=pr_review_comment['id'],
            reaction="rocket")

        return {"message": "PR updated based on review comment", "commit_message": coding_result['commit_message'], "elapsed_time": elapsed_time}, 200

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Full traceback:\n{error_traceback}")
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        time_info = f"Time taken before error occurred: {elapsed_time:.2f} seconds"
        
        # Reply to the PR review comment about the error
        error_comment = f"An error occurred while processing this PR review comment:\n\n```\n{str(e)}\n\n{error_traceback}\n```\n\n{time_info}"

        github_api.reply_to_pr_review_comment(
            token=token,
            owner=owner,
            repo=repo_name,
            pr_number=pull_request['number'],
            pr_review_comment_id=pr_review_comment['id'],
            body=error_comment
        )
        
        return {"error": f"An internal error occurred: {str(e)}", "elapsed_time": elapsed_time}, 500

    finally:
        # Clean up the temporary directory
        if temp_dir:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")

def _handle_issue_comment(token, owner, repo_name, issue, comment):
    """ Handle an issue comment event

    This function 
    """
    logger.info(f"Processing issue comment for issue #{issue['number']} in {owner}/{repo_name}")

    if not _is_aiderbot_mentioned(comment['body']):
        not_mentioned_message = "Issue comment ignored as @aiderbot was not mentioned"
        logger.info(not_mentioned_message)
        return {"message": not_mentioned_message}, 204

    # Check if the comment is from the app user
    if comment['user']['login'] == APP_USER_NAME:
        app_user_message = f"Comment from {APP_USER_NAME} ignored"
        logger.info(app_user_message)
        return {"message": app_user_message}, 204

    # Check if the user has sufficient permissions
    author_association = comment['author_association']
    if author_association not in ['OWNER', 'MEMBER', 'COLLABORATOR']:
        not_associated_message = f"Ignoring comment from user without sufficient permissions: {comment['user']['login']} (association: {author_association})"
        logger.info(not_associated_message)
        return {"message": not_associated_message}, 204

    # Check if there's already a pull request for this issue
    existing_prs = github_api.get_pull_requests_for_issue(
        token=token,
        owner=owner,
        repo=repo_name,
        issue_number=issue['number']
    )
    if existing_prs:
        logger.info(f"Pull request already exists for issue #{issue['number']}")
        return {"message": "Pull request already exists for this issue"}, 200

    # If no existing PR, proceed with creating one
    return _create_pull_request_for_issue(
        token=token,
        owner=owner,
        repo_name=repo_name,
        issue=issue,
        comments=[comment]
    )

def _extract_issue_number_from_pr_title(title):
    """ Extract the issue number from the PR title """
    match = re.search(r'#(\d+)', title)
    return int(match.group(1)) if match else None

def _extract_files_list_from_issue(issue_body):
    """ Extract the list of files mentioned in the issue body

    Looks for a section in the issue body that starts with 'Files:' and
    then looks for bullets that indicate file paths.
    """
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

@app.task
def task_create_pull_request_for_issue(payload):
    return _create_pull_request_for_issue(
        token=github_api.get_github_token_for_installation(payload['installation']['id']),
        owner=payload['repository']['owner']['login'],
        repo_name=payload['repository']['name'],
        issue=payload['issue'],
        start_time=time.time()
    )

@app.task
def task_handle_pr_review_comment(payload):
    return _handle_pr_review_comment(
        token=github_api.get_github_token_for_installation(payload['installation']['id']),
        owner=payload['repository']['owner']['login'],
        repo_name=payload['repository']['name'],
        pull_request=payload['pull_request'],
        pr_review_comment=payload['comment']
    )

@app.task
def task_handle_issue_comment(payload):
    return _handle_issue_comment(
        token=github_api.get_github_token_for_installation(payload['installation']['id']),
        owner=payload['repository']['owner']['login'],
        repo_name=payload['repository']['name'],
        issue=payload['issue'],
        comment=payload['comment']
    )
