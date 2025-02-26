import boto3
from dotenv import load_dotenv
import os

# Connect to AWS EC2
def connect_to_ec2():
    load_dotenv()

    try :
        ec2 = boto3.client('ec2',
                        os.getenv('AWS_REGION'),
                        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                        aws_session_token=os.getenv('AWS_SESSION_TOKEN')
                        )
        return ec2
    except Exception as e:
        print(e)

def create_ec2_instance():
    ec2 = connect_to_ec2()
    conn = ec2.run_instances(InstanceType="t2.micro",
                            MaxCount=1,
                            MinCount=1,
                            ImageId="ami-0c614dee691cbbf37")
    print("Dynamic EC2 Instance Created: ", conn['Instances'][0]['InstanceId'])

if __name__ == "__main__":
    create_ec2_instance()

