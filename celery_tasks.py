from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

# Celery configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
app = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)

# Import the functions we need
from main import create_pull_request_for_issue, handle_pr_review_comment, handle_issue_comment

@app.task
def task_create_pull_request_for_issue(token, owner, repo_name, issue, comments=None):
    return create_pull_request_for_issue(token=token, owner=owner, repo_name=repo_name, issue=issue, comments=comments)

@app.task
def task_handle_pr_review_comment(token, owner, repo_name, pull_request, comment):
    return handle_pr_review_comment(token=token, owner=owner, repo_name=repo_name, pull_request=pull_request, comment=comment)

@app.task
def task_handle_issue_comment(token, owner, repo_name, issue, comment):
    return handle_issue_comment(token=token, owner=owner, repo_name=repo_name, issue=issue, comment=comment)
