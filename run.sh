#!/bin/bash

# Check if all required arguments are provided
if [ "$#" -lt 10 ]; then
    echo "Usage: $0 <PRIVATE_KEY> <USER_NAME> <HOSTNAME> <AWS_ACCESS_KEY_ID> <AWS_SECRET_ACCESS_KEY> <AWS_SESSION_TOKEN> <AWS_REGION> <ECR_REPOSITORY_URI> <API_URL> <DB_DSN>"
    exit 1
fi

# Assign arguments to variables
PRIVATE_KEY="$1"
USER_NAME="$2"
HOSTNAME="$3"
AWS_ACCESS_KEY_ID="$4"
AWS_SECRET_ACCESS_KEY="$5"
AWS_SESSION_TOKEN="$6"
AWS_REGION="$7"
ECR_REPOSITORY_URI="$8"
API_URL="$9"
DB_DSN="${10}"

# Write private key to file
echo "$PRIVATE_KEY" > private_key && chmod 600 private_key

# Execute remote commands
ssh -o StrictHostKeyChecking=no -i private_key ${USER_NAME}@${HOSTNAME} bash -s << 'EOF'
export AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
export AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN
export AWS_DEFAULT_REGION=$AWS_REGION
aws ecr get-login-password --region $AWS_REGION | docker login -u AWS --password-stdin $ECR_REPOSITORY_URI
docker rm -v $(docker ps -aq)
docker pull $ECR_REPOSITORY_URI:frontend
docker run -p "3000:80" -e API_URL="$API_URL" -d $ECR_REPOSITORY_URI:frontend
docker pull $ECR_REPOSITORY_URI:backend
docker run -p "8080:8080" -e DB_DSN="$DB_DSN" -d $ECR_REPOSITORY_URI:backend
sudo systemctl is-active --quiet nginx || sudo systemctl start nginx
EOF