#!/bin/bash

# Check if all required arguments are provided
if [ "$#" -lt 9 ]; then
    echo "Usage: $0 <PRIVATE_KEY> <USER_NAME> <HOST> <AWS_ACCESS_KEY_ID> <AWS_SECRET_ACCESS_KEY> <AWS_SESSION_TOKEN> <AWS_REGION> <ECR_REPOSITORY_URI> <DB_DSN>"
    exit 1
fi

# Assign arguments to variables
PRIVATE_KEY="$1"
USER_NAME="$2"
HOST="$3"
AWS_ACCESS_KEY_ID="$4"
AWS_SECRET_ACCESS_KEY="$5"
AWS_SESSION_TOKEN="$6"
AWS_REGION="$7"
ECR_REPOSITORY_URI="$8"
DB_DSN="$9"

echo "$HOST"
echo "$AWS_REGION"

# Write private key to file
echo "$PRIVATE_KEY" > private_key && chmod 600 private_key

# Execute remote commands, passing environment variables explicitly
ssh -o StrictHostKeyChecking=no -i private_key ${USER_NAME}@${HOST} bash -s \
  -- "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" "$AWS_SESSION_TOKEN" "$AWS_REGION" "$ECR_REPOSITORY_URI" "$DB_DSN" << 'EOF'
export AWS_ACCESS_KEY_ID=$1
export AWS_SECRET_ACCESS_KEY=$2
export AWS_SESSION_TOKEN=$3
export AWS_DEFAULT_REGION=$4
ECR_REPOSITORY_URI=$5

# Perform actions with the passed environment variables
echo "DB_DSN=$(echo "$6" | sed 's/\\//g')" > .env
docker login -u AWS -p $(aws ecr get-login-password --region us-east-1) $ECR_REPOSITORY_URI
docker rm -v -f $(docker ps -aq)
docker pull $ECR_REPOSITORY_URI:frontend
docker run -p "3000:80" --env-file .env -d $ECR_REPOSITORY_URI:frontend
docker pull $ECR_REPOSITORY_URI:backend
docker run -p "8080:8080" --env-file .env -d $ECR_REPOSITORY_URI:backend
sudo systemctl is-active --quiet nginx || sudo systemctl start nginx
EOF