"""
EC2 Deployment and Testing Script for GitHub Actions

This script:
1. Launches an EC2 instance using a launch template
2. Waits for the instance to be ready
3. Copies files to the instance
4. Runs Docker Compose
5. Performs health checks
6. Runs tests
"""

import os
import sys
import time
import json
import boto3
import paramiko
import requests
import tempfile
from pathlib import Path

# Get environment variables
LAUNCH_TEMPLATE_ID = os.environ.get('LAUNCH_TEMPLATE_ID')
LAUNCH_TEMPLATE_NAME = os.environ.get('LAUNCH_TEMPLATE_NAME')
AWS_REGION = os.environ.get('AWS_REGION')
EC2_SSH_KEY = os.environ.get('EC2_SSH_KEY')
EC2_USER = os.environ.get('EC2_USER')
HEALTH_CHECK_URL = os.environ.get('HEALTH_CHECK_URL')

# Constants
SSH_TIMEOUT = 300  # 5 minutes
HEALTH_CHECK_TIMEOUT = 300  # 5 minutes
HEALTH_CHECK_INTERVAL = 10  # 10 seconds

def write_github_output(name, value):
    """Write output variables for GitHub Actions."""
    with open(os.environ.get('GITHUB_OUTPUT', '/dev/null'), 'a') as f:
        f.write(f"{name}={value}\n")

def create_ssh_key_file():
    """Create a temporary SSH key file from the environment variable."""
    if not EC2_SSH_KEY:
        raise ValueError("EC2_SSH_KEY environment variable is not set")
    
    key_file = tempfile.NamedTemporaryFile(delete=False, mode='w')
    key_file.write(EC2_SSH_KEY)
    key_file.close()
    
    # Set correct permissions
    os.chmod(key_file.name, 0o600)
    
    return key_file.name

def launch_ec2_instance():
    """Launch an EC2 instance using the launch template."""
    print("Launching EC2 instance...")
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    print("AWS_REGION: ", AWS_REGION)
    print("EC2: ", ec2)
    print("LAUNCH TEMPLATE ID: ", LAUNCH_TEMPLATE_ID)
    print("LAUNCH TEMPLATE NAME: ", LAUNCH_TEMPLATE_NAME)
    
    # Launch the instance
    response = ec2.run_instances(
        LaunchTemplate={
            'LaunchTemplateId': LAUNCH_TEMPLATE_ID,
            'LaunchTemplateName': LAUNCH_TEMPLATE_NAME,
            'Version': '1'
        },
        MinCount=1,
        MaxCount=1
    )

    print("RESPONSE: ", response)
    
    instance_id = response['Instances'][0]['InstanceId']
    print(f"EC2 instance {instance_id} launched.")
    
    return instance_id

def wait_for_instance_running(instance_id):
    """Wait for the instance to be in the running state."""
    print("Waiting for instance to be in running state...")
    
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])

def get_instance_public_ip(instance_id):
    """Get the public IP of the instance."""
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    response = ec2.describe_instances(InstanceIds=[instance_id])
    public_ip = response['Reservations'][0]['Instances'][0]['PublicIpAddress']
    print(f"Instance public IP: {public_ip}")
    return public_ip

def wait_for_ssh_ready(public_ip, key_file, timeout=SSH_TIMEOUT):
    """Wait for SSH to be available on the instance."""
    print("Waiting for SSH to be available...")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            ssh.connect(
                hostname=public_ip,
                username=EC2_USER,
                key_filename=key_file,
                timeout=10
            )
            print("SSH is ready!")
            ssh.close()
            return True
        except Exception as e:
            print(f"SSH not available yet: {e}")
            time.sleep(10)
    
    raise TimeoutError(f"SSH not available after {timeout} seconds")

def copy_files_to_instance(public_ip, key_file):
    """Copy all files from the current directory to the EC2 instance."""
    print("Copying files to EC2 instance...")
    
    # Create SSH transport
    transport = paramiko.Transport((public_ip, 22))
    transport.connect(username=EC2_USER, pkey=paramiko.RSAKey.from_private_key_file(key_file))
    sftp = paramiko.SFTPClient.from_transport(transport)
    
    # Create remote deployment directory
    try:
        sftp.mkdir("deployment")
    except IOError:
        # Directory might already exist
        pass
    
    # Copy all files and directories recursively
    local_path = "."
    remote_path = "deployment"
    
    for root, dirs, files in os.walk(local_path):
        # Skip .git directory
        if '.git' in root:
            continue
            
        # Create directories
        for dir in dirs:
            if dir == '.git':
                continue
                
            local_dir_path = os.path.join(root, dir)
            remote_dir_path = os.path.join(remote_path, os.path.relpath(local_dir_path, local_path))
            try:
                sftp.mkdir(remote_dir_path)
                print(f"Created directory: {remote_dir_path}")
            except IOError:
                continue
        
        # Copy files
        for file in files:
            local_file_path = os.path.join(root, file)
            remote_file_path = os.path.join(remote_path, os.path.relpath(local_file_path, local_path))
            
            try:
                sftp.put(local_file_path, remote_file_path)
                print(f"Copied: {local_file_path} -> {remote_file_path}")
            except Exception as e:
                print(f"Error copying {local_file_path}: {e}")
    
    sftp.close()
    transport.close()
    print("File copying completed.")

def run_remote_command(public_ip, key_file, command, description=None):
    """Run a command on the remote instance."""
    if description:
        print(f"{description}...")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname=public_ip,
        username=EC2_USER,
        key_filename=key_file
    )
    
    stdin, stdout, stderr = ssh.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()
    
    # Print output
    stdout_content = stdout.read().decode('utf-8')
    stderr_content = stderr.read().decode('utf-8')
    
    if stdout_content:
        print(f"STDOUT:\n{stdout_content}")
    if stderr_content:
        print(f"STDERR:\n{stderr_content}")
    
    ssh.close()
    
    if exit_code != 0:
        print(f"Command failed with exit code {exit_code}")
        return False
    
    return True

def run_health_check(public_ip, key_file, health_url, timeout=HEALTH_CHECK_TIMEOUT):
    """Run health checks until they pass or timeout."""
    print(f"Running health checks on {health_url}...")
    
    health_check_command = f"""
    set -e
    TIMEOUT={timeout}
    INTERVAL={HEALTH_CHECK_INTERVAL}
    START_TIME=$(date +%s)
    END_TIME=$((START_TIME + TIMEOUT))
    
    while [ $(date +%s) -lt $END_TIME ]; do
        echo "Running health check..."
        HTTP_STATUS=$(curl -s -o /dev/null -w "%{{http_code}}" {health_url})
        
        if [ "$HTTP_STATUS" -eq 200 ]; then
            echo "Health check passed!"
            exit 0
        fi
        
        echo "Health check failed with status $HTTP_STATUS. Retrying in $INTERVAL seconds..."
        sleep $INTERVAL
    done
    
    echo "Health check timed out after {timeout} seconds"
    exit 1
    """
    
    return run_remote_command(public_ip, key_file, health_check_command, "Running health checks")

def run_docker_compose(public_ip, key_file):
    """Run Docker Compose on the remote instance."""
    docker_compose_command = """
    cd ~/deployment
    docker-compose up -d
    """
    
    return run_remote_command(public_ip, key_file, docker_compose_command, "Running Docker Compose")

def run_tests(public_ip, key_file):
    """Run tests on the remote instance."""
    test_command = """
    cd ~/deployment
    # Add your test commands here
    ./run_tests.sh
    """
    
    return run_remote_command(public_ip, key_file, test_command, "Running tests")

def terminate_instance(instance_id):
    """Terminate the EC2 instance."""
    print(f"Terminating EC2 instance {instance_id}...")
    
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    ec2.terminate_instances(InstanceIds=[instance_id])
    
    print("Instance termination initiated.")

def main():
    """Main function to orchestrate the deployment and testing."""
    instance_id = None
    key_file = None
    
    try:
        # Create SSH key file
        key_file = create_ssh_key_file()
        
        # Launch EC2 instance
        instance_id = launch_ec2_instance()
        write_github_output("instance_id", instance_id)
        
        # Wait for instance to be running
        wait_for_instance_running(instance_id)
        
        # Get public IP
        public_ip = get_instance_public_ip(instance_id)
        write_github_output("public_ip", public_ip)
        
        # Wait for SSH to be available
        wait_for_ssh_ready(public_ip, key_file)
        
        # Copy files to instance
        copy_files_to_instance(public_ip, key_file)
        
        # Run Docker Compose
        if not run_docker_compose(public_ip, key_file):
            raise Exception("Docker Compose failed")
        
        # Run health checks
        if not run_health_check(public_ip, key_file, HEALTH_CHECK_URL):
            raise Exception("Health checks failed")
        
        # Run tests
        if not run_tests(public_ip, key_file):
            raise Exception("Tests failed")
        
        print("Deployment and tests completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    finally:
        # Clean up
        if key_file and os.path.exists(key_file):
            os.unlink(key_file)
        terminate_instance(instance_id)

if __name__ == "__main__":
    main()