from aider.repo import GitRepo
import os
import subprocess
from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput
import logging
from anthropic import Anthropic

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

def do_coding_request(prompt, files_list, root_folder_path, conventions_file=None):
    logger.info("Starting coding request")
    logger.info(f"Files List: {files_list}")
    
    model = Model("claude-3-5-sonnet-20240620")
    full_file_paths = []
    for file in files_list:
        if isinstance(file, tuple):
            full_file_paths.append(os.path.join(root_folder_path, file[0]))
        else:
            full_file_paths.append(os.path.join(root_folder_path, file))
    io = InputOutput(yes=True)
    git_repo = GitRepo(io, full_file_paths, root_folder_path, models=model.commit_message_models())
    
    read_only_fnames = []
    if conventions_file:
        read_only_fnames.append(conventions_file)
        logger.info(f"Added conventions file to read-only files: {conventions_file}")
    
    coder = Coder.create(main_model=model, fnames=full_file_paths, io=io, repo=git_repo, stream=False, suggest_shell_commands=False, read_only_fnames=read_only_fnames)

    logger.info("Running coder with prompt")
    coder.run(prompt)

    logger.info("Coding request completed")

    # Get the last commit message
    commit_message = subprocess.check_output(['git', 'log', '-1', '--pretty=%B'], cwd=root_folder_path).decode('utf-8').strip()
    if not commit_message:
        commit_message = "Update files based on the latest request"
    logger.info(f"Commit message: {commit_message}")

    return {
        'commit_message': commit_message
    }

def generate_summary(issue_title, issue_body, git_diff, aider_summary):
    logger.info("Generating summary using Anthropic API")
    
    anthropic = Anthropic()
    prompt = f"""
    Please generate a descriptive summary for a pull request based on the following information:

    Issue Title: {issue_title}
    Issue Body: {issue_body}

    Git Diff:
    {git_diff}

    Aider's Summary:
    {aider_summary}

    Your task is to create a concise yet informative summary that captures the essence of the changes made and their purpose. This summary will be added to the pull request description.
    """

    response = anthropic.completions.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens_to_sample=500,
        prompt=prompt
    )

    summary = response.completion.strip()
    logger.info("Summary generation completed")
    return summary


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
