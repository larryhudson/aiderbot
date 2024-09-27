import pytest
from unittest.mock import patch, MagicMock
from main import app, verify_webhook_signature
from celery_tasks import create_pull_request_for_issue, handle_pr_review_comment, handle_issue_comment

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_route(client):
    """Test that the index route returns the expected message"""
    response = client.get('/')
    assert response.status_code == 200
    assert response.json == {"message": "Hello, World!"}

def test_verify_webhook_signature():
    """Test the webhook signature verification function"""
    payload = b'test_payload'
    valid_signature = 'sha256=a85a8719f9f3bce398b0a4e77f7a4f2b8679da4a7c70168d1c3c807b0807a823'
    invalid_signature = 'sha256=invalid'

    with patch('main.GITHUB_WEBHOOK_SECRET', b'test_secret'):
        assert verify_webhook_signature(payload, valid_signature) == True
        assert verify_webhook_signature(payload, invalid_signature) == False

@patch('github_api.get_github_token_for_installation')
@patch('celery_tasks.task_create_pull_request_for_issue.delay')
def test_webhook_issue_opened(mock_task, mock_get_token, client):
    """Test the webhook endpoint for issue opened event"""
    mock_get_token.return_value = 'test_token'
    
    data = {
        'action': 'opened',
        'installation': {'id': 123},
        'repository': {'owner': {'login': 'test_owner'}, 'name': 'test_repo'},
        'issue': {'number': 1, 'title': 'Test Issue', 'body': '@aiderbot test'}
    }
    
    response = client.post('/webhook', json=data, headers={'X-GitHub-Event': 'issues', 'X-Hub-Signature-256': 'sha256=valid'})
    
    assert response.status_code == 202
    mock_task.assert_called_once()

@patch('github_api.get_github_token_for_installation')
@patch('github_api.create_issue_reaction')
@patch('git_commands.clone_repository')
@patch('aider_coder.do_coding_request')
@patch('github_api.create_pull_request')
@patch('github_api.create_issue_comment')
def test_create_pull_request_for_issue(mock_comment, mock_create_pr, mock_coding, mock_clone, mock_reaction, mock_get_token):
    """Test the create_pull_request_for_issue function"""
    mock_get_token.return_value = 'test_token'
    mock_clone.return_value = ('/tmp/repo', 'initial_hash')
    mock_coding.return_value = {'summary': 'Test summary', 'commit_message': 'Test commit'}
    mock_create_pr.return_value = {'html_url': 'https://github.com/test/pr/1'}

    result, status_code = create_pull_request_for_issue(
        token='test_token',
        owner='test_owner',
        repo_name='test_repo',
        issue={'number': 1, 'title': 'Test Issue', 'body': '@aiderbot test'}
    )

    assert status_code == 200
    assert 'Pull request created' in result['message']
    mock_create_pr.assert_called_once()
    mock_comment.assert_called_once()

# Add more tests for handle_pr_review_comment and handle_issue_comment functions
