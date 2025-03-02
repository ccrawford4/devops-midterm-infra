#!/usr/bin/env python3
import os
import sys
import subprocess
import boto3
import tempfile
import paramiko

def main():
    # Alternative: Use environment variables instead of command line arguments
    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.environ.get('AWS_SESSION_TOKEN')
    aws_region = os.environ.get('AWS_DEFAULT_REGION')
    ecr_repository_uri = os.environ.get('ECR_REPOSITORY_URI')
    private_key = os.environ.get('EC2_SSH_KEY')
    host = os.environ.get('EC2_HOST')
    user_name = os.environ.get('EC2_USER')
    db_user = os.environ.get('DB_USER')
    db_password = os.environ.get('DB_PASSWORD')
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT')
    db_name = os.environ.get('DB_NAME')

    # Write private key to file
    with tempfile.NamedTemporaryFile(delete=False, mode='w') as key_file:
        key_file.write(private_key)
        key_file_path = key_file.name
    
    # Set proper permissions for the key file
    os.chmod(key_file_path, 0o600)

    try:
        # Initialize SSH client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Connect to remote host
        client.connect(hostname=host, username=user_name, key_filename=key_file_path)
        
        # Prepare remote commands
        commands = [
            f"aws configure set aws_access_key_id {aws_access_key_id}",
            f"aws configure set aws_secret_access_key {aws_secret_access_key}",
            f"aws configure set aws_session_token {aws_session_token}",
            f"aws configure set aws_default_region {aws_region}",
            f"aws ecr get-login-password --region {aws_region} | docker login -u AWS --password-stdin {ecr_repository_uri}",
            "docker rm -f $(docker ps -aq)",
            f"docker pull {ecr_repository_uri}:frontend-latest",
            f"docker run -p \"3000:80\" -d {ecr_repository_uri}:frontend-latest",
            f"docker pull {ecr_repository_uri}:backend-latest",
            f"echo DB_USER"
            f"cat .env",
            f"docker run -p \"8080:8080\" -e DB_USER={db_user} -e DB_PASSWORD={db_password} -e DB_HOST={db_host} -e DB_PORT={db_port} -e DB_NAME={db_name} {ecr_repository_uri}:backend-latest",
            "sudo systemctl is-active --quiet nginx || sudo systemctl start nginx",
        ]
        
        # Execute remote commands
        for command in commands:
            print(f"Executing: {command}")
            stdin, stdout, stderr = client.exec_command(command)
            print(stdout.read().decode())
            err = stderr.read().decode()
            if err:
                print(f"Error: {err}")
    
    finally:
        # Clean up the key file
        client.close()
        os.unlink(key_file_path)

if __name__ == "__main__":
    main()